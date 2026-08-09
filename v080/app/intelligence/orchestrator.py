from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from .alignment import HumanAlignmentAnalyzer
from .learning import LearningRegistry
from .repair import RepairRouter
from .store import IntelligenceStore
from .technical import TechnicalFailureLocalizer


SERVICE_PREFIX = "__MARINS_"


class System1Intelligence:
    """Native two-layer System №1 intelligence for MarinsFasad.

    Layer 1 technical diagnosis always runs first. Layer 2 human/logical alignment
    is gated and can run only when Layer 1 has no sufficient technical root cause.
    """

    version = "1.0.0"

    def __init__(self, projects_root: Path):
        self.projects_root = Path(projects_root)
        self.store = IntelligenceStore(self.projects_root / "_system1")
        self.technical = TechnicalFailureLocalizer()
        self.alignment = HumanAlignmentAnalyzer()
        self.repair = RepairRouter()
        self.learning = LearningRegistry(self.store)

    @staticmethod
    def _run_id(job_id: str | None) -> str | None:
        return f"RUN-{job_id[:12]}" if job_id else None

    def _project_state(self, engine: Any, project_id: str) -> dict[str, Any]:
        return engine._system1_original_read(project_id)

    def _engine_report(self, project_dir: Path) -> dict[str, Any]:
        path = project_dir / "images" / "stages" / "environment" / "generation.json"
        if not path.is_file():
            return {}
        try:
            return json.loads(path.read_text("utf-8"))
        except Exception:
            return {}

    @staticmethod
    def _component(event_type: str) -> str:
        if "Prompt" in event_type or "Payload" in event_type:
            return "prompt_transport"
        if "Geometry" in event_type:
            return "geometry"
        if "Quality" in event_type:
            return "quality_gate"
        if "Generation" in event_type:
            return "generation_runtime"
        if "Revision" in event_type:
            return "human_feedback"
        if "Approved" in event_type:
            return "approval_gate"
        return "pipeline"

    @staticmethod
    def _status(event_type: str) -> str:
        if "Failed" in event_type or "Error" in event_type:
            return "FAILED"
        if "Completed" in event_type or "Approved" in event_type:
            return "SUCCESS"
        if "Queued" in event_type or "Started" in event_type:
            return "PENDING"
        return "INFO"

    def observe_event(self, engine: Any, project_id: str, event_type: str,
                      payload: dict[str, Any] | None, actor: str) -> None:
        payload = dict(payload or {})
        state = self._project_state(engine, project_id)
        generation = state.get("generation") or {}
        job_id = str(payload.get("job_id") or generation.get("job_id") or "") or None
        run_id = self._run_id(job_id)
        latest = self.store.latest_run(project_id)
        if not run_id and latest:
            run_id = latest.get("run_id")

        if event_type in {"EnvironmentGenerationQueued", "EnvironmentGenerationStarted"} and run_id:
            self.store.upsert_run(
                run_id, project_id, job_id=job_id, stage="environment",
                status="queued" if "Queued" in event_type else "processing",
                summary={"model": generation.get("model"), "actor": actor},
            )

        enriched = dict(payload)
        evidence_ref = None
        prompt_rel = None
        if event_type == "PromptCompiled":
            prompt_rel = payload.get("path")
        elif event_type == "GenerationPayloadPrepared":
            prompt_rel = generation.get("prompt")
        if prompt_rel:
            prompt_path = engine.path(project_id) / str(prompt_rel)
            if prompt_path.is_file():
                text = prompt_path.read_text("utf-8")
                enriched.update({
                    "prompt_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    "prompt_length": len(text),
                    "full_prompt_recorded": True,
                })
                evidence_ref = str(prompt_path.relative_to(engine.path(project_id)))

        project_dir = engine.path(project_id)
        report = self._engine_report(project_dir)
        if event_type in {"EnvironmentGenerationCompleted", "EnvironmentGenerationFailed"} and report:
            enriched["engine_report_summary"] = {
                "generation_mode": report.get("generation_mode"),
                "generation_quality": report.get("generation_quality"),
                "provider_call_count": report.get("provider_call_count"),
                "outpaint_refinement_used": report.get("outpaint_refinement_used"),
                "outpaint_placeholder_detected": report.get("outpaint_placeholder_detected"),
                "fallback_remaining_pixels": report.get("fallback_remaining_pixels"),
            }

        self.store.add_event(
            run_id=run_id, project_id=project_id, event_type=event_type,
            component=self._component(event_type), stage=state.get("active_stage"),
            status=self._status(event_type), payload=enriched, evidence_ref=evidence_ref,
        )

        quality = (state.get("quality") or {}).get("environment_candidate") or {}

        if event_type == "EnvironmentGenerationCompleted" and run_id:
            self.store.upsert_run(run_id, project_id, job_id=job_id, status="completed", summary={
                "candidate": (state.get("assets") or {}).get("environment_candidate"),
                "generation_quality": report.get("generation_quality"),
                "generation_mode": report.get("generation_mode"),
            })
            diagnosis = self.technical.analyze(generation=generation, engine_report=report, quality=quality)
            diagnosis["repair_route"] = self.repair.route(diagnosis)
            self.store.add_diagnosis(run_id=run_id, project_id=project_id, layer="technical", diagnosis=diagnosis)

        if event_type == "EnvironmentGenerationFailed":
            if run_id:
                self.store.upsert_run(run_id, project_id, job_id=job_id, status="failed", summary={"error": generation.get("error")})
            diagnosis = self.technical.analyze(
                observed_failure=str(payload.get("error") or generation.get("error") or "generation failed"),
                generation=generation, engine_report=report, quality=quality,
            )
            diagnosis["repair_route"] = self.repair.route(diagnosis)
            self.store.add_diagnosis(run_id=run_id, project_id=project_id, layer="technical", diagnosis=diagnosis)

        if event_type == "RevisionAdded" and str(payload.get("stage") or "") == "environment":
            raw = str(payload.get("text") or "").strip()
            if not raw or raw.startswith(SERVICE_PREFIX):
                return
            if not ((state.get("assets") or {}).get("environment_candidate") or generation.get("status") in {"review", "approved", "error"}):
                return
            technical_row = self.store.latest_diagnosis(project_id, layer="technical")
            technical = technical_row.get("payload") if technical_row else self.technical.analyze(
                generation=generation, engine_report=report, quality=quality
            )
            feedback_id = f"FB-{uuid4().hex[:12]}"
            if technical.get("root_cause_found") and float(technical.get("confidence") or 0) >= 0.70:
                analysis = {
                    "status": "GATED_BY_LAYER1",
                    "layer2_invoked": False,
                    "why": "Layer 1 already found a sufficient technical root cause. Human/logical alignment is recorded as evidence but cannot override the diagnosis.",
                    "technical_diagnosis": technical,
                    "repair_route": self.repair.route(technical),
                }
                self.store.add_feedback(
                    feedback_id=feedback_id, run_id=run_id, project_id=project_id,
                    raw_feedback=raw, layer1_status="ROOT_CAUSE_FOUND",
                    layer2_invoked=False, analysis=analysis,
                )
            else:
                alignment = self.alignment.analyze(raw, generation=report or generation, quality=quality)
                alignment["repair_route"] = self.repair.route(alignment)
                alignment["precedence"] = "Layer 2 invoked only because Layer 1 had no sufficient technical root cause."
                self.store.add_diagnosis(run_id=run_id, project_id=project_id, layer="alignment", diagnosis=alignment)
                self.store.add_feedback(
                    feedback_id=feedback_id, run_id=run_id, project_id=project_id,
                    raw_feedback=raw, layer1_status="NO_TECHNICAL_ROOT_CAUSE",
                    layer2_invoked=True, analysis=alignment,
                )
                self.learning.observe_explicit_rule(project_id=project_id, raw_feedback=raw)

        if event_type == "EnvironmentApproved":
            latest = self.store.latest_run(project_id)
            approved_run_id = latest.get("run_id") if latest else run_id
            if approved_run_id:
                self.store.upsert_run(approved_run_id, project_id, job_id=job_id, status="approved", summary={
                    "approved_asset": (state.get("assets") or {}).get("environment_candidate"),
                })
            diagnosis_row = self.store.latest_diagnosis(project_id)
            diagnosis = diagnosis_row.get("payload") if diagnosis_row else None
            self.learning.register_approval(
                project_id=project_id, run_id=approved_run_id, state=state, diagnosis=diagnosis
            )

    def summary(self, project_id: str) -> dict[str, Any]:
        result = self.store.summary(project_id)
        result["precedence"] = {
            "layer1": "technical diagnosis is authoritative when root_cause_found and confidence >= 0.70",
            "layer2": "human/logical alignment runs only after Layer 1 is clear",
            "learning": "approval creates regression evidence; permanent rules are never auto-promoted",
        }
        result["recent_trace"] = self.store.recent_events(project_id, 12)
        return result
