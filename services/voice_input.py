"""Always-on, offline USB microphone input for Alfred."""

from __future__ import annotations

import json
import logging
import array
import io
import math
import re
import shutil
import subprocess
import threading
import time
import wave
import os
import tempfile
from pathlib import Path
from typing import Callable


LOGGER = logging.getLogger(__name__)
CARD_LINE = re.compile(
    r"card\s+(?P<number>\d+):\s+(?P<id>[^\s]+)\s+\[[^]]+\],\s+"
    r"device\s+(?P<device>\d+):",
    re.IGNORECASE,
)


def _words(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", value.casefold())


def _edit_distance(left: str, right: str) -> int:
    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, 1):
        current = [left_index]
        for right_index, right_char in enumerate(right, 1):
            current.append(min(
                current[-1] + 1,
                previous[right_index] + 1,
                previous[right_index - 1] + (left_char != right_char),
            ))
        previous = current
    return previous[-1]


def _normalize_command(words: list[str]) -> str:
    # Vosk sometimes hears "calendar" as "Canada" on this microphone.
    # Correct only that observed single-word substitution.
    words = ["calendar" if word == "canada" else word for word in words]
    command = " ".join(words).strip()
    # Recover the short power phrase variants produced by the small offline
    # model with this USB microphone (for example, "van off").
    command = re.sub(r"^(?:van|fan|than|done)\s+(on|off)$", r"turn \1", command)
    if command in {"on", "off"}:
        command = f"turn {command}"
    # The UNO's small offline model consistently renders the short phrase
    # "turn on" as "dawn" with this microphone. Keep this correction narrow.
    if command in {"dawn", "turn one", "turned on", "that on"}:
        command = "turn on"
    power = re.search(r"\b(?:turn|power|van|fan|than|done)\s+(on|off)\b", command)
    if power:
        command = f"turn {power.group(1)}"
    return command


def _looks_like_command(transcript: str) -> bool:
    words = set(_words(_normalize_command(_words(transcript))))
    return bool(words.intersection({
        "task", "tasks", "calendar", "schedule", "event", "events",
        "sleep", "slept", "step", "steps", "heart", "weather",
        "turn", "power", "on", "off", "today", "tomorrow",
    }))


