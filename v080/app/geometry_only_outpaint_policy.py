from __future__ import annotations

from pathlib import Path

from . import ai_engine as _engine_module


_PreviousOpenRouterImageEngine = _engine_module.OpenRouterImageEngine


class OpenRouterImageEngine(_PreviousOpenRouterImageEngine):
    """Final user contract: one approved geometry image, automatic outpaint."""

    transport_engine_version = "2.9.0"
    environment_input_policy = "approved-geometry-only"
    outpaint_detection_policy = "automatic-from-approved-geometry-transparency"
    user_mask_required = False

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
