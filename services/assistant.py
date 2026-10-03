"""Grounded natural-language answers for Alfred's private phone companion."""

from __future__ import annotations

import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _joined(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return f"{', '.join(items[:-1])}, and {items[-1]}"


def _parse_datetime(value: str | None, target_zone=None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo and target_zone is not None:
            return parsed.astimezone(target_zone)
        return parsed.astimezone() if parsed.tzinfo else parsed
    except (TypeError, ValueError):
        return None


def _stale_suffix(section: dict) -> str:
    # Staleness remains available to the UI in section metadata, but repeating
    # it after every spoken answer is noisy and not useful at TV distance.
    return ""


class AssistantChannel:
    """Keep the latest phone answer for the single kiosk display to consume."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sequence = 0
        self._message: str | None = None

    def publish(self, message: str) -> int:
        with self._lock:
            self._sequence += 1
            self._message = message
            return self._sequence

    def latest(self, after: int | None = None) -> dict:
        with self._lock:
            message = self._message if after is not None and self._sequence > after else None
            return {"sequence": self._sequence, "message": message}

    def message_for(self, sequence: int) -> str | None:
        """Return the current message only when the requested sequence matches."""
        with self._lock:
            return self._message if sequence == self._sequence else None


class AssistantService:
    """Answer a deliberately small set of personal-data intents without an LLM."""

    POWER_PHRASES = {
        "turn on", "turn off", "turn on tv", "turn off tv", "turn the tv on",
        "turn the tv off", "tv on", "tv off", "power on", "power off",
        "power on tv", "power off tv",
    }

    def __init__(self, tasks, calendar, health, weather, display_timezone: str = "") -> None:
        self.tasks = tasks
        self.calendar = calendar
        self.health = health
        self.weather = weather
        try:
            self.timezone = ZoneInfo(display_timezone) if display_timezone else datetime.now().astimezone().tzinfo
        except ZoneInfoNotFoundError:
            self.timezone = datetime.now().astimezone().tzinfo

    @classmethod
    def is_power_command(cls, query: str) -> bool:
        normalized = _normalized(query)
        if normalized in cls.POWER_PHRASES:
            return True
        words = set(normalized.split())
        return (
            "tv" in words
            and bool(words.intersection({"turn", "power"}))
            and bool(words.intersection({"on", "off"}))
        )

    def answer(self, query: str) -> dict:
        normalized = _normalized(query)
        if not normalized:
            return self._result("unknown", "Type or say a question first.")

        if self._is_day_briefing(normalized):
            return self._result("briefing", self._briefing())
        if any(term in normalized for term in ("task", "to do", "todo")):
            return self._result("tasks", self._tasks())
        if any(term in normalized for term in ("next event", "what is next", "whats next")):
            return self._result("next_event", self._next_event())
        if any(term in normalized for term in ("calendar", "schedule", "event", "appointment")):
            day = "tomorrow" if "tomorrow" in normalized else "today" if "today" in normalized else None
            return self._result("calendar", self._calendar(day=day))
        if "sleep" in normalized:
            return self._result("sleep", self._sleep())
        if "step" in normalized or "walk" in normalized:
            return self._result("steps", self._steps())
        if any(term in normalized for term in ("heart rate", "heartbeat", "pulse", "bpm")):
            return self._result("heart_rate", self._heart_rate())
        if any(term in normalized for term in ("weather", "temperature", "outside")):
            return self._result("weather", self._weather())

        return self._result(
            "unknown",
            "I can answer questions about your tasks, calendar, next event, sleep, steps, heart rate, weather, or how your day looks.",
        )

    @staticmethod
    def _result(intent: str, answer: str) -> dict:
        return {"ok": True, "intent": intent, "answer": answer}

    @staticmethod
    def _is_day_briefing(normalized: str) -> bool:
        return any(
            phrase in normalized
            for phrase in (
                "how does my day look", "how is my day", "my day today",
                "day briefing", "daily briefing", "brief me", "morning briefing",
                "what do i have today", "what is on today", "whats on today",
                "tell me about my day",
            )
        )

    def _tasks(self) -> str:
        section = self.tasks.get(force=False, allow_stale=True)
        tasks = section.get("data", {}).get("tasks", [])
        more = section.get("data", {}).get("more_count", 0)
        if not section.get("meta", {}).get("available", True):
            return "I couldn't retrieve Google Tasks right now."
        if not tasks:
            return "You have no incomplete Google Tasks."
        names = [str(task.get("title", "Untitled task")) for task in tasks[:5]]
        total = len(tasks) + int(more or 0)
        remainder = max(0, total - len(names))
        tail = f", plus {remainder} more" if remainder else ""
        noun = "task" if total == 1 else "tasks"
        return f"You have {total} incomplete {noun}: {_joined(names)}{tail}." + _stale_suffix(section)

    def _calendar(self, *, day: str | None) -> str:
        section = self.calendar.get(force=False, allow_stale=True)
        events = section.get("data", {}).get("events", [])
        if not section.get("meta", {}).get("available", True):
            return "I couldn't retrieve Google Calendar right now."
        if day:
            target = datetime.now(self.timezone).date()
            if day == "tomorrow":
                target += timedelta(days=1)
            events = [event for event in events if self._event_date(event) == target]
        if not events:
            if day == "today":
                return "You have nothing else scheduled today."
            if day == "tomorrow":
                return "You have nothing scheduled tomorrow."
            return "You have no upcoming calendar events."
        descriptions = [self._event_description(event) for event in events[:4]]
        remainder = max(0, len(events) - len(descriptions))
        tail = f", plus {remainder} more" if remainder else ""
        prefix = "Today you have" if day == "today" else "Tomorrow you have" if day == "tomorrow" else "Your upcoming events are"
        return f"{prefix} {_joined(descriptions)}{tail}." + _stale_suffix(section)

    def _next_event(self) -> str:
        section = self.calendar.get(force=False, allow_stale=True)
        events = section.get("data", {}).get("events", [])
        if not section.get("meta", {}).get("available", True):
            return "I couldn't retrieve Google Calendar right now."
        if not events:
            return "You have no upcoming calendar events."
        return f"Your next event is {self._event_description(events[0])}." + _stale_suffix(section)

    def _briefing(self) -> str:
        with ThreadPoolExecutor(max_workers=3, thread_name_prefix="alfred-briefing") as pool:
            task_future = pool.submit(self.tasks.get, False, True)
            calendar_future = pool.submit(self.calendar.get, False, True)
            weather_future = pool.submit(self.weather.get, False, True)
            task_section = task_future.result()
            calendar_section = calendar_future.result()
            weather_section = weather_future.result()

        tasks = task_section.get("data", {}).get("tasks", [])
        task_total = len(tasks) + int(task_section.get("data", {}).get("more_count", 0) or 0)
        task_part = "You have no incomplete tasks" if task_total == 0 else f"You have {task_total} incomplete {'task' if task_total == 1 else 'tasks'}"

        today = datetime.now(self.timezone).date()
        events = [
            event for event in calendar_section.get("data", {}).get("events", [])
            if self._event_date(event) == today
        ]
        if events:
            event_part = f"Your next event is {self._event_description(events[0])}"
            if len(events) > 1:
                event_part += f", with {len(events) - 1} more later today"
        else:
            event_part = "nothing else is scheduled today"

        weather = weather_section.get("data", {})
        temperature = weather.get("temperature_c")
        condition = weather.get("condition")
        if temperature is None:
            weather_part = "weather is currently unavailable"
        else:
            weather_part = f"it is {round(float(temperature))} degrees Celsius"
            if condition:
                weather_part += f" with {str(condition).lower()}"

        return f"{task_part}. {event_part.capitalize()}. Right now, {weather_part}."

    def _sleep(self) -> str:
        section = self.health.get(force=False, allow_stale=True)
        data = section.get("data", {})
        minutes = data.get("sleep_minutes")
        if minutes is None:
            return "Your latest sleep duration is unavailable."
        hours, remaining = divmod(int(minutes), 60)
        when = _parse_datetime(data.get("sleep_ended_at"), self.timezone)
        date_part = f", ending {when.strftime('%B %d').replace(' 0', ' ')}," if when else ""
        return f"Your last sleep was{date_part} {hours} hours and {remaining} minutes." + _stale_suffix(section)

    def _steps(self) -> str:
        section = self.health.get(force=False, allow_stale=True)
        data = section.get("data", {})
        steps = data.get("steps")
        if steps is None:
            return "Your step count is unavailable."
        step_date = data.get("steps_date")
        if step_date == datetime.now(self.timezone).date().isoformat():
            when = "today"
        elif step_date:
            try:
                parsed = date.fromisoformat(step_date)
                when = f"for {parsed.strftime('%B %d').replace(' 0', ' ')}"
            except ValueError:
                when = "from the latest available day"
        else:
            when = "from the latest available day"
        return f"You have {int(steps):,} steps {when}." + _stale_suffix(section)

    def _heart_rate(self) -> str:
        section = self.health.get_heart_rate(force=False, allow_stale=True)
        data = section.get("data", {})
        heart_rate = data.get("heart_rate")
        if heart_rate is None:
            return "Your latest heart-rate measurement is unavailable."
        measured = _parse_datetime(data.get("heart_rate_measured_at"), self.timezone)
        when = f" at {measured.strftime('%I:%M %p').lstrip('0')}" if measured else ""
        return f"Your latest heart-rate measurement was {int(heart_rate)} beats per minute{when}." + _stale_suffix(section)

    def _weather(self) -> str:
        section = self.weather.get(force=False, allow_stale=True)
        data = section.get("data", {})
        temperature = data.get("temperature_c")
        condition = data.get("condition")
        if temperature is None:
            return "The weather is currently unavailable."
        answer = f"It is {round(float(temperature))} degrees Celsius"
        if condition:
            answer += f" with {str(condition).lower()}"
        return answer + "." + _stale_suffix(section)

    def _event_date(self, event: dict) -> date | None:
        value = event.get("start")
        if not value:
            return None
        if event.get("all_day"):
            try:
                return date.fromisoformat(value)
            except ValueError:
                return None
        parsed = _parse_datetime(value, self.timezone)
        return parsed.date() if parsed else None

    def _event_description(self, event: dict) -> str:
        title = str(event.get("title") or "Untitled event")
        if event.get("all_day"):
            return f"{title}, all day"
        start = _parse_datetime(event.get("start"), self.timezone)
        if not start:
            return title
        today = datetime.now(self.timezone).date()
        day = "today" if start.date() == today else f"on {start.strftime('%A')}"
        time_label = start.strftime("%I:%M %p").lstrip("0")
        return f"{title} {day} at {time_label}"
