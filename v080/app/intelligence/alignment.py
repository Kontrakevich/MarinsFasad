from __future__ import annotations

from typing import Any


class HumanAlignmentAnalyzer:
    """Layer 2. Runs only after Layer 1 is clear."""

    version = "human-alignment-v1"

    def analyze(self, raw_feedback: str, *, generation: dict[str, Any] | None = None,
                quality: dict[str, Any] | None = None) -> dict[str, Any]:
        raw = str(raw_feedback or "").strip()
        low = raw.lower()
        generation = generation or {}
        quality = quality or {}

        mappings = [
            (("заплат", "стык", "шов", "кусок", "низкое качество", "мыло", "размыт"),
             "QUALITY_EXPECTATION_GAP", "quality_outpaint", "Increase context/detail consistency and seam continuity without changing valid source pixels."),
            (("не учел пром", "не учитывает пром", "только первую", "игнорирует", "не выполнил весь"),
             "CONSTRAINT_DILUTION", "prompt_compiler", "Propagate the complete compiled operator prompt through every internal generation pass."),
            (("геометр", "ракурс", "перспектив", "форма здания", "исказ"),
             "CONSTRAINT_DILUTION", "geometry_contract", "Restore immutable camera/geometry constraints and verify them after generation."),
            (("столб", "провод", "кабель", "не убрал", "остал"),
             "INTENT_MISINTERPRETATION", "image_edit", "Execute the requested semantic removals strongly and reconstruct the physical background."),
            (("погод", "освещ", "свет", "вечер", "дожд", "атмосфер"),
             "INTENT_MISINTERPRETATION", "relight", "Apply the requested scene-wide photometric change coherently while preserving geometry."),
            (("дубай", "слишком наряд", "вычур", "дорого-богато", "перебор"),
             "OVERDESIGN", "style_direction", "Reduce decorative spectacle and return to restrained architectural premium character."),
            (("не marins", "не маринс", "бренд", "off-brand"),
             "BRAND_MISALIGNMENT", "brand_rules", "Reapply confirmed MARINS visual rules before generation."),
            (("стиль", "футур", "не тот образ"),
             "STYLE_DRIFT", "style_direction", "Return visual direction to the explicit brief/reference intent."),
            (("нереал", "искусствен", "рендер", "пластик"),
             "QUALITY_EXPECTATION_GAP", "photorealism", "Increase physical material/light realism and reject synthetic-looking results."),
        ]

        failure_type = "INTENT_MISINTERPRETATION"
        target = "operator_intent"
        action = "Apply the narrowest justified visual delta from the user's feedback."
        for terms, failure, route, repair in mappings:
            if any(term in low for term in terms):
                failure_type, target, action = failure, route, repair
                break

        positive = any(token in low for token in ("отлич", "то что надо", "утверж", "нравится", "хорошо получилось"))
        if positive:
            failure_type = "POSITIVE_ALIGNMENT"
            target = "learning_registry"
            action = "Store as run-level positive evidence; do not promote to permanent rules without repeated confirmation."

        return {
            "status": "DIAGNOSED",
            "layer2_invoked": True,
            "feedback_type": "APPROVAL" if positive else "CORRECTION",
            "intent_hypothesis": raw,
            "failure_type": failure_type,
            "component": target,
            "confidence": 0.68,
            "why": "Interpretation is based on explicit human feedback after Layer 1 found no sufficient technical root cause.",
            "desired_change": action,
            "repair": {"target": target, "action": action, "auto_execute": False},
            "needs_user_validation": not positive,
            "analyzer_version": self.version,
            "quality_context": quality,
            "generation_context": {
                "status": generation.get("status"),
                "mode": generation.get("generation_mode"),
                "quality": generation.get("generation_quality"),
            },
        }
