"""Google Calendar read-only service."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from config import Settings
from services.cache import CachedService
from services.google_oauth import GOOGLE_WORKSPACE_SCOPES, authorized_session, get_json


SCOPES = [
    "https://www.googleapis.com/auth/calendar.events.readonly",
    "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
]
DEFAULT_COLORS = {
    "1": "#7986cb", "2": "#33b679", "3": "#8e24aa", "4": "#e67c73",
    "5": "#f6c026", "6": "#f5511d", "7": "#039be5", "8": "#616161",
    "9": "#3f51b5", "10": "#0b8043", "11": "#d60000",
}


class CalendarService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.cache = CachedService("calendar", settings.cache_dir, settings.calendar_ttl)
        self.token_path = settings.secrets_dir / "google_workspace_token.json"

    def get(self, force: bool = False, allow_stale: bool = False) -> dict:
        return self.cache.get(
            self._fetch, {"events": [], "more_count": 0}, force=force,
            allow_stale=allow_stale,
            persist_success=not self.settings.demo_mode,
        )

    def _fetch(self) -> dict:
        if self.settings.demo_mode:
            return self._demo()

        session = authorized_session(self.token_path, GOOGLE_WORKSPACE_SCOPES)
        local_zone = self._display_timezone()
        now = datetime.now(local_zone)
        end_of_range = datetime.combine(
            now.date() + timedelta(days=max(1, self.settings.calendar_days)),
            time.min,
            tzinfo=now.tzinfo,
        )
        base = "https://www.googleapis.com/calendar/v3"
        calendar_id = quote(self.settings.calendar_id, safe="")
        events_data = get_json(
            session,
            f"{base}/calendars/{calendar_id}/events",
            params={
                "timeMin": now.isoformat(),
                "timeMax": end_of_range.isoformat(),
                "singleEvents": "true",
                "orderBy": "startTime",
                "maxResults": 2500,
            },
            timeout=self.settings.request_timeout,
        )
        colors = DEFAULT_COLORS.copy()
        try:
            color_data = get_json(session, f"{base}/colors", timeout=self.settings.request_timeout)
            colors.update({key: value["background"] for key, value in color_data.get("event", {}).items()})
        except Exception:
            pass

        default_color = "#73c9b1"
        try:
            calendar_info = get_json(
                session, f"{base}/users/me/calendarList/{calendar_id}",
                timeout=self.settings.request_timeout,
            )
            default_color = calendar_info.get("backgroundColor", default_color)
        except Exception:
            pass

        normalized = [self._normalize(item, colors, default_color) for item in events_data.get("items", [])]
        normalized = [event for event in normalized if event]
        visible = normalized[: self.settings.max_events]
        return {"events": visible, "more_count": max(0, len(normalized) - len(visible))}

    def _display_timezone(self):
        configured = getattr(self.settings, "dashboard_time_zone", "").strip()
        if configured:
            try:
                return ZoneInfo(configured)
            except ZoneInfoNotFoundError:
                pass
        return datetime.now().astimezone().tzinfo

    @staticmethod
    def _normalize(item: dict, colors: dict[str, str], default_color: str) -> dict | None:
        start = item.get("start", {})
        end = item.get("end", {})
        all_day = "date" in start
        raw_start = start.get("date") if all_day else start.get("dateTime")
        raw_end = end.get("date") if all_day else end.get("dateTime")
        if not raw_start:
            return None
        return {
            "id": item.get("id", raw_start),
            "title": item.get("summary") or "Untitled event",
            "start": raw_start,
            "end": raw_end,
            "all_day": all_day,
            "color": colors.get(item.get("colorId", ""), default_color),
        }

    def _demo(self) -> dict:
        now = datetime.now(self._display_timezone())
        samples = [
            ("Gym Nick", 0, 8, "#e41f2b"),
            ("Peet's Coffee", 1, 11, "#f5cf63"),
            ("TEL Meeting", 1, 16, "#9693ef"),
            ("Peet's Coffee", 2, 11, "#f5cf63"),
            ("Peet's Coffee", 3, 14, "#f5cf63"),
        ]
        events = []
        for index, (name, day_offset, hour, color) in enumerate(samples, start=1):
            start = datetime.combine(
                now.date() + timedelta(days=day_offset),
                time(hour=hour),
                tzinfo=now.tzinfo,
            )
            if start <= now:
                start = now + timedelta(hours=1)
            events.append({
                "id": f"demo-{index}", "title": name, "start": start.isoformat(),
                "end": (start + timedelta(hours=1)).isoformat(), "all_day": False,
                "color": color,
            })
        return {"events": events, "more_count": 0}
