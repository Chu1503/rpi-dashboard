"""Natural speech for the TV dashboard, with a fully local fallback."""

from __future__ import annotations

import shutil
import subprocess
import logging
import os
import tempfile
import array
import io
import sys
import threading
import wave
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path


LOGGER = logging.getLogger(__name__)


class SpeechError(RuntimeError):
    """Raised when local speech audio cannot be generated."""


class SpeechService:
    """Generate loud, HDMI-friendly WAV speech with local fallbacks."""

    TARGET_RATE = 48_000
    HDMI_PREROLL_SECONDS = 0.18
    HDMI_TRAILING_SECONDS = 0.10
    TARGET_PEAK = 30_500
    MAX_GAIN = 3.5

    def __init__(self) -> None:
        self._player = ThreadPoolExecutor(max_workers=1, thread_name_prefix="alfred-speech")
        self._generator = ThreadPoolExecutor(max_workers=2, thread_name_prefix="alfred-voice")
        self._prepared_lock = threading.Lock()
        self._prepared: dict[int, Future[tuple[bytes, str, str]]] = {}
        self._voice_lock = threading.Lock()
        self._piper_voice = None
        self._piper_failed = False
        configured_model = os.environ.get("ALFRED_PIPER_MODEL", "").strip()
        self._piper_model = (
            Path(configured_model).expanduser()
            if configured_model
            else Path(__file__).resolve().parents[1]
            / "data"
            / "voices"
            / "en_GB-semaine-medium.onnx"
        )
        self._speaker_id = int(os.environ.get("ALFRED_PIPER_SPEAKER", "2"))
        self._edge_voice = os.environ.get("ALFRED_TTS_VOICE", "en-GB-RyanNeural").strip()
        self._edge_rate = os.environ.get("ALFRED_TTS_RATE", "+5%").strip()
        self._edge_volume = os.environ.get("ALFRED_TTS_VOLUME", "+0%").strip()
        self._edge_pitch = os.environ.get("ALFRED_TTS_PITCH", "+0Hz").strip()

    def warm_up_async(self) -> None:
        """Load the neural voice after startup, before the first question."""
        if self._piper_model.is_file():
            self._player.submit(self._warm_up)

    def _warm_up(self) -> None:
        try:
            self._load_piper_voice()
        except SpeechError as exc:
            LOGGER.warning("Piper voice unavailable; using eSpeak fallback: %s", exc)

    def synthesize(self, text: str) -> bytes:
        binary = shutil.which("espeak-ng")
        if not binary:
            raise SpeechError("espeak-ng is not installed on the UNO Q.")

        clean_text = " ".join(str(text).split()).strip()[:1000]
        if not clean_text:
            raise SpeechError("There is no response to speak.")

        with tempfile.NamedTemporaryFile(prefix="alfred-", suffix=".wav", delete=False) as handle:
            output_path = Path(handle.name)
        try:
            try:
                result = subprocess.run(
                    [
                        binary,
                        "-w",
                        str(output_path),
                        "-v",
                        "en-us",
                        "-s",
                        "158",
                        "-a",
                        "180",
                        clean_text,
                    ],
                    capture_output=True,
                    check=False,
                    timeout=20,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise SpeechError("The UNO Q could not generate speech audio.") from exc

            audio = output_path.read_bytes()
            if result.returncode != 0 or not audio.startswith(b"RIFF"):
                detail = result.stderr.decode("utf-8", errors="replace").strip()
                raise SpeechError(detail or "The UNO Q could not generate valid speech audio.")
            return audio
        finally:
            output_path.unlink(missing_ok=True)

    def speak_async(self, text: str) -> None:
        """Play through the UNO user's default PipeWire sink without blocking HTTP."""
        self._player.submit(self._speak, text)

    def playback_audio(self, text: str) -> bytes:
        """Return a browser- and HDMI-friendly 48 kHz stereo WAV."""
        try:
            audio = self._synthesize_piper(text)
        except SpeechError as exc:
            LOGGER.warning("Piper synthesis failed; using eSpeak fallback: %s", exc)
            audio = self.synthesize(text)
        return self._normalize_for_hdmi(audio)

    def prepare_async(self, sequence: int, text: str) -> None:
        """Begin synthesis immediately, while the kiosk receives the answer."""
        with self._prepared_lock:
            self._prepared[sequence] = self._generator.submit(self._render_audio, text)
            for old_sequence in sorted(self._prepared)[:-4]:
                self._prepared.pop(old_sequence, None)

    def prepared_audio(self, sequence: int, text: str) -> tuple[bytes, str, str]:
        """Return pre-generated speech, or synthesize if the kiosk won the race."""
        with self._prepared_lock:
            future = self._prepared.get(sequence)
            if future is None:
                future = self._generator.submit(self._render_audio, text)
                self._prepared[sequence] = future
        try:
            return future.result(timeout=25)
        except TimeoutError as exc:
            raise SpeechError("Alfred's voice took too long to generate.") from exc

    def _render_audio(self, text: str) -> tuple[bytes, str, str]:
        try:
            # Edge supplies a much more natural voice, but its service returns
            # MP3 only.  Decode it on the UNO so Chromium receives the same
            # simple 48 kHz WAV format as Alfred's proven local voice path.
            return self._edge_wav(text), "audio/wav", "wav"
        except SpeechError as exc:
            LOGGER.warning("Online neural voice unavailable; using local voice: %s", exc)
            return self.playback_audio(text), "audio/wav", "wav"

    def _edge_wav(self, text: str) -> bytes:
        try:
            import miniaudio
        except ImportError as exc:
            raise SpeechError("The natural voice WAV decoder is not installed.") from exc
        try:
            decoded = miniaudio.decode(
                self._synthesize_edge(text),
                output_format=miniaudio.SampleFormat.SIGNED16,
                nchannels=2,
                sample_rate=self.TARGET_RATE,
            )
        except (miniaudio.MiniaudioError, RuntimeError, ValueError) as exc:
            raise SpeechError("The natural voice could not be converted to WAV.") from exc

        pcm = decoded.samples.tobytes()
        if not pcm:
            raise SpeechError("The natural voice returned empty audio.")

        output = io.BytesIO()
        with wave.open(output, "wb") as destination:
            destination.setnchannels(decoded.nchannels)
            destination.setsampwidth(2)
            destination.setframerate(decoded.sample_rate)
            destination.writeframes(pcm)
        return self._normalize_for_hdmi(output.getvalue())

    def _synthesize_edge(self, text: str) -> bytes:
        return b"".join(self.stream_edge(text))

    def stream_edge(self, text: str):
        """Yield natural MP3 audio as Microsoft produces it for low latency."""
        clean_text = " ".join(str(text).split()).strip()[:1000]
        if not clean_text:
            raise SpeechError("There is no response to speak.")
        try:
            import edge_tts

            speech = edge_tts.Communicate(
                clean_text,
                self._edge_voice,
                rate=self._edge_rate,
                volume=self._edge_volume,
                pitch=self._edge_pitch,
                connect_timeout=5,
                receive_timeout=15,
            )
            received_audio = False
            for chunk in speech.stream_sync():
                if chunk.get("type") != "audio":
                    continue
                received_audio = True
                yield chunk["data"]
        except Exception as exc:
            raise SpeechError("The online neural voice could not be reached.") from exc
        if not received_audio:
            raise SpeechError("The online neural voice returned no audio.")

    def _load_piper_voice(self):
        """Load and retain the Piper model so subsequent replies stay fast."""
        with self._voice_lock:
            if self._piper_voice is not None:
                return self._piper_voice
            if self._piper_failed:
                raise SpeechError("The Piper voice could not be loaded.")
            if not self._piper_model.is_file():
                self._piper_failed = True
                raise SpeechError(f"The Piper voice model is missing: {self._piper_model}")

            try:
                from piper import PiperVoice

                self._piper_voice = PiperVoice.load(str(self._piper_model))
            except (ImportError, OSError, RuntimeError, ValueError) as exc:
                self._piper_failed = True
                raise SpeechError("The Piper voice could not be loaded.") from exc
            LOGGER.info("Loaded Alfred neural voice: %s", self._piper_model.name)
            return self._piper_voice

    def _synthesize_piper(self, text: str) -> bytes:
        clean_text = " ".join(str(text).split()).strip()[:1000]
        if not clean_text:
            raise SpeechError("There is no response to speak.")

        voice = self._load_piper_voice()
        try:
            from piper import SynthesisConfig

            synthesis_config = SynthesisConfig(
                # Final HDMI normalization below supplies the loudness without
                # clipping the neural model's waveform here.
                speaker_id=self._speaker_id,
                volume=1.12,
                length_scale=0.92,
                noise_scale=0.68,
                noise_w_scale=0.82,
                normalize_audio=True,
            )
            output = io.BytesIO()
            with self._voice_lock:
                with wave.open(output, "wb") as wav_file:
                    voice.synthesize_wav(
                        clean_text,
                        wav_file,
                        syn_config=synthesis_config,
                    )
            audio = output.getvalue()
        except (ImportError, OSError, RuntimeError, ValueError, wave.Error) as exc:
            raise SpeechError("The UNO Q could not generate Piper speech audio.") from exc
        if not audio.startswith(b"RIFF"):
            raise SpeechError("The UNO Q generated invalid Piper speech audio.")
        return audio

    def _speak(self, text: str) -> None:
        try:
            audio = self._normalize_for_hdmi(self.synthesize(text))
            player = shutil.which("pw-play")
            if not player:
                raise SpeechError("pw-play is not installed on the UNO Q.")

            environment = os.environ.copy()
            if hasattr(os, "getuid"):
                environment.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
            with tempfile.NamedTemporaryFile(prefix="alfred-play-", suffix=".wav", delete=False) as handle:
                playback_path = Path(handle.name)
                handle.write(audio)
            try:
                result = subprocess.run(
                    [player, "--media-role=Notification", str(playback_path)],
                    capture_output=True,
                    check=False,
                    timeout=60,
                    env=environment,
                )
                if result.returncode != 0:
                    detail = result.stderr.decode("utf-8", errors="replace").strip()
                    raise SpeechError(detail or "PipeWire could not play Alfred's response.")
            finally:
                playback_path.unlink(missing_ok=True)
        except SpeechError as exc:
            LOGGER.error("TV speech playback failed: %s", exc)
        except (OSError, subprocess.TimeoutExpired) as exc:
            LOGGER.error("TV speech playback failed: %s", exc)

    @classmethod
    def _normalize_for_hdmi(cls, audio: bytes) -> bytes:
        """Convert speech to loud 48 kHz stereo with an HDMI wake-up lead-in."""
        try:
            with wave.open(io.BytesIO(audio), "rb") as source:
                channels = source.getnchannels()
                width = source.getsampwidth()
                rate = source.getframerate()
                frames = source.readframes(source.getnframes())
        except (EOFError, wave.Error) as exc:
            raise SpeechError("The generated speech WAV could not be decoded.") from exc

        if width != 2 or channels not in {1, 2} or rate <= 0:
            raise SpeechError("The generated speech WAV has an unsupported format.")

        samples = array.array("h")
        samples.frombytes(frames)
        if sys.byteorder != "little":
            samples.byteswap()
        if channels == 2:
            mono = [(samples[index] + samples[index + 1]) // 2 for index in range(0, len(samples), 2)]
        else:
            mono = samples
        if not mono:
            raise SpeechError("The generated speech WAV is empty.")

        target_rate = cls.TARGET_RATE
        output_frames = max(1, round(len(mono) * target_rate / rate))
        resampled = array.array("h")
        for output_index in range(output_frames):
            position = output_index * rate / target_rate
            left_index = min(int(position), len(mono) - 1)
            right_index = min(left_index + 1, len(mono) - 1)
            fraction = position - left_index
            value = round(mono[left_index] + (mono[right_index] - mono[left_index]) * fraction)
            resampled.append(value)

        peak = max(abs(value) for value in resampled)
        gain = min(cls.MAX_GAIN, cls.TARGET_PEAK / max(peak, 1))
        amplified = array.array(
            "h",
            (
                max(-32768, min(32767, round(value * gain)))
                for value in resampled
            ),
        )

        # Some TVs mute HDMI between sounds and miss the first syllable while the
        # audio path wakes. Opening the stream with silence prevents that clipping.
        preroll_frames = round(target_rate * cls.HDMI_PREROLL_SECONDS)
        trailing_frames = round(target_rate * cls.HDMI_TRAILING_SECONDS)
        stereo = array.array("h", [0]) * (preroll_frames * 2)
        for value in amplified:
            stereo.extend((value, value))
        stereo.extend([0] * (trailing_frames * 2))
        if sys.byteorder != "little":
            stereo.byteswap()

        output = io.BytesIO()
        with wave.open(output, "wb") as destination:
            destination.setnchannels(2)
            destination.setsampwidth(2)
            destination.setframerate(target_rate)
            destination.writeframes(stereo.tobytes())
        return output.getvalue()
