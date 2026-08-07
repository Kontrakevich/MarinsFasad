from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .event_store import EventStore


class ProjectEngine:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def create(self, name: str) -> dict:
        slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", name.strip()).strip("-").lower() or "project"
        project_id = f"{slug}-{uuid.uuid4().hex[:8]}"
        project = self.root / project_id
        for folder in ("images/master", "images/preview", "images/stages", "prompts", "diagnostics", "history"):
            (project / folder).mkdir(parents=True, exist_ok=True)
        state = {
            "id": project_id,
            "name": name.strip() or project_id,
            "version": "0.8.0-dev",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "pipeline": {"source": "ready", "geometry": "locked", "environment": "locked", "final": "locked", "branding": "locked"},
            "assets": {},
            "comments": [],
            "quality": {},
            "diagnostics": [],
            "active_stage": "source",
        }
        self.write(project_id, state)
        self.events(project_id).append("ProjectCreated", {"name": state["name"]})
        return self.read(project_id)

    def list(self) -> list[dict]:
        with self._lock:
            output = []
            for path in sorted(self.root.glob("*/project.json")):
                try:
                    output.append(json.loads(path.read_text("utf-8")))
                except Exception:
                    continue
            return output

    def read(self, project_id: str) -> dict:
        with self._lock:
            state = json.loads((self.path(project_id) / "project.json").read_text("utf-8"))
            state["event_count"] = len(self.events(project_id).list())
            return state

    def write(self, project_id: str, state: dict) -> None:
        with self._lock:
            state["updated_at"] = datetime.now(timezone.utc).isoformat()
            path = self.path(project_id) / "project.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
            try:
                temporary.write_text(
                    json.dumps(state, ensure_ascii=False, indent=2),
                    "utf-8",
                )
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)

    def record(self, project_id: str, event_type: str, payload: dict | None = None, *, actor: str = "user") -> dict:
        with self._lock:
            return self.events(project_id).append(event_type, payload, actor=actor)

    def history(self, project_id: str, limit: int = 100) -> list[dict]:
        with self._lock:
            return self.events(project_id).recent(limit)

    def events(self, project_id: str) -> EventStore:
        return EventStore(self.path(project_id))

    def path(self, project_id: str) -> Path:
        path = (self.root / project_id).resolve()
        root = self.root.resolve()
        if path != root and root not in path.parents:
            raise ValueError("Unsafe project path")
        return path
