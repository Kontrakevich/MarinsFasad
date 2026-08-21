from __future__ import annotations

from typing import Any


class RepairRouter:
    version = "repair-router-v1"

    ROUTES = {
        "provider_transport": "transport_retry",
        "provider_configuration": "configuration_repair",
        "prompt_transport": "prompt_transport_repair",
        "geometry_gate": "geometry_gate_repair",
        "outpaint_engine": "outpaint_strategy_repair",
        "quality_gate": "quality_profile_repair",
        "runtime": "runtime_diagnostic_repair",
        "quality_outpaint": "quality_profile_repair",
        "prompt_compiler": "prompt_contract_repair",
        "geometry_contract": "geometry_contract_repair",
        "image_edit": "image_edit_repair",
        "relight": "relight_repair",
        "style_direction": "style_direction_repair",
        "brand_rules": "brand_rule_retrieval",
        "photorealism": "photorealism_repair",
        "operator_intent": "operator_intent_repair",
        "learning_registry": "learning_evidence_only",
    }

    def route(self, diagnosis: dict[str, Any] | None) -> dict[str, Any]:
        diagnosis = diagnosis or {}
        component = str(diagnosis.get("component") or "runtime")
        return {
            "router_version": self.version,
            "route": self.ROUTES.get(component, "manual_review"),
            "target": component,
            "action": (diagnosis.get("repair") or {}).get("action"),
            "automatic_execution": False,
            "policy": "diagnose-first-controlled-retry-no-self-modifying-code",
        }
