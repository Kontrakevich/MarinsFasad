from __future__ import annotations

import json
from pathlib import Path

from . import ai_engine as _engine_module
from .hybrid_engine import OpenRouterImageEngine as _HybridOpenRouterImageEngine


class OpenRouterImageEngine(_HybridOpenRouterImageEngine):
    """Canonical skill-aware runtime.

    OUTPAINT is pixel-preserving outside missing regions.
    RELIGHT is a full-frame photometric transformation with geometry locked.
    IMAGE EDIT keeps requested semantic changes and never restores source pixels
    over them. HYBRID performs semantic edit/relight first and outpaint second.
    """

    transport_engine_version = "3.3.0"
    available_generation_modes = ("hybrid", "relight", "edit", "outpaint")
    skill_contract_version = "outpaint-relight-edit-hybrid-v1"

    def _promote_provider_output(self, **kwargs) -> dict:
        result = super()._promote_provider_output(**kwargs)
        mode = self._normalize_generation_mode(
            result.get("requested_generation_mode") or result.get("generation_mode")
        )
        result["active_skill"] = mode
        result["skill_contract_version"] = self.skill_contract_version
        result["pixel_preservation_scope"] = (
            "outside-missing-regions"
            if mode == "outpaint"
            else "none-photometric-full-frame-allowed"
            if mode == "relight"
            else "do-not-restore-over-requested-edits"
        )
        result["geometry_preservation_required"] = True
        result["global_relight_enabled"] = mode in {"relight", "hybrid"}
        result["strong_image_edit_enabled"] = mode in {"hybrid", "relight", "edit"}
        return result

    def generate_environment(self, **kwargs) -> dict:
        # The runtime owns the generation directory lifecycle. Create it before
        # entering the hybrid engine so the one-pass path can always persist
        # generation.json even when provider/test doubles do not create folders.
        output_dir = Path(kwargs["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)

        result = super().generate_environment(**kwargs)
        mode = self._normalize_generation_mode(
            result.get("requested_generation_mode") or result.get("generation_mode")
        )
        result.update(
            {
                "active_skill": mode,
                "skill_contract_version": self.skill_contract_version,
                "available_generation_modes": list(self.available_generation_modes),
                "global_relight_enabled": mode in {"relight", "hybrid"},
                "strong_image_edit_enabled": mode in {"hybrid", "relight", "edit"},
                "pixel_preservation_scope": (
                    "outside-missing-regions"
                    if mode == "outpaint"
                    else "none-photometric-full-frame-allowed"
                    if mode == "relight"
                    else "do-not-restore-over-requested-edits"
                ),
            }
        )
        (output_dir / "generation.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            "utf-8",
        )
        return result


_engine_module.OpenRouterImageEngine = OpenRouterImageEngine
