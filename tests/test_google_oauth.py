import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services.google_oauth import GOOGLE_WORKSPACE_SCOPES, load_credentials


class _FakeCredentials:
    def __init__(self):
        self.expired = False
        self.refresh_token = "refresh-token"
        self.granted_scopes = GOOGLE_WORKSPACE_SCOPES
        self.valid = True
        self.refresh_count = 0

    def refresh(self, _request):
        self.refresh_count += 1


class GoogleOAuthTests(unittest.TestCase):
    def _token_file(self, folder: str, scopes: list[str]) -> Path:
        path = Path(folder) / "token.json"
        path.write_text(json.dumps({"scopes": scopes}), encoding="utf-8")
        return path

    def test_missing_shared_scope_forces_token_refresh_and_save(self):
        with tempfile.TemporaryDirectory() as folder:
            token_path = self._token_file(folder, GOOGLE_WORKSPACE_SCOPES[:2])
            credentials = _FakeCredentials()
            with (
                patch(
                    "services.google_oauth.Credentials.from_authorized_user_info",
                    return_value=credentials,
                ),
                patch("services.google_oauth.save_credentials") as save,
            ):
                result = load_credentials(token_path, GOOGLE_WORKSPACE_SCOPES)

        self.assertIs(result, credentials)
        self.assertEqual(credentials.refresh_count, 1)
        save.assert_called_once_with(credentials, token_path)

    def test_complete_shared_scope_set_keeps_valid_access_token(self):
        with tempfile.TemporaryDirectory() as folder:
            token_path = self._token_file(folder, GOOGLE_WORKSPACE_SCOPES)
            credentials = _FakeCredentials()
            with (
                patch(
                    "services.google_oauth.Credentials.from_authorized_user_info",
                    return_value=credentials,
                ),
                patch("services.google_oauth.save_credentials") as save,
            ):
                load_credentials(token_path, GOOGLE_WORKSPACE_SCOPES)

        self.assertEqual(credentials.refresh_count, 0)
        save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
