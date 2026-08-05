from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path


class EventStore:
    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.path = project_dir / "events.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    def append(self, event_type: str, payload: dict | None = None, *, actor: str = "user") -> dict:
        event = {
            "id": uuid.uuid4().hex,
            "type": event_type,
            "actor": actor,
            "at": datetime.now(timezone.utc).isoformat(),
            "payload": payload or {},
        }
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, ensure_ascii=False) + "\n")
        return event

    def list(self) -> list[dict]:
        events: list[dict] = []
        for line in self.path.read_text("utf-8").splitlines():
            if not line.strip():
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return events

    def recent(self, limit: int = 100) -> list[dict]:
        return self.list()[-max(1, limit):]
