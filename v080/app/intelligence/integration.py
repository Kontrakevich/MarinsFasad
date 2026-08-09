from __future__ import annotations

import threading
from pathlib import Path

from ..project_engine import ProjectEngine
from .orchestrator import System1Intelligence


_SYSTEMS: dict[str, System1Intelligence] = {}
_LOCK = threading.RLock()

_original_read = ProjectEngine.read
_original_write = ProjectEngine.write
_original_record = ProjectEngine.record
ProjectEngine._system1_original_read = _original_read  # type: ignore[attr-defined]


def _system(engine: ProjectEngine) -> System1Intelligence:
    key = str(Path(engine.root).resolve())
    with _LOCK:
        current = _SYSTEMS.get(key)
        if current is None:
            current = System1Intelligence(engine.root)
            _SYSTEMS[key] = current
        return current


def read_with_intelligence(self: ProjectEngine, project_id: str) -> dict:
    state = _original_read(self, project_id)
    try:
        state["system1_intelligence"] = _system(self).summary(project_id)
    except Exception as exc:
        state["system1_intelligence"] = {
            "version": "1.0.0",
            "status": "summary-unavailable",
            "error": f"{type(exc).__name__}: {exc}",
        }
    return state


def write_without_transient_intelligence(self: ProjectEngine, project_id: str, state: dict) -> None:
    if "system1_intelligence" not in state:
        return _original_write(self, project_id, state)
    clean = dict(state)
    clean.pop("system1_intelligence", None)
    return _original_write(self, project_id, clean)


def record_with_intelligence(self: ProjectEngine, project_id: str, event_type: str,
                             payload: dict | None = None, *, actor: str = "user") -> dict:
    event = _original_record(self, project_id, event_type, payload, actor=actor)
    try:
        _system(self).observe_event(self, project_id, event_type, payload or {}, actor)
    except Exception as exc:
        try:
            _system(self).store.add_event(
                run_id=None,
                project_id=project_id,
                event_type="System1ObserverError",
                component="system1_intelligence",
                stage=None,
                status="WARNING",
                payload={"source_event": event_type, "error": f"{type(exc).__name__}: {exc}"},
            )
        except Exception:
            pass
    return event


ProjectEngine.read = read_with_intelligence  # type: ignore[assignment]
ProjectEngine.write = write_without_transient_intelligence  # type: ignore[assignment]
ProjectEngine.record = record_with_intelligence  # type: ignore[assignment]
