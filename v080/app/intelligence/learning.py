from __future__ import annotations

import hashlib
import re
from typing import Any
from uuid import uuid4

from .store import IntelligenceStore, utcnow


class LearningRegistry:
    version = "learning-registry-v1"

    def __init__(self, store: IntelligenceStore):
        self.store = store

    def register_approval(self, *, project_id: str, run_id: str | None, state: dict[str, Any],
                          diagnosis: dict[str, Any] | None) -> dict[str, Any]:
        assets = state.get("assets") or {}
        generation = state.get("generation") or {}
        quality = (state.get("quality") or {}).get("environment_candidate") or {}
        case_id = f"REG-{uuid4().hex[:12]}"
        case = {
            "case_id": case_id,
            "created_at": utcnow(),
            "project_id": project_id,
            "run_id": run_id,
            "stage": "environment",
            "approved_asset": assets.get("environment_candidate"),
            "approved_geometry": assets.get("geometry_candidate"),
            "prompt": generation.get("prompt"),
            "quality": quality,
            "diagnosis_before_approval": diagnosis,
            "expected_invariants": [
                "approved corrected camera and architecture remain geometrically stable",
                "full compiled prompt survives every internal generation pass",
                "outpaint contains no blank/placeholder missing regions",
                "existing visible pixels are preserved in strict OUTPAINT mode",
            ],
            "status": "APPROVED_REFERENCE",
        }
        self.store.add_regression(
            case_id=case_id, project_id=project_id, run_id=run_id,
            status="APPROVED_REFERENCE", case=case,
        )
        return case

    def observe_explicit_rule(self, *, project_id: str, raw_feedback: str) -> dict[str, Any] | None:
        text = str(raw_feedback or "").strip()
        low = text.lower()
        explicit = any(token in low for token in ("всегда", "никогда", "правило", "для marins", "для маринс"))
        if not explicit:
            return None
        normalized = re.sub(r"\s+", " ", low).strip()
        rule_key = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
        preference_id = f"PREF-{project_id}-{rule_key}"
        value = {
            "rule": text,
            "source": "explicit-user-feedback",
            "promotion_policy": "project-candidate-only; brand/system require explicit later confirmation",
        }
        self.store.add_preference_evidence(
            preference_id=preference_id,
            scope="PROJECT",
            project_id=project_id,
            rule_key=rule_key,
            status="CANDIDATE",
            value=value,
        )
        return {"preference_id": preference_id, "scope": "PROJECT", "status": "CANDIDATE", **value}
