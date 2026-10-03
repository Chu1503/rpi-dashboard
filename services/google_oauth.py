"""Server-side Google OAuth token loading and automatic refresh."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from google.auth.transport.requests import AuthorizedSession, Request
from google.oauth2.credentials import Credentials


_TOKEN_LOCK = threading.Lock()

GOOGLE_WORKSPACE_SCOPES = [
    "https://www.googleapis.com/auth/calendar.events.readonly",
    "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
    "https://www.googleapis.com/auth/tasks.readonly",
]


def _scope_set(value: Any) -> set[str]:
    if isinstance(value, str):
        return set(value.split())
    return set(value or [])


def load_credentials(token_path: Path, scopes: list[str]) -> Credentials:
    if not token_path.exists():
        raise RuntimeError(f"Google authorization is not configured ({token_path.name} is missing)")

    # Calendar and Tasks intentionally share one refresh token. Always compare
    # the scopes stored on disk with the complete scope set requested by the
    # caller; otherwise one service can refresh and save a narrower token that
    # silently removes the other service's access.
    with _TOKEN_LOCK:
        token_info = json.loads(token_path.read_text(encoding="utf-8"))
        credentials = Credentials.from_authorized_user_info(token_info, scopes=scopes)
        missing_stored_scopes = set(scopes) - _scope_set(token_info.get("scopes"))

        if (credentials.expired or missing_stored_scopes) and credentials.refresh_token:
            credentials.refresh(Request())
            granted_scopes = _scope_set(credentials.granted_scopes)
            missing_granted_scopes = set(scopes) - granted_scopes if granted_scopes else set()
            if missing_granted_scopes:
                raise RuntimeError(
                    "Google did not grant every required scope; rerun the matching "
                    "authorization setup script"
                )
            save_credentials(credentials, token_path)

    if not credentials.valid:
        raise RuntimeError("Google credentials are invalid; run the matching setup script again")
    return credentials


def save_credentials(credentials: Credentials, token_path: Path) -> None:
    token_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = token_path.with_suffix(".tmp")
    temporary.write_text(credentials.to_json(), encoding="utf-8")
    try:
        os.chmod(temporary, 0o600)
    except OSError:
        pass
    os.replace(temporary, token_path)


def authorized_session(token_path: Path, scopes: list[str]) -> AuthorizedSession:
    return AuthorizedSession(load_credentials(token_path, scopes))


def get_json(
    session: AuthorizedSession,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    timeout: int = 12,
) -> dict[str, Any]:
    response = session.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    return response.json()


def post_json(
    session: AuthorizedSession,
    url: str,
    *,
    payload: dict[str, Any],
    timeout: int = 12,
) -> dict[str, Any]:
    response = session.post(url, json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()
