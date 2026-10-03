"""Tiny thread-safe memory + disk cache with stale-success fallback."""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


LOGGER = logging.getLogger(__name__)


class CachedService:
    def __init__(self, name: str, cache_dir: Path, ttl_seconds: int):
        self.name = name
        self.path = cache_dir / f"{name}.json"
        self.ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
        self._memory: dict[str, Any] | None = None

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _parse(value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    def _load(self) -> dict[str, Any] | None:
        if self._memory is not None:
            return self._memory
        try:
            self._memory = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            self._memory = None
        return self._memory

    def _save(self, payload: Any, updated_at: str) -> None:
        record = {"updated_at": updated_at, "payload": payload}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(record, separators=(",", ":")), encoding="utf-8")
        os.replace(temporary, self.path)
        self._memory = record

    def get(
        self,
        fetch: Callable[[], Any],
        unavailable_payload: Any,
        *,
        force: bool = False,
        allow_stale: bool = False,
        persist_success: bool = True,
    ) -> dict[str, Any]:
        """Return a fresh value, or the last successful value clearly marked stale."""
        with self._lock:
            record = self._load() if persist_success else None
            if record and not force:
                try:
                    age = (self._now() - self._parse(record["updated_at"])).total_seconds()
                    if age < self.ttl_seconds or allow_stale:
                        return self._response(
                            record["payload"],
                            record["updated_at"],
                            stale=age >= self.ttl_seconds,
                            message="Using the latest dashboard value." if age >= self.ttl_seconds else "",
                        )
                except (KeyError, TypeError, ValueError):
                    LOGGER.warning("Ignoring malformed %s cache", self.name)
                    record = None

            try:
                payload = fetch()
                updated_at = self._now().isoformat().replace("+00:00", "Z")
                if persist_success:
                    self._save(payload, updated_at)
                return self._response(payload, updated_at, stale=False)
            except Exception as exc:  # service failures must never take down the dashboard
                LOGGER.warning("%s refresh failed: %s", self.name, exc)
                if record:
                    return self._response(
                        record["payload"], record["updated_at"], stale=True,
                        message="Unable to update; showing the last successful data.",
                    )
                return self._response(
                    unavailable_payload, None, stale=False, available=False,
                    message="Unable to update.",
                )

    def invalidate_memory(self) -> None:
        with self._lock:
            self._memory = None

    @staticmethod
    def _response(
        payload: Any,
        updated_at: str | None,
        *,
        stale: bool,
        available: bool = True,
        message: str = "",
    ) -> dict[str, Any]:
        return {
            "data": payload,
            "meta": {
                "available": available,
                "stale": stale,
                "updated_at": updated_at,
                "message": message,
            },
        }
