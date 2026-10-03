"""Sony TV control through the UNO Q's Linux-to-MCU Router Bridge."""

from __future__ import annotations

import itertools
import socket
import threading
import time
from pathlib import Path

import msgpack


class TvControlError(RuntimeError):
    """A safe, user-facing TV control failure."""


class TvService:
    """Send short RPC commands to the sketch running on the UNO Q MCU."""

    def __init__(self, settings):
        self.socket_path = Path(settings.tv_bridge_socket)
        self.timeout = settings.tv_rpc_timeout
        self._request_ids = itertools.count(1)
        self._lock = threading.Lock()
        self._last_power_at = 0.0

    def status(self) -> dict:
        available = self.socket_path.exists()
        return {
            "available": available,
            "message": (
                "UNO Q Bridge is available."
                if available
                else "UNO Q Bridge is unavailable on this machine."
            ),
        }

    def power(self) -> dict:
        # The normal Sony power command is a toggle. Debounce it so an
        # accidental double tap cannot immediately undo the requested action.
        with self._lock:
            now = time.monotonic()
            if now - self._last_power_at < 2.0:
                raise TvControlError("Please wait two seconds before sending power again.")
            result = self._rpc_call("tv_power")
            self._last_power_at = time.monotonic()

        if result is False:
            raise TvControlError("The UNO Q rejected the IR power command.")
        return {
            "ok": True,
            "message": "Sony power signal sent.",
            "warning": "The Sony power signal is a toggle.",
        }

    def command(self, action: str) -> dict:
        methods = {
            "volume_up": "tv_volume_up", "volume_down": "tv_volume_down",
            "hdmi_1": "tv_hdmi_1", "hdmi_2": "tv_hdmi_2",
        }
        if action not in methods:
            raise ValueError("Invalid TV command.")
        with self._lock:
            result = self._rpc_call(methods[action])
        if result is False:
            raise TvControlError("The UNO Q rejected the IR command.")
        return {"ok": True}

    def _rpc_call(self, method: str):
        if not hasattr(socket, "AF_UNIX") or not self.socket_path.exists():
            raise TvControlError(
                "UNO Q Bridge is unavailable. Run this on the UNO Q and flash the Alfred IR sketch."
            )

        request_id = next(self._request_ids)
        request = [0, request_id, method, []]
        unpacker = msgpack.Unpacker(raw=False)

        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(self.timeout)
                client.connect(str(self.socket_path))
                client.sendall(msgpack.packb(request, use_bin_type=True))

                while True:
                    chunk = client.recv(4096)
                    if not chunk:
                        raise TvControlError("UNO Q Bridge closed without a response.")
                    unpacker.feed(chunk)
                    for response in unpacker:
                        if not isinstance(response, list) or len(response) != 4:
                            continue
                        response_type, response_id, error, result = response
                        if response_type != 1 or response_id != request_id:
                            continue
                        if error:
                            raise TvControlError(f"UNO Q Bridge error: {error}")
                        return result
        except TvControlError:
            raise
        except (OSError, ValueError, msgpack.UnpackException) as exc:
            raise TvControlError(f"Could not contact the UNO Q IR controller: {exc}") from exc
