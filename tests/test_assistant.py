import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from services.assistant import AssistantChannel, AssistantService


class StubService:
    def __init__(self, payload):
        self.payload = payload
        self.force_calls = []

    def get(self, force=False, allow_stale=False):
        self.force_calls.append(force)
        return self.payload

    def get_heart_rate(self, force=False, allow_stale=False):
        self.force_calls.append(force)
        return self.payload


def section(data, *, stale=False, available=True):
    return {
        "data": data,
        "meta": {"available": available, "stale": stale, "updated_at": "2026-08-30T12:00:00Z", "message": ""},
    }


class AssistantTests(unittest.TestCase):
    def setUp(self):
        self.tasks = StubService(section({
            "tasks": [{"id": "1", "title": "Submit assignment", "due": None}],
            "more_count": 0,
        }))
        self.calendar = StubService(section({
            "events": [{
                "id": "event-1", "title": "Office Hours",
                "start": "2099-08-30T15:00:00-05:00",
                "end": "2099-08-30T16:00:00-05:00", "all_day": False,
            }],
            "more_count": 0,
        }))
        self.health = StubService(section({
            "sleep_minutes": 416, "sleep_ended_at": "2026-08-30T07:00:00-05:00",
            "steps": 4312, "steps_date": "2026-08-30",
            "heart_rate": 68, "heart_rate_measured_at": "2026-08-30T11:42:00-05:00",
        }))
        self.weather = StubService(section({"temperature_c": 21.2, "condition": "Partly cloudy"}))
        self.assistant = AssistantService(
            self.tasks, self.calendar, self.health, self.weather, "America/Chicago"
        )

    def test_task_question_is_grounded_and_uses_dashboard_cache(self):
        result = self.assistant.answer("What are my tasks?")
        self.assertEqual(result["intent"], "tasks")
        self.assertIn("Submit assignment", result["answer"])
        self.assertEqual(self.tasks.force_calls, [False])

    def test_sleep_question_formats_duration(self):
        result = self.assistant.answer("How much did I sleep last night?")
        self.assertEqual(result["intent"], "sleep")
        self.assertIn("6 hours and 56 minutes", result["answer"])

    def test_power_phrases_are_explicit(self):
        self.assertTrue(self.assistant.is_power_command("Turn the TV off"))
        self.assertFalse(self.assistant.is_power_command("What is my TV schedule?"))

    def test_tomorrow_calendar_filters_to_tomorrow(self):
        tomorrow = datetime.now(ZoneInfo("America/Chicago")) + timedelta(days=1)
        self.calendar.payload["data"]["events"] = [{
            "id": "tomorrow", "title": "Tomorrow Meeting",
            "start": tomorrow.replace(hour=10, minute=0).isoformat(),
            "end": tomorrow.replace(hour=11, minute=0).isoformat(), "all_day": False,
        }]
        result = self.assistant.answer("calendar for tomorrow")
        self.assertEqual(result["intent"], "calendar")
        self.assertIn("Tomorrow you have", result["answer"])
        self.assertIn("Tomorrow Meeting", result["answer"])

    def test_calendar_speaks_configured_timezone(self):
        self.calendar.payload["data"]["events"] = [{
            "id": "tz", "title": "Optimization",
            "start": "2026-09-08T13:00:00+00:00",
            "end": "2026-09-08T14:15:00+00:00", "all_day": False,
        }]
        result = self.assistant.answer("calendar")
        self.assertIn("8:00 AM", result["answer"])
        self.assertNotIn("1:00 PM", result["answer"])

    def test_stale_source_warning_is_not_spoken(self):
        self.tasks.payload["meta"]["stale"] = True
        result = self.assistant.answer("tasks")
        self.assertNotIn("last known value", result["answer"])

    def test_unknown_question_explains_supported_topics(self):
        result = self.assistant.answer("Write me a novel")
        self.assertEqual(result["intent"], "unknown")
        self.assertIn("tasks", result["answer"])

    def test_channel_does_not_replay_on_initial_dashboard_connection(self):
        channel = AssistantChannel()
        sequence = channel.publish("Hello Chu")
        self.assertIsNone(channel.latest()["message"])
        self.assertEqual(channel.latest(sequence)["message"], None)
        self.assertEqual(channel.latest(sequence - 1)["message"], "Hello Chu")
        self.assertEqual(channel.message_for(sequence), "Hello Chu")
        self.assertIsNone(channel.message_for(sequence - 1))


if __name__ == "__main__":
    unittest.main()
