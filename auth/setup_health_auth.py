"""One-time Google Health API OAuth authorization."""

from __future__ import annotations

import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.google_oauth import authorized_session, save_credentials  # noqa: E402
from services.health import BASE_URL, SCOPES  # noqa: E402


CLIENT_FILE = ROOT / "data" / "secrets" / "client_secret.json"
TOKEN_FILE = ROOT / "data" / "secrets" / "google_health_token.json"


def main() -> int:
    if not CLIENT_FILE.exists():
        print(f"Missing {CLIENT_FILE}")
        print("Download an OAuth Desktop app JSON file from Google Cloud and save it with that name.")
        return 1

    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_FILE), SCOPES)
    credentials = flow.run_local_server(
        host="localhost", port=0, open_browser=True,
        access_type="offline", prompt="consent",
        authorization_prompt_message="Open this URL in your browser to authorize Alfred Health:\n{url}",
        success_message="Alfred Health authorization completed. You can close this tab.",
    )
    save_credentials(credentials, TOKEN_FILE)
    print(f"Saved the refreshable Health token to {TOKEN_FILE}")

    try:
        session = authorized_session(TOKEN_FILE, SCOPES)
        response = session.get(
            f"{BASE_URL}/heart-rate/dataPoints",
            params={"pageSize": 1},
            timeout=15,
        )
        if response.status_code == 400:
            error = response.json().get("error", {})
            details = error.get("details", [])
            reason = next(
                (detail.get("reason") for detail in details if detail.get("reason")),
                None,
            )
            if reason == "ACCOUNT_NOT_LINKED":
                redirect = next(
                    (detail.get("metadata", {}).get("redirect_uri") for detail in details if detail.get("metadata")),
                    "https://fitbit.google.com/auth/signup",
                )
                print("The authorized Google account is not linked to Google Health/Fitbit yet.")
                print(f"Complete the account setup with the same Google account: {redirect}")
                print("Then run this script again to confirm Health access.")
                return 2
        response.raise_for_status()
        print("Google Health API check: OK")
    except Exception as exc:
        print("Token saved, but the Health API test could not read data.")
        print("Confirm API access, OAuth publishing/verification, scopes, and that your wearable has synced.")
        print(f"Google response: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
