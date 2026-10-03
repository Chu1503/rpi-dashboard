"""One-time Google Calendar + Tasks OAuth authorization."""

from __future__ import annotations

import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.calendar import SCOPES as CALENDAR_SCOPES  # noqa: E402
from services.google_oauth import authorized_session, get_json, save_credentials  # noqa: E402
from services.tasks import SCOPES as TASKS_SCOPES  # noqa: E402


CLIENT_FILE = ROOT / "data" / "secrets" / "client_secret.json"
TOKEN_FILE = ROOT / "data" / "secrets" / "google_workspace_token.json"
SCOPES = [*CALENDAR_SCOPES, *TASKS_SCOPES]


def main() -> int:
    if not CLIENT_FILE.exists():
        print(f"Missing {CLIENT_FILE}")
        print("Download an OAuth Desktop app JSON file from Google Cloud and save it with that name.")
        return 1

    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_FILE), SCOPES)
    credentials = flow.run_local_server(
        host="localhost", port=0, open_browser=True,
        access_type="offline", prompt="consent",
        authorization_prompt_message="Open this URL in your browser to authorize Alfred:\n{url}",
        success_message="Alfred authorization completed. You can close this tab.",
    )
    save_credentials(credentials, TOKEN_FILE)
    print(f"Saved the refreshable workspace token to {TOKEN_FILE}")

    session = authorized_session(TOKEN_FILE, SCOPES)
    calendar = get_json(session, "https://www.googleapis.com/calendar/v3/users/me/calendarList", params={"maxResults": 1})
    task_lists = get_json(session, "https://tasks.googleapis.com/tasks/v1/users/@me/lists", params={"maxResults": 1})
    print(f"Calendar check: OK ({len(calendar.get('items', []))} calendar returned)")
    print(f"Tasks check: OK ({len(task_lists.get('items', []))} task list returned)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
