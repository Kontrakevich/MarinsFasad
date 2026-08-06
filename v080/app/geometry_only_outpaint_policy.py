from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

from . import ai_engine as _engine_module


_PreviousOpenRouterImageEngine = _engine_module.OpenRouterImageEngine
AIEngineError = _engine_module.AIEngineError


class OpenRouterImageEngine(_PreviousOpenRouterImageEngine):
    """Final user contract: one approved geometry image, automatic outpaint."""

    transport_engine_version = "2.9.0"
    environment_input_policy = "approved-geometry-only"
    outpaint_detection_policy = "automatic-from-approved-geometry-transparency"
    user_mask_required = False

    def _approval_contract(
        self,
        geometry_image: Path,
        outpaint_mask: Path,
    ) -> dict[str, Any]:
        """Verify only the approved geometry asset.

        The second path is an internal automatically generated outpaint plan. It
        is not a project asset, is never approved by the user and does not take
        part in the approval decision.
        """
        project_root = self._project_root_from_geometry(geometry_image)
        if project_root is None:
            return {
                "approval_verified": False,
                "approval_source": "standalone-engine-call",
                "environment_input_policy": self.environment_input_policy,
            }

        try:
            state = json.loads((project_root / "project.json").read_text("utf-8"))
        except Exception as exc:
            raise AIEngineError(
                "Не удалось прочитать состояние утверждения проекта. Запрос к генератору не отправлен.",
                details={
                    "provider_call_made": False,
                    "credits_spent": False,
                    "reason": "approval_state_unreadable",
                    "exception": type(exc).__name__,
                },
            ) from exc

        geometry_status = (state.get("geometry") or {}).get("status")
        pipeline_status = (state.get("pipeline") or {}).get("geometry")
        expected_rel = (state.get("assets") or {}).get("geometry_candidate")
        expected_geometry = (
            (project_root / expected_rel).resolve()
            if expected_rel
            else None
        )
        verified = (
            geometry_status == "approved"
            and pipeline_status == "approved"
            and expected_geometry == geometry_image.resolve()
        )
        if not verified:
            raise AIEngineError(
                "Для генерации нужен точный утверждённый результат коррекции геометрии.",
                details={
                    "provider_call_made": False,
                    "credits_spent": False,
                    "reason": "geometry_not_approved",
                    "geometry_status": geometry_status,
                    "pipeline_status": pipeline_status,
                    "expected_geometry": str(expected_geometry) if expected_geometry else None,
                    "received_geometry": str(geometry_image.resolve()),
                },
            )

        return {
            "approval_verified": True,
            "approval_source": "project.json",
            "project_id": state.get("id"),
            "geometry_status": geometry_status,
            "pipeline_status": pipeline_status,
            "environment_input_policy": self.environment_input_policy,
        }

    @staticmethod
    def _effective_edit_mask(
        geometry_image: Path,
        approved_mask: Path,
        destination: Path,
    ) -> Path:
        """Derive the private compositing plan only from geometry transparency."""
        with Image.open(geometry_image) as source:
            geometry = ImageOps.exif_transpose(source).convert("RGBA")
        automatic = geometry.getchannel("A").point(
            lambda value: 255 if value < 250 else 0,
            mode="L",
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        automatic.save(destination, format="PNG", optimize=False)
        return destination

    def prepare_environment_inputs(
        self,
        *,
        prompt: str,
        geometry_image: Path,
        outpaint_mask: Path,
        output_dir: Path,
        width: int,
        height: int,
        forced_max_request_bytes: int | None = None,
        forced_target_request_bytes: int | None = None,
        supported_sizes=None,
    ) -> dict:
        prepared = super().prepare_environment_inputs(
            prompt=prompt,
            geometry_image=geometry_image,
            outpaint_mask=outpaint_mask,
            output_dir=output_dir,
            width=width,
            height=height,
            forced_max_request_bytes=forced_max_request_bytes,
            forced_target_request_bytes=forced_target_request_bytes,
            supported_sizes=supported_sizes,
        )
        prepared.update(
            {
                "environment_input_policy": self.environment_input_policy,
                "outpaint_detection": self.outpaint_detection_policy,
                "user_outpaint_file_required": False,
                "provider_reference_count": 1,
                "input_reference_count": 1,
                "generation_mode": "automatic-outpaint-and-selective-edit",
            }
        )
        return prepared

    def _tile_prompt(self, original_prompt: str, tile_index: int) -> str:
        return (
            "OUTPAINT TILE RECONSTRUCTION — REQUIRED\n"
            f"Tile {tile_index} is an enlarged crop from the approved corrected photograph.\n"
            "The supplied image contains a magenta/cyan service pattern only where visual information is missing.\n"
            "Replace every service-pattern pixel with real photorealistic scene content. Continue the adjacent sky, facade, "
            "building edges, pavement, asphalt, ground lines, shadows, wires and perspective without seams.\n"
            "Preserve every existing photographic pixel around the missing area.\n"
            "Do not return white, black, transparent, checkerboard or flat-colour fills.\n"
            "The complete project instruction remains authoritative:\n\n"
            f"{original_prompt}"
        )


_engine_module.OpenRouterImageEngine = OpenRouterImageEngine
