import unittest
from unittest.mock import patch

from app import app, assistant_channel, display_control_channel, settings


class AppTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def test_page_and_health_check_start_without_credentials(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/remote").status_code, 200)
        self.assertEqual(self.client.get("/healthz").get_json(), {"status": "ok"})

    def test_lan_client_can_only_reach_phone_remote_routes(self):
        remote = {"REMOTE_ADDR": "192.168.1.50"}
        self.assertEqual(
            self.client.get("/remote", environ_overrides=remote).status_code, 200
        )
        self.assertEqual(
            self.client.get("/api/tv/status", environ_overrides=remote).status_code,
            200,
        )
        self.assertEqual(
            self.client.get("/api/dashboard", environ_overrides=remote).status_code,
            404,
        )
        self.assertEqual(
            self.client.get("/api/assistant/speech/1", environ_overrides=remote).status_code,
            404,
        )
        self.assertEqual(
            self.client.get("/api/assistant/speech-stream/1", environ_overrides=remote).status_code,
            404,
        )
        self.assertEqual(
            self.client.get("/api/display/control", environ_overrides=remote).status_code,
            404,
        )
        self.assertEqual(
            self.client.get("/api/voice/status", environ_overrides=remote).status_code,
            404,
        )

    def test_usb_voice_status_is_available_to_the_local_kiosk(self):
        response = self.client.get("/api/voice/status")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            set(response.get_json()),
            {
                "enabled", "listening", "wake_word", "device", "last_heard",
                "last_command", "error",
            },
        )

    @patch("app.speech_service.prepared_audio", return_value=(b"RIFFtest", "audio/wav", "wav"))
    def test_kiosk_can_fetch_generated_speech_for_latest_answer(self, synthesize):
        sequence = assistant_channel.publish("Your tasks are ready.")
        response = self.client.get(f"/api/assistant/speech/{sequence}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "audio/wav")
        self.assertEqual(response.data, b"RIFFtest")
        synthesize.assert_called_once_with(sequence, "Your tasks are ready.")

    @patch("app.speech_service.stream_edge", return_value=iter((b"ID3", b"audio")))
    def test_kiosk_can_stream_natural_speech(self, stream_edge):
        sequence = assistant_channel.publish("Your tasks are ready.")
        response = self.client.get(f"/api/assistant/speech-stream/{sequence}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "audio/mpeg")
        self.assertEqual(response.data, b"ID3audio")
        stream_edge.assert_called_once_with("Your tasks are ready.")

    @patch("app.assistant_service.answer", return_value={"ok": True, "intent": "tasks", "answer": "One task."})
    def test_authenticated_phone_can_ask_assistant(self, answer):
        response = self.client.post(
            "/api/assistant/query",
            headers={
                "X-Alfred-Remote": "1",
                "X-Alfred-Remote-Token": settings.tv_remote_token,
            },
            json={"query": "What are my tasks?"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["answer"], "One task.")
        answer.assert_called_once_with("What are my tasks?")

    def test_assistant_rejects_missing_access_key(self):
        response = self.client.post(
            "/api/assistant/query",
            headers={"X-Alfred-Remote": "1"},
            json={"query": "What are my tasks?"},
        )
        self.assertEqual(response.status_code, 403)

    def test_tv_power_rejects_missing_access_key(self):
        response = self.client.post(
            "/api/tv/power", headers={"X-Alfred-Remote": "1"}
        )
        self.assertEqual(response.status_code, 403)

    def test_display_refresh_is_authenticated_and_consumed_once(self):
        denied = self.client.post(
            "/api/display/refresh", headers={"X-Alfred-Remote": "1"}
        )
        self.assertEqual(denied.status_code, 403)

        response = self.client.post(
            "/api/display/refresh",
            headers={
                "X-Alfred-Remote": "1",
                "X-Alfred-Remote-Token": settings.tv_remote_token,
            },
            json={},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])
        self.assertEqual(self.client.get("/api/display/control").get_json()["action"], "refresh")
        self.assertIsNone(self.client.get("/api/display/control").get_json()["action"])

    def test_display_scroll_is_authenticated_and_clamped(self):
        response = self.client.post(
            "/api/display/scroll",
            headers={
                "X-Alfred-Remote": "1",
                "X-Alfred-Remote-Token": settings.tv_remote_token,
            },
            json={"position": 1.5},
        )
        self.assertEqual(response.status_code, 200)
        command = self.client.get("/api/display/control").get_json()
        self.assertEqual(command["action"], "scroll")
        self.assertEqual(command["position"], 1.0)

    @patch("app.tv_service.power", return_value={"ok": True, "message": "sent"})
    def test_tv_power_calls_bridge_with_access_key(self, power):
        response = self.client.post(
            "/api/tv/power",
            headers={
                "X-Alfred-Remote": "1",
                "X-Alfred-Remote-Token": settings.tv_remote_token,
            },
            json={"action": "power"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])
        power.assert_called_once_with()

    def test_unconfigured_services_return_safe_json(self):
        response = self.client.get("/api/dashboard")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(set(payload), {"calendar", "health", "tasks", "weather"})
        for section in payload.values():
            self.assertIn("data", section)
            self.assertIn("meta", section)

    def test_manual_refresh_endpoint_is_safe(self):
        response = self.client.post("/api/refresh")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.get_json()), {"calendar", "health", "tasks", "weather"})

    def test_heart_rate_has_independent_cached_and_forced_endpoints(self):
        cached = self.client.get("/api/heart-rate")
        forced = self.client.post("/api/heart-rate/refresh")
        self.assertEqual(cached.status_code, 200)
        self.assertEqual(forced.status_code, 200)
        for response in (cached, forced):
            payload = response.get_json()
            self.assertEqual(
                set(payload["data"]), {"heart_rate", "heart_rate_measured_at"}
            )
            self.assertIn("meta", payload)

    def test_steps_has_independent_cached_and_forced_endpoints(self):
        cached = self.client.get("/api/steps")
        forced = self.client.post("/api/steps/refresh")
        self.assertEqual(cached.status_code, 200)
        self.assertEqual(forced.status_code, 200)
        for response in (cached, forced):
            payload = response.get_json()
            self.assertEqual(set(payload["data"]), {"steps", "steps_date"})
            self.assertIn("meta", payload)


if __name__ == "__main__":
    unittest.main()
