from __future__ import annotations

import re
from typing import Any


class IntentSkillRouter:
    """Deterministic preflight router for incompatible operator intent/skill pairs.

    The router does not reinterpret the operator request. It only prevents a strict
    OUTPAINT contract from swallowing semantic edits that cannot legally modify
    existing visible pixels. In that case execution is promoted to HYBRID:
    semantic edit/relight first, missing-region outpaint second.
    """

    version = "1.0.0"
    policy = "outpaint-semantic-conflict-promotes-to-hybrid"

    _REMOVE = re.compile(
        r"(?:\bудал(?:и|ить|ите|яем|ить\s+все)?\b|\bуб(?:ери|ерите|рать)\b|"
        r"\bочист(?:и|ить|ите)\b|\bremove\b|\bdelete\b|\berase\b|\bcleanup\b)",
        re.IGNORECASE,
    )
    _ADD_REPLACE = re.compile(
        r"(?:\bдобав(?:ь|ить|ьте)\b|\bзамен(?:и|ить|ите)\b|\bвстав(?:ь|ить|ьте)\b|"
        r"\bперенес(?:и|ти|ите)\b|\badd\b|\breplace\b|\binsert\b)",
        re.IGNORECASE,
    )
    _RELIGHT = re.compile(
        r"(?:освещ|свет|релайт|погод|дожд|снег|пасмур|солнеч|закат|рассвет|ноч|"
        r"мокр(?:ый|ая|ое|ые)|атмосфер|экспозиц|баланс\s+белого|\brelight\b|"
        r"\bweather\b|\blighting\b|\bsunset\b|\bnight\b|\brain\b)",
        re.IGNORECASE,
    )
    _VISIBLE_REPAIR = re.compile(
        r"(?:залит(?:ые|ый|ая|ое)?\s+(?:темн|черн)|темн(?:ые|ый|ая|ое)\s+(?:мест|участ)|"
        r"черн(?:ые|ый|ая|ое)\s+(?:мест|участ|полос|пятн)|закрашенн|замазанн|"
        r"painted\s+black|dark\s+filled|black\s+area)",
        re.IGNORECASE,
    )

    @classmethod
    def route(cls, requested_mode: str, operator_comments: list[str]) -> dict[str, Any]:
        requested = str(requested_mode or "hybrid").strip().lower()
        text = "\n".join(str(item or "").strip() for item in operator_comments if str(item or "").strip())
        signals: list[str] = []

        if requested == "outpaint":
            if cls._REMOVE.search(text):
                signals.append("semantic_object_removal")
            if cls._ADD_REPLACE.search(text):
                signals.append("semantic_add_or_replace")
            if cls._RELIGHT.search(text):
                signals.append("scene_wide_relight_or_weather")
            if cls._VISIBLE_REPAIR.search(text):
                signals.append("visible_pixel_repair")

        effective = "hybrid" if requested == "outpaint" and signals else requested
        auto_routed = effective != requested
        reason = (
            "OUTPAINT cannot legally change existing visible pixels required by the operator request; "
            "HYBRID is required so semantic edits run first and missing-region reconstruction runs second."
            if auto_routed
            else "Selected skill is compatible with the detected operator intent."
        )
        return {
            "router_version": cls.version,
            "policy": cls.policy,
            "requested_mode": requested,
            "effective_mode": effective,
            "auto_routed": auto_routed,
            "signals": signals,
            "reason": reason,
        }
