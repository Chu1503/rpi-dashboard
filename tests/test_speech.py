import subprocess
import unittest
import array
import io
import wave
from types import SimpleNamespace
from unittest.mock import patch

from services.speech import SpeechError, SpeechService


class SpeechServiceTests(unittest.TestCase):
    @patch("services.speech.subprocess.run")
    @patch("services.speech.shutil.which", return_value="/usr/bin/espeak-ng")
    @patch("services.speech.Path.read_bytes", return_value=b"RIFFtest")
    def test_generates_wav_without_a_shell(self, read_bytes, which, run):
        run.return_value = SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

        audio = SpeechService().synthesize("Hello   Chu")

        self.assertEqual(audio, b"RIFFtest")
        command = run.call_args.args[0]
        self.assertEqual(command[0:2], ["/usr/bin/espeak-ng", "-w"])
        self.assertEqual(command[-1], "Hello Chu")
        self.assertNotIn("shell", run.call_args.kwargs)

    @patch("services.speech.shutil.which", return_value=None)
    def test_missing_binary_has_an_actionable_error(self, which):
        with self.assertRaisesRegex(SpeechError, "not installed"):
            SpeechService().synthesize("Hello")

    @patch("services.speech.subprocess.run", side_effect=subprocess.TimeoutExpired("espeak-ng", 20))
    @patch("services.speech.shutil.which", return_value="/usr/bin/espeak-ng")
    def test_timeout_becomes_speech_error(self, which, run):
        with self.assertRaises(SpeechError):
            SpeechService().synthesize("Hello")

    @patch("services.speech.os.getuid", return_value=1000, create=True)
    @patch("services.speech.SpeechService._normalize_for_hdmi", return_value=b"RIFFstereo")
    @patch("services.speech.SpeechService.synthesize", return_value=b"RIFFtest")
    @patch("services.speech.subprocess.run")
    @patch("services.speech.shutil.which", return_value="/usr/bin/pw-play")
    def test_direct_playback_uses_pipewire_default_sink(self, which, run, synthesize, normalize, getuid):
        run.return_value = SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

        SpeechService()._speak("Hello Chu")

        playback = run.call_args_list[0]
        self.assertEqual(playback.args[0][0:2], ["/usr/bin/pw-play", "--media-role=Notification"])
        self.assertTrue(playback.args[0][2].endswith(".wav"))
        self.assertIn("XDG_RUNTIME_DIR", playback.kwargs["env"])

    def test_normalizes_espeak_mono_wav_for_hdmi(self):
        source = io.BytesIO()
        samples = array.array("h", [0, 4000, -4000, 8000, -8000] * 100)
        with wave.open(source, "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(22050)
            output.writeframes(samples.tobytes())

        normalized = SpeechService._normalize_for_hdmi(source.getvalue())

        with wave.open(io.BytesIO(normalized), "rb") as result:
            self.assertEqual(result.getnchannels(), 2)
            self.assertEqual(result.getsampwidth(), 2)
            self.assertEqual(result.getframerate(), 48000)
            self.assertGreater(result.getnframes(), 14_000)
            frames = array.array("h")
            frames.frombytes(result.readframes(result.getnframes()))
            preroll_samples = round(48_000 * SpeechService.HDMI_PREROLL_SECONDS) * 2
            self.assertTrue(all(sample == 0 for sample in frames[:preroll_samples]))
            self.assertGreater(max(abs(sample) for sample in frames), 20_000)

    @patch("services.speech.SpeechService._synthesize_piper", return_value=b"RIFFpiper")
    @patch("services.speech.SpeechService._normalize_for_hdmi", return_value=b"RIFFready")
    def test_playback_prefers_piper(self, normalize, piper):
        service = SpeechService()

        self.assertEqual(service.playback_audio("Good evening"), b"RIFFready")
        piper.assert_called_once_with("Good evening")
        normalize.assert_called_once_with(b"RIFFpiper")

    @patch("services.speech.SpeechService.synthesize", return_value=b"RIFFespeak")
    @patch("services.speech.SpeechService._synthesize_piper", side_effect=SpeechError("missing"))
    @patch("services.speech.SpeechService._normalize_for_hdmi", return_value=b"RIFFready")
    def test_playback_falls_back_to_espeak(self, normalize, piper, espeak):
        service = SpeechService()

        self.assertEqual(service.playback_audio("Good evening"), b"RIFFready")
        espeak.assert_called_once_with("Good evening")
        normalize.assert_called_once_with(b"RIFFespeak")


if __name__ == "__main__":
    unittest.main()
