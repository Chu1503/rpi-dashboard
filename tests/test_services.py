import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from services.calendar import CalendarService
from services.google_oauth import GOOGLE_WORKSPACE_SCOPES
from services.health import HealthService
from services.tasks import TasksService
from services.weather import WEATHER_CODES


class ServiceNormalizationTests(unittest.TestCase):
    @staticmethod
    def _health_service():
        settings = SimpleNamespace(
            demo_mode=False,
            secrets_dir=Path("secrets"),
            cache_dir=Path("cache"),
            health_ttl=600,
            steps_ttl=120,
            heart_rate_ttl=300,
            request_timeout=12,
        )
        return HealthService(settings)

    def test_steps_falls_back_to_yesterday_when_today_has_no_rollup(self):
        service = self._health_service()
        response = {
            "rollupDataPoints": [
                {
                    "civilStartTime": {"date": {"year": 2026, "month": 8, "day": 28}},
                    "steps": {"countSum": "9768"},
                },
                {"civilStartTime": {"date": {"year": 2026, "month": 8, "day": 29}}},
            ]
        }
        with patch("services.health.post_json", return_value=response):
            steps = service._steps(object(), datetime.fromisoformat("2026-08-29T00:05:00-05:00"))

        self.assertEqual(steps, {"count": 9768, "date": "2026-08-28"})

    def test_steps_keeps_a_real_zero_for_today(self):
        service = self._health_service()
        response = {
            "rollupDataPoints": [
                {
                    "civilStartTime": {"date": {"year": 2026, "month": 8, "day": 28}},
                    "steps": {"countSum": "9768"},
                },
                {
                    "civilStartTime": {"date": {"year": 2026, "month": 8, "day": 29}},
                    "steps": {"countSum": "0"},
                },
            ]
        }
        with patch("services.health.post_json", return_value=response):
            steps = service._steps(object(), datetime.fromisoformat("2026-08-29T00:05:00-05:00"))

        self.assertEqual(steps, {"count": 0, "date": "2026-08-29"})

    def test_calendar_all_day_event(self):
        event = CalendarService._normalize(
            {"id": "one", "summary": "Holiday", "start": {"date": "2026-08-23"}, "end": {"date": "2026-08-24"}},
            {}, "#abcdef",
        )
        self.assertTrue(event["all_day"])
        self.assertEqual(event["title"], "Holiday")
        self.assertEqual(event["color"], "#abcdef")

    def test_weather_code_mapping(self):
        self.assertEqual(WEATHER_CODES[2], "Partly cloudy")
        self.assertEqual(WEATHER_CODES[95], "Thunderstorm")

    def test_tasks_requests_the_complete_shared_workspace_scope_set(self):
        settings = SimpleNamespace(
            demo_mode=False,
            secrets_dir=Path("secrets"),
            cache_dir=Path("cache"),
            tasks_ttl=60,
            request_timeout=12,
            max_tasks=14,
        )
        service = TasksService(settings)
        with (
            patch("services.tasks.authorized_session", return_value=object()) as authorize,
            patch("services.tasks.get_json", return_value={"items": []}),
        ):
            service._fetch()

        authorize.assert_called_once_with(service.token_path, GOOGLE_WORKSPACE_SCOPES)

    def test_calendar_requests_the_complete_shared_workspace_scope_set(self):
        settings = SimpleNamespace(
            demo_mode=False,
            secrets_dir=Path("secrets"),
            cache_dir=Path("cache"),
            calendar_ttl=60,
            calendar_days=14,
            calendar_id="primary",
            dashboard_time_zone="America/Chicago",
            request_timeout=12,
            max_events=5,
        )
        service = CalendarService(settings)
        with (
            patch("services.calendar.authorized_session", return_value=object()) as authorize,
            patch("services.calendar.get_json", return_value={"items": []}),
        ):
            service._fetch()

        authorize.assert_called_once_with(service.token_path, GOOGLE_WORKSPACE_SCOPES)

    def test_calendar_uses_configured_display_timezone(self):
        settings = SimpleNamespace(
            dashboard_time_zone="America/Chicago",
            cache_dir=Path("cache"),
            calendar_ttl=60,
            secrets_dir=Path("secrets"),
        )
        zone = CalendarService(settings)._display_timezone()
        self.assertEqual(str(zone), "America/Chicago")


if __name__ == "__main__":
    unittest.main()
