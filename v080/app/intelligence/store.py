from __future__ import annotations

import json
import re
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SECRET = re.compile(r"(password|passwd|token|api[_-]?key|secret|authorization|cookie)", re.I)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def sanitize(value: Any, key: str = "") -> Any:
    if key and _SECRET.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k): sanitize(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    return value


class IntelligenceStore:
    """Thread-safe native persistence for System №1 intelligence."""

    schema_version = "system1-intelligence-sqlite-v1"

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "system1.sqlite3"
        self._lock = threading.RLock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=20)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _init_db(self) -> None:
        with self._lock, self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    job_id TEXT,
                    stage TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    summary_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_runs_project ON runs(project_id, started_at DESC);
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT,
                    project_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    component TEXT NOT NULL,
                    stage TEXT,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    evidence_ref TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_events_run ON events(run_id, id);
                CREATE INDEX IF NOT EXISTS idx_events_project ON events(project_id, id DESC);
                CREATE TABLE IF NOT EXISTS diagnoses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT,
                    project_id TEXT NOT NULL,
                    layer TEXT NOT NULL,
                    status TEXT NOT NULL,
                    root_cause TEXT,
                    confidence REAL NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_diagnoses_project ON diagnoses(project_id, id DESC);
                CREATE TABLE IF NOT EXISTS feedback (
                    feedback_id TEXT PRIMARY KEY,
                    run_id TEXT,
                    project_id TEXT NOT NULL,
                    raw_feedback TEXT NOT NULL,
                    layer1_status TEXT NOT NULL,
                    layer2_invoked INTEGER NOT NULL,
                    analysis_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_feedback_project ON feedback(project_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS regression_cases (
                    case_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    run_id TEXT,
                    status TEXT NOT NULL,
                    case_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_regression_project ON regression_cases(project_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS preferences (
                    preference_id TEXT PRIMARY KEY,
                    scope TEXT NOT NULL,
                    project_id TEXT,
                    rule_key TEXT NOT NULL,
                    status TEXT NOT NULL,
                    evidence_count INTEGER NOT NULL,
                    value_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_preferences_project ON preferences(project_id, updated_at DESC);
                """
            )

    @staticmethod
    def _dump(value: Any) -> str:
        return json.dumps(sanitize(value), ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _load(value: str | None) -> Any:
        if not value:
            return {}
        try:
            return json.loads(value)
        except Exception:
            return {}

    def upsert_run(self, run_id: str, project_id: str, *, job_id: str | None = None,
                   stage: str = "environment", status: str = "processing",
                   summary: dict[str, Any] | None = None) -> None:
        now = utcnow()
        ended = now if status in {"completed", "failed", "approved"} else None
        with self._lock, self._connect() as db:
            db.execute(
                """
                INSERT INTO runs(run_id, project_id, job_id, stage, status, started_at, ended_at, summary_json)
                VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(run_id) DO UPDATE SET
                    job_id=COALESCE(excluded.job_id, runs.job_id),
                    status=excluded.status,
                    ended_at=COALESCE(excluded.ended_at, runs.ended_at),
                    summary_json=excluded.summary_json
                """,
                (run_id, project_id, job_id, stage, status, now, ended, self._dump(summary or {})),
            )

    def add_event(self, *, run_id: str | None, project_id: str, event_type: str,
                  component: str, stage: str | None, status: str,
                  payload: Any = None, evidence_ref: str | None = None) -> None:
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT INTO events(run_id,project_id,timestamp,event_type,component,stage,status,payload_json,evidence_ref) VALUES(?,?,?,?,?,?,?,?,?)",
                (run_id, project_id, utcnow(), event_type, component, stage, status,
                 self._dump(payload or {}), evidence_ref),
            )

    def add_diagnosis(self, *, run_id: str | None, project_id: str, layer: str,
                      diagnosis: dict[str, Any]) -> None:
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT INTO diagnoses(run_id,project_id,layer,status,root_cause,confidence,payload_json,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (
                    run_id, project_id, layer, str(diagnosis.get("status") or "UNKNOWN"),
                    diagnosis.get("failure_type") or diagnosis.get("root_cause"),
                    float(diagnosis.get("confidence") or 0.0), self._dump(diagnosis), utcnow(),
                ),
            )

    def add_feedback(self, *, feedback_id: str, run_id: str | None, project_id: str,
                     raw_feedback: str, layer1_status: str, layer2_invoked: bool,
                     analysis: dict[str, Any]) -> None:
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO feedback(feedback_id,run_id,project_id,raw_feedback,layer1_status,layer2_invoked,analysis_json,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (feedback_id, run_id, project_id, raw_feedback, layer1_status,
                 1 if layer2_invoked else 0, self._dump(analysis), utcnow()),
            )

    def add_regression(self, *, case_id: str, project_id: str, run_id: str | None,
                       status: str, case: dict[str, Any]) -> None:
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO regression_cases(case_id,project_id,run_id,status,case_json,created_at) VALUES(?,?,?,?,?,?)",
                (case_id, project_id, run_id, status, self._dump(case), utcnow()),
            )

    def add_preference_evidence(self, *, preference_id: str, scope: str, project_id: str | None,
                                rule_key: str, status: str, value: dict[str, Any]) -> None:
        now = utcnow()
        with self._lock, self._connect() as db:
            existing = db.execute(
                "SELECT evidence_count FROM preferences WHERE preference_id=?", (preference_id,)
            ).fetchone()
            count = int(existing["evidence_count"]) + 1 if existing else 1
            db.execute(
                """
                INSERT INTO preferences(preference_id,scope,project_id,rule_key,status,evidence_count,value_json,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(preference_id) DO UPDATE SET
                    status=excluded.status,
                    evidence_count=excluded.evidence_count,
                    value_json=excluded.value_json,
                    updated_at=excluded.updated_at
                """,
                (preference_id, scope, project_id, rule_key, status, count,
                 self._dump(value), now, now),
            )

    def latest_run(self, project_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT * FROM runs WHERE project_id=? ORDER BY started_at DESC LIMIT 1", (project_id,)
            ).fetchone()
        if not row:
            return None
        data = dict(row)
        data["summary"] = self._load(data.pop("summary_json", "{}"))
        return data

    def latest_diagnosis(self, project_id: str, *, layer: str | None = None) -> dict[str, Any] | None:
        sql = "SELECT * FROM diagnoses WHERE project_id=?"
        params: list[Any] = [project_id]
        if layer:
            sql += " AND layer=?"
            params.append(layer)
        sql += " ORDER BY id DESC LIMIT 1"
        with self._lock, self._connect() as db:
            row = db.execute(sql, params).fetchone()
        if not row:
            return None
        data = dict(row)
        data["payload"] = self._load(data.pop("payload_json", "{}"))
        return data

    def recent_events(self, project_id: str, limit: int = 30) -> list[dict[str, Any]]:
        with self._lock, self._connect() as db:
            rows = db.execute(
                "SELECT * FROM events WHERE project_id=? ORDER BY id DESC LIMIT ?", (project_id, int(limit))
            ).fetchall()
        output = []
        for row in reversed(rows):
            data = dict(row)
            data["payload"] = self._load(data.pop("payload_json", "{}"))
            output.append(data)
        return output

    def summary(self, project_id: str) -> dict[str, Any]:
        latest_run = self.latest_run(project_id)
        technical = self.latest_diagnosis(project_id, layer="technical")
        alignment = self.latest_diagnosis(project_id, layer="alignment")
        with self._lock, self._connect() as db:
            counts = {
                "runs": db.execute("SELECT COUNT(*) c FROM runs WHERE project_id=?", (project_id,)).fetchone()["c"],
                "events": db.execute("SELECT COUNT(*) c FROM events WHERE project_id=?", (project_id,)).fetchone()["c"],
                "feedback": db.execute("SELECT COUNT(*) c FROM feedback WHERE project_id=?", (project_id,)).fetchone()["c"],
                "regressions": db.execute("SELECT COUNT(*) c FROM regression_cases WHERE project_id=?", (project_id,)).fetchone()["c"],
                "preferences": db.execute("SELECT COUNT(*) c FROM preferences WHERE project_id=?", (project_id,)).fetchone()["c"],
            }
            feedback_row = db.execute(
                "SELECT * FROM feedback WHERE project_id=? ORDER BY created_at DESC LIMIT 1", (project_id,)
            ).fetchone()
            regression_row = db.execute(
                "SELECT * FROM regression_cases WHERE project_id=? ORDER BY created_at DESC LIMIT 1", (project_id,)
            ).fetchone()
        feedback = None
        if feedback_row:
            feedback = dict(feedback_row)
            feedback["analysis"] = self._load(feedback.pop("analysis_json", "{}"))
            feedback["layer2_invoked"] = bool(feedback["layer2_invoked"])
        regression = None
        if regression_row:
            regression = dict(regression_row)
            regression["case"] = self._load(regression.pop("case_json", "{}"))
        return {
            "version": "1.0.0",
            "architecture": "layer1-technical-then-layer2-alignment",
            "storage": self.schema_version,
            "layer2_gate": "only-after-layer1-has-no-sufficient-technical-root-cause",
            "latest_run": latest_run,
            "layer1_technical": technical["payload"] if technical else None,
            "layer2_alignment": alignment["payload"] if alignment else None,
            "latest_feedback": feedback,
            "latest_regression": regression,
            "counts": counts,
        }
