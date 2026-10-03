import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from services.voice_input import VoiceInputService, _looks_like_command, _normalize_command


class VoiceInputTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        settings = SimpleNamespace(
            voice_input_enabled=False,
            voice_model_path=Path(self.temp_dir.name),
            mic_device="",
            voice_sample_rate=16000,
            wake_word="Alfred",
            wake_words=("Alfred", "Computer", "Jarvis"),
            wake_aliases=("Alfred", "Alford", "Fred", "Computer", "Jarvis", "Jervis"),
        )
        self.service = VoiceInputService(settings, lambda command: {"answer": command})

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_extracts_command_after_wake_word(self):
        self.assertEqual(
            self.service.extract_command("Hey Alfred, show my calendar for today"),
            "show my calendar for today",
        )

    def test_accepts_common_wake_word_recognition_variant(self):
        self.assertEqual(self.service.extract_command("Alford turn on"), "turn on")
        self.assertEqual(self.service.extract_command("Alfret show calendar"), "show calendar")

    def test_recovers_observed_usb_mic_phrase(self):
        self.service.wake_aliases.add("fred")
        self.assertEqual(self.service.extract_command("hi fred van off"), "turn off")

    def test_recovers_calendar_as_canada(self):
        self.assertEqual(_normalize_command(["canada"]), "calendar")
        self.assertEqual(_normalize_command(["canada", "for", "tomorrow"]), "calendar for tomorrow")
        self.assertTrue(_looks_like_command("canada for tomorrow"))

    def test_wake_word_alone_arms_followup(self):
        self.assertEqual(self.service.extract_command("Alfred"), "")
        self.assertEqual(self.service.extract_command("Computer"), "")
        self.assertEqual(self.service.extract_command("Jarvis"), "")

    def test_each_wake_word_extracts_a_command(self):
        self.assertEqual(self.service.extract_command("Computer show calendar"), "show calendar")
        self.assertEqual(self.service.extract_command("Jarvis show tasks"), "show tasks")

    def test_ignores_utterance_without_wake_word(self):
        self.assertIsNone(self.service.extract_command("show my tasks"))

    def test_recovers_command_after_keyword_model_hears_mangled_wake(self):
        self.assertTrue(_looks_like_command("luke luke show my calendar"))
        self.assertFalse(_looks_like_command("luke luke"))
        self.assertEqual(_normalize_command(["luke", "turn", "on"]), "turn on")
        self.assertEqual(_normalize_command(["dawn"]), "turn on")
        self.assertEqual(self.service.extract_command("computer dawn"), "turn on")
