from __future__ import annotations

from typing import Any


class TechnicalFailureLocalizer:
    """Layer 1. Deterministic technical diagnosis has precedence over human alignment."""

    version = "technical-localizer-v1"

    def analyze(self, *, observed_failure: str = "", generation: dict[str, Any] | None = None,
                engine_report: dict[str, Any] | None = None, quality: dict[str, Any] | None = None) -> dict[str, Any]:
        generation = generation or {}
        report = engine_report or {}
        quality = quality or {}
        text = " ".join(
            [
                str(observed_failure or ""),
                str(generation.get("error") or ""),
                str(report.get("error") or ""),
                str(report.get("reason") or ""),
                str(report.get("provider_error") or ""),
            ]
        ).lower()

        def found(failure_type: str, component: str, confidence: float, why: str, action: str) -> dict[str, Any]:
            return {
                "status": "ROOT_CAUSE_FOUND",
                "root_cause_found": True,
                "failure_type": failure_type,
                "component": component,
                "confidence": confidence,
                "why": why,
                "repair": {"target": component, "action": action, "auto_execute": False},
                "localizer_version": self.version,
            }

        if any(token in text for token in ("429", "502", "503", "504", "timeout", "service unavailable")):
            return found("PROVIDER_OR_GATEWAY_FAILURE", "provider_transport", 0.96,
                         "Provider/gateway failure is present in runtime evidence.",
                         "Retry the same immutable request through the resilient transport; do not rewrite the prompt.")
        if any(token in text for token in ("openrouter_api_key", "не настроен ключ", "authorization")):
            return found("PROVIDER_CONFIGURATION_FAILURE", "provider_configuration", 0.99,
                         "Generation cannot reach the provider with valid configuration.",
                         "Repair provider configuration before any prompt or visual changes.")
        if any(token in text for token in ("prompt_transport_mismatch", "промпт был изменён")) or report.get("prompt_match") is False:
            return found("PROMPT_TRANSPORT_MISMATCH", "prompt_transport", 0.99,
                         "The compiled prompt changed before provider execution.",
                         "Restore verbatim compiled-prompt propagation across every internal pass.")
        if any(token in text for token in ("geometry_not_approved", "approved_geometry_missing", "утверждённый результат коррекции")):
            return found("APPROVED_GEOMETRY_MISSING", "geometry_gate", 0.99,
                         "The generation stage started without an approved geometry asset.",
                         "Block generation until the exact corrected geometry candidate is approved.")
        if any(token in text for token in ("outpaint_failed_after_edge", "не смогла полностью дорисовать", "edge_refinement_plan_empty")):
            return found("OUTPAINT_RECONSTRUCTION_FAILURE", "outpaint_engine", 0.98,
                         "Automatic outpaint and its controlled local refinement failed to reconstruct all missing pixels.",
                         "Repair the outpaint strategy/quality profile while preserving the full prompt and approved geometry.")
        if bool(report.get("outpaint_placeholder_detected")):
            return found("OUTPAINT_PLACEHOLDER", "outpaint_engine", 0.97,
                         "The generated missing region is still a blank/placeholder area.",
                         "Run controlled edge refinement; do not escalate to human-alignment diagnosis yet.")
        if report.get("fallback_remaining_pixels") not in (None, 0):
            return found("OUTPAINT_INCOMPLETE", "outpaint_engine", 0.97,
                         "Missing pixels remain after outpaint refinement.",
                         "Complete the missing-region reconstruction before evaluating aesthetics.")
        if quality and quality.get("passed") is False:
            return found("TECHNICAL_QUALITY_GATE_FAILURE", "quality_gate", 0.92,
                         "The deterministic quality gate failed.",
                         "Repair the measurable quality failure before subjective alignment analysis.")
        if generation.get("status") == "error" or observed_failure:
            return found("RUNTIME_EXECUTION_FAILURE", "runtime", 0.72,
                         "The run failed technically, but the deterministic localizer has no narrower signature.",
                         "Inspect the run trace and exception evidence before changing generation intent.")

        return {
            "status": "NO_TECHNICAL_ROOT_CAUSE",
            "root_cause_found": False,
            "failure_type": None,
            "component": None,
            "confidence": 0.90,
            "why": "No sufficient technical failure signature was found in the recorded run evidence.",
            "repair": None,
            "localizer_version": self.version,
        }
