from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path


class ProjectEngine:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

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
            "pipeline": {
                "source": "ready",
                "geometry": "locked",
                "environment": "locked",
                "final": "locked",
                "branding": "locked"
            },
            "assets": {},
            "comments": [],
            "quality": {}
        }
        self.write(project_id, state)
        return state

    def list(self) -> list[dict]:
        output = []
        for path in sorted(self.root.glob("*/project.json")):
            try: output.append(json.loads(path.read_text("utf-8")))
            except Exception: continue
        return output

    def read(self, project_id: str) -> dict:
        return json.loads((self.root / project_id / "project.json").read_text("utf-8"))

    def write(self, project_id: str, state: dict) -> None:
        path = self.root / project_id / "project.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, ensure_ascii=False, indent=2), "utf-8")

    def path(self, project_id: str) -> Path:
        path = (self.root / project_id).resolve()
        if self.root.resolve() not in path.parents:
            raise ValueError("Unsafe project path")
        return path
