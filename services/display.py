"""One-shot control channel for the single local kiosk display."""

from __future__ import annotations

import threading


class DisplayControlChannel:
    """Hold one pending display action until Chromium consumes it."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sequence = 0
        self._pending_action: str | None = None
        self._pending_payload: dict = {}

    def publish(self, action: str, **payload) -> int:
        with self._lock:
            self._sequence += 1
            self._pending_action = action
            self._pending_payload = payload
            return self._sequence

    def take(self) -> dict:
        with self._lock:
            action = self._pending_action
            payload = self._pending_payload
            self._pending_action = None
            self._pending_payload = {}
            return {"sequence": self._sequence, "action": action, **payload}
