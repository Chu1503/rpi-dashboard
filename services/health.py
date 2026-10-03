"""Isolated Google Health API v4 integration."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from config import Settings
from services.cache import CachedService
from services.google_oauth import authorized_session, get_json, post_json


SCOPES = [
    "https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly",
    "https://www.googleapis.com/auth/googlehealth.health_metrics_and_measurements.readonly",
    "https://www.googleapis.com/auth/googlehealth.sleep.readonly",
]
BASE_URL = "https://health.googleapis.com/v4/users/me/dataTypes"


class HealthService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.cache = CachedService("health", settings.cache_dir, settings.health_ttl)
        self.steps_cache = CachedService(
            "steps", settings.cache_dir, getattr(settings, "steps_ttl", 120)
        )
        self.heart_rate_cache = CachedService(
            "heart_rate", settings.cache_dir, settings.heart_rate_ttl
        )
        self.token_path = settings.secrets_dir / "google_health_token.json"

    def get(self, force: bool = False, allow_stale: bool = False) -> dict:
        empty = {
            "sleep_minutes": None,
            "sleep_ended_at": None,
            "steps": None,
            "steps_date": None,
            "heart_rate": None,
            "heart_rate_measured_at": None,
        }
        return self.cache.get(
            self._fetch, empty, force=force, allow_stale=allow_stale,
            persist_success=not self.settings.demo_mode,
        )

    def get_heart_rate(self, force: bool = False, allow_stale: bool = False) -> dict:
        """Refresh only the latest heart-rate reading on its own cadence."""
        empty = {"heart_rate": None, "heart_rate_measured_at": None}
        return self.heart_rate_cache.get(
            self._fetch_heart_rate, empty, force=force, allow_stale=allow_stale,
            persist_success=not self.settings.demo_mode,
        )

    def get_steps(self, force: bool = False, allow_stale: bool = False) -> dict:
        """Refresh today's step rollup without refetching sleep and heart rate."""
        empty = {"steps": None, "steps_date": None}
        return self.steps_cache.get(
            self._fetch_steps, empty, force=force, allow_stale=allow_stale,
            persist_success=not self.settings.demo_mode,
        )

    def _fetch_steps(self) -> dict:
        if self.settings.demo_mode:
            return {
                "steps": 6842,
                "steps_date": datetime.now().astimezone().date().isoformat(),
            }
        session = authorized_session(self.token_path, SCOPES)
        steps = self._steps(session, datetime.now().astimezone())
        return {
            "steps": steps["count"] if steps else None,
            "steps_date": steps["date"] if steps else None,
        }

    def _fetch_heart_rate(self) -> dict:
        if self.settings.demo_mode:
            return {
                "heart_rate": 71,
                "heart_rate_measured_at": datetime.now(timezone.utc).isoformat(),
            }
        session = authorized_session(self.token_path, SCOPES)
        return self._heart_rate(session, datetime.now().astimezone())

    def _fetch(self) -> dict:
        if self.settings.demo_mode:
            return {
                "sleep_minutes": 454,
                "sleep_ended_at": datetime.now(timezone.utc).isoformat(),
                "steps": 6842,
                "steps_date": datetime.now().astimezone().date().isoformat(),
                "heart_rate": 71,
                "heart_rate_measured_at": datetime.now(timezone.utc).isoformat(),
            }
        session = authorized_session(self.token_path, SCOPES)
        now = datetime.now().astimezone()
        sleep = self._sleep(session, now)
        steps = self._steps(session, now)
        return {
            "steps": steps["count"] if steps else None,
            "steps_date": steps["date"] if steps else None,
            "sleep_minutes": sleep["minutes"] if sleep else None,
            "sleep_ended_at": sleep["ended_at"] if sleep else None,
            **self._heart_rate(session, now),
        }

    @staticmethod
    def _rollup_date(point: dict) -> date | None:
        """Read the civil date from a Google Health daily-rollup point."""
        civil_start = point.get("civilStartTime", {})
        value = civil_start.get("date", civil_start)
        try:
            return date(int(value["year"]), int(value["month"]), int(value["day"]))
        except (KeyError, TypeError, ValueError):
            return None

    def _steps(self, session, now: datetime) -> dict | None:
        # Shortly after local midnight Google may not have created today's rollup
        # yet. Fetch yesterday as a fallback instead of replacing valid data with
        # a blank value. The returned date lets the UI identify fallback data.
        yesterday = now.date() - timedelta(days=1)
        tomorrow = now.date() + timedelta(days=1)
        payload = {
            "range": {
                "start": {"date": {"year": yesterday.year, "month": yesterday.month, "day": yesterday.day}},
                "end": {"date": {"year": tomorrow.year, "month": tomorrow.month, "day": tomorrow.day}},
            },
            "windowSizeDays": 1,
        }
        result = post_json(
            session, f"{BASE_URL}/steps/dataPoints:dailyRollUp", payload=payload,
            timeout=self.settings.request_timeout,
        )
        points = result.get("rollupDataPoints", [])
        candidates = []
        for point in points:
            value = point.get("steps", {}).get("countSum")
            rollup_date = self._rollup_date(point)
            if value is not None and rollup_date is not None:
                candidates.append((rollup_date, int(value)))
        if not candidates:
            return None
        rollup_date, count = max(candidates, key=lambda candidate: candidate[0])
        return {"count": count, "date": rollup_date.isoformat()}

    def _sleep(self, session, now: datetime) -> dict | None:
        start = (now - timedelta(days=2)).date().isoformat()
        end = (now.date() + timedelta(days=1)).isoformat()
        result = get_json(
            session, f"{BASE_URL}/sleep/dataPoints",
            params={"pageSize": 10, "filter": f'sleep.interval.civil_end_time >= "{start}" AND sleep.interval.civil_end_time < "{end}"'},
            timeout=self.settings.request_timeout,
        )
        for point in result.get("dataPoints", []):
            sleep = point.get("sleep", {})
            if sleep.get("metadata", {}).get("nap"):
                continue
            minutes = sleep.get("summary", {}).get("minutesAsleep")
            if minutes is not None:
                return {
                    "minutes": int(minutes),
                    "ended_at": sleep.get("interval", {}).get("endTime"),
                }
        return None

    def _heart_rate(self, session, now: datetime) -> dict:
        since = (now.astimezone(timezone.utc) - timedelta(days=2)).isoformat().replace("+00:00", "Z")
        result = get_json(
            session, f"{BASE_URL}/heart-rate/dataPoints",
            params={"pageSize": 1, "filter": f'heart_rate.sample_time.physical_time >= "{since}"'},
            timeout=self.settings.request_timeout,
        )
        points = result.get("dataPoints", [])
        if not points:
            return {"heart_rate": None, "heart_rate_measured_at": None}
        heart = points[0].get("heartRate", {})
        bpm = heart.get("beatsPerMinute")
        measured_at = heart.get("sampleTime", {}).get("physicalTime")
        return {"heart_rate": int(bpm) if bpm is not None else None, "heart_rate_measured_at": measured_at}
