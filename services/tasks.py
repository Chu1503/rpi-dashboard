"""Google Tasks read-only service."""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import quote

from config import Settings
from services.cache import CachedService
from services.google_oauth import GOOGLE_WORKSPACE_SCOPES, authorized_session, get_json


SCOPES = ["https://www.googleapis.com/auth/tasks.readonly"]


class TasksService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.cache = CachedService("tasks", settings.cache_dir, settings.tasks_ttl)
        self.token_path = settings.secrets_dir / "google_workspace_token.json"

    def get(self, force: bool = False, allow_stale: bool = False) -> dict:
        return self.cache.get(
            self._fetch, {"tasks": [], "more_count": 0}, force=force,
            allow_stale=allow_stale,
            persist_success=not self.settings.demo_mode,
        )

    def _fetch(self) -> dict:
        if self.settings.demo_mode:
            return self._demo()
        session = authorized_session(self.token_path, GOOGLE_WORKSPACE_SCOPES)
        lists = get_json(
            session, "https://tasks.googleapis.com/tasks/v1/users/@me/lists",
            params={"maxResults": 100}, timeout=self.settings.request_timeout,
        ).get("items", [])

        tasks: list[dict] = []
        for task_list in lists:
            task_list_id = quote(task_list["id"], safe="")
            page_token = None
            while True:
                params = {"showCompleted": "false", "showHidden": "false", "maxResults": 100}
                if page_token:
                    params["pageToken"] = page_token
                response = get_json(
                    session, f"https://tasks.googleapis.com/tasks/v1/lists/{task_list_id}/tasks",
                    params=params, timeout=self.settings.request_timeout,
                )
                for item in response.get("items", []):
                    if item.get("status") != "completed" and item.get("title"):
                        tasks.append({
                            "id": item.get("id"), "title": item["title"],
                            "due": item.get("due"), "list": task_list.get("title", "Tasks"),
                        })
                page_token = response.get("nextPageToken")
                if not page_token:
                    break

        tasks.sort(key=lambda task: (task["due"] is None, task["due"] or "", task["title"].lower()))
        visible = tasks[: self.settings.max_tasks]
        return {"tasks": visible, "more_count": max(0, len(tasks) - len(visible))}

    def _demo(self) -> dict:
        today = datetime.now(timezone.utc).date().isoformat()
        tasks = [
            {"id": "1", "title": "Finish Alfred dashboard", "due": f"{today}T00:00:00.000Z", "list": "Personal"},
            {"id": "2", "title": "Submit assignment", "due": None, "list": "School"},
            {"id": "3", "title": "Buy groceries", "due": None, "list": "Personal"},
            {"id": "4", "title": "Laundry", "due": None, "list": "Personal"},
            {"id": "5", "title": "Reply to emails", "due": None, "list": "Personal"},
            {"id": "6", "title": "Review project notes", "due": None, "list": "Work"},
            {"id": "7", "title": "Order replacement cable", "due": None, "list": "Personal"},
            {"id": "8", "title": "Plan tomorrow", "due": None, "list": "Personal"},
            {"id": "9", "title": "Call home", "due": None, "list": "Personal"},
            {"id": "10", "title": "Water the plants", "due": None, "list": "Personal"},
        ]
        return {"tasks": tasks, "more_count": 3}