class VoiceInputService:
    """Listen for a wake word and dispatch the rest of the utterance."""

    def __init__(self, settings, on_command: Callable[[str], dict]) -> None:
        self.enabled = settings.voice_input_enabled
        self.model_path = settings.voice_model_path
        self.configured_device = settings.mic_device
        self.sample_rate = settings.voice_sample_rate
        self.wake_word = settings.wake_word.casefold()
        self.wake_words = {
            word.casefold()
            for word in settings.wake_words
            if re.fullmatch(r"[a-z0-9]+", word.casefold())
        } | {self.wake_word}
        self.wake_aliases = {
            word.casefold()
            for word in settings.wake_aliases
            if re.fullmatch(r"[a-z0-9]+", word.casefold())
        } | self.wake_words
        self.on_command = on_command
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._last_wake_chime_at = 0.0
        self._status = {
            "enabled": self.enabled,
            "listening": False,
            "wake_word": settings.wake_word,
            "wake_words": list(settings.wake_words),
            "wake_detected_at": None,
            "device": None,
            "last_heard": None,
            "last_command": None,
            "error": None,
        }

    def start(self) -> None:
        if not self.enabled or self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run,
            name="alfred-usb-voice",
            daemon=True,
        )
        self._thread.start()

    def status(self) -> dict:
        with self._lock:
            return dict(self._status)

    def _update(self, **values) -> None:
        with self._lock:
            self._status.update(values)

    def _run(self) -> None:
        model = None
        last_error = None
        while True:
            device = self._find_capture_device()
            if not device:
                message = (
                    "No USB microphone is detected. Reconnect the USB audio "
                    "adapter and confirm that it appears in lsusb and arecord -l."
                )
                self._update(listening=False, device=None, error=message)
                if message != last_error:
                    LOGGER.warning(message)
                    last_error = message
                time.sleep(5)
                continue

            if not self.model_path.is_dir():
                message = f"The Vosk speech model is missing: {self.model_path}"
                self._update(listening=False, device=device, error=message)
                if message != last_error:
                    LOGGER.error(message)
                    last_error = message
                time.sleep(10)
                continue

            try:
                if model is None:
                    from vosk import Model, SetLogLevel

                    SetLogLevel(-1)
                    model = Model(str(self.model_path))
                    LOGGER.info("Loaded offline speech model: %s", self.model_path.name)
                self._listen_once(model, device)
                last_error = None
            except Exception as exc:  # keep the unattended listener recoverable
                message = f"USB voice listener stopped: {exc}"
                self._update(listening=False, error=message)
                if message != last_error:
                    LOGGER.warning(message)
                    last_error = message
                time.sleep(3)

    def _find_capture_device(self) -> str | None:
        if self.configured_device:
            return self.configured_device
        binary = shutil.which("arecord")
        if not binary:
            return None
        try:
            result = subprocess.run(
                [binary, "-l"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None

        for line in result.stdout.splitlines():
            match = CARD_LINE.search(line)
            if not match:
                continue
            card_number = match.group("number")
            try:
                device_path = Path(f"/sys/class/sound/card{card_number}/device").resolve()
            except OSError:
                continue
            if "/usb" not in device_path.as_posix().casefold():
                continue
            return f"plughw:CARD={match.group('id')},DEV={match.group('device')}"
        return None

    def _listen_once(self, model, device: str) -> None:
        from vosk import KaldiRecognizer

        self._enable_usb_mic_agc(device)

        command = [
            shutil.which("arecord") or "arecord",
            "-q",
            "-D",
            device,
            "-t",
            "raw",
            "-f",
            "S16_LE",
            "-r",
            str(self.sample_rate),
            "-c",
            "1",
        ]
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        recognizer = KaldiRecognizer(model, self.sample_rate)
        # A generic speech model can hear "Computer" as unrelated words. A
        # second recognizer constrained to wake words is substantially more
        # reliable while the generic recognizer still handles full commands.
        wake_grammar = json.dumps(sorted(self.wake_aliases) + ["[unk]"])
        wake_recognizer = KaldiRecognizer(model, self.sample_rate, wake_grammar)
        armed_until = 0.0
        self._update(listening=True, device=device, error=None)
        LOGGER.info("Listening for wake words %s on %s", sorted(self.wake_words), device)

        try:
            while process.poll() is None:
                if process.stdout is None:
                    break
                audio = process.stdout.read(8000)
                if not audio:
                    break
                command_complete = recognizer.AcceptWaveform(audio)
                wake_complete = wake_recognizer.AcceptWaveform(audio)
                wake_heard = False
                if wake_complete:
                    wake_text = str(json.loads(wake_recognizer.Result()).get("text", "")).strip()
                else:
                    wake_text = str(json.loads(wake_recognizer.PartialResult()).get("partial", "")).strip()
                wake_heard = any(word in self.wake_aliases for word in _words(wake_text))
                if wake_heard and time.monotonic() >= armed_until:
                    armed_until = time.monotonic() + 7.0
                    self._update(wake_detected_at=time.time())
                    LOGGER.info("Wake word detected by keyword recognizer: %s", wake_text)
                    self._acknowledge_wake()

                if not command_complete:
                    continue
                transcript = str(json.loads(recognizer.Result()).get("text", "")).strip()
                if transcript:
                    self._update(last_heard=transcript)

                if wake_heard:
                    extracted = self.extract_command(transcript)
                    if extracted:
                        self._dispatch(extracted)
                        return
                    # The constrained recognizer may hear the wake word while
                    # the general recognizer returns only the command portion
                    # of the same utterance (for example, just "calendar").
                    if transcript and time.monotonic() < armed_until and _looks_like_command(transcript):
                        self._dispatch(_normalize_command(_words(transcript)))
                        return
                    # When the generic model did not also recognize the wake
                    # word, discard this utterance. It is usually the mangled
                    # wake phrase itself; the command follows after the chime.
                    continue
                if not transcript:
                    continue
                extracted = self.extract_command(transcript)
                if extracted is not None:
                    self._update(wake_detected_at=time.time())
                    self._acknowledge_wake()
                    if extracted:
                        self._dispatch(extracted)
                        return
                    armed_until = time.monotonic() + 7.0
                    LOGGER.info("Wake word heard; waiting for a command")
                    continue
                if time.monotonic() < armed_until and _looks_like_command(transcript):
                    self._dispatch(_normalize_command(_words(transcript)))
                    return
        finally:
            self._update(listening=False)
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
            if process.returncode not in (None, 0, -15):
                detail = ""
                if process.stderr is not None:
                    detail = process.stderr.read().decode(errors="replace").strip()
                if detail:
                    raise RuntimeError(detail)

    @staticmethod
    def _enable_usb_mic_agc(device: str) -> None:
        mixer = shutil.which("amixer")
        match = re.search(r"CARD=([^,]+)", device)
        if not mixer or not match:
            return
        subprocess.run(
            [mixer, "-q", "-c", match.group(1), "set", "Auto Gain Control", "on"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=3,
        )

    def extract_command(self, transcript: str) -> str | None:
        words = _words(transcript)
        for index, word in enumerate(words):
            # Small offline models commonly render "Alfred" as a close
            # phonetic spelling. Accept one edit, while keeping a wake word.
            fuzzy_wake = len(word) >= 5 and any(
                _edit_distance(word, wake_word) <= 1
                for wake_word in self.wake_words
            )
            if word in self.wake_aliases or fuzzy_wake:
                return _normalize_command(words[index + 1 :])
        return None

    def _acknowledge_wake(self) -> None:
        """Play one short cue without changing Alfred's speech path."""
        now = time.monotonic()
        if now - self._last_wake_chime_at < 1.5:
            return
        self._last_wake_chime_at = now
        player = shutil.which("pw-play")
        if not player:
            return
        rate = 48_000
        mono = array.array("h")
        mono.extend([0] * round(rate * 0.08))
        for frequency, duration in ((760, 0.16),):
            frame_count = round(rate * duration)
            for frame in range(frame_count):
                edge = min(frame / (rate * 0.015), (frame_count - frame) / (rate * 0.02), 1.0)
                mono.append(round(12_000 * max(0.0, edge) * math.sin(2 * math.pi * frequency * frame / rate)))
            mono.extend([0] * round(rate * 0.035))
        stereo = array.array("h")
        for sample in mono:
            stereo.extend((sample, sample))
        output = io.BytesIO()
        with wave.open(output, "wb") as destination:
            destination.setnchannels(2)
            destination.setsampwidth(2)
            destination.setframerate(rate)
            destination.writeframes(stereo.tobytes())

        environment = os.environ.copy()
        if hasattr(os, "getuid"):
            environment.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
        path = None
        try:
            with tempfile.NamedTemporaryFile(prefix="alfred-wake-", suffix=".wav", delete=False) as handle:
                path = handle.name
                handle.write(output.getvalue())
            subprocess.run(
                [player, "--media-role=Notification", path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=4,
                env=environment,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            LOGGER.warning("Wake acknowledgement could not play: %s", exc)
        finally:
            if path:
                Path(path).unlink(missing_ok=True)

    def _dispatch(self, command: str) -> None:
        self._update(last_command=command)
        LOGGER.info("USB voice command: %s", command)
        result = self.on_command(command)
        answer = str(result.get("answer", "")) if isinstance(result, dict) else ""
        # Stop capturing while the television speaks so Alfred cannot hear and
        # recursively trigger on its own response.
        playback_seconds = min(14.0, max(2.5, len(answer.split()) / 2.5 + 1.5))
        time.sleep(playback_seconds)
