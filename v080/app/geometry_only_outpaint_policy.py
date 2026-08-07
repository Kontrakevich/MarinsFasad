from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

from . import ai_engine as _engine_module


_PreviousOpenRouterImageEngine = _engine_module.OpenRouterImageEngine
AIEngineError = _engine_module.AIEngineError


class OpenRouterImageEngine(_PreviousOpenRouterImageEngine):
    """Final contract: approved geometry only, automatic outpaint.

    The user approves exactly one visual asset: the corrected geometry image.
    Missing regions are derived from its alpha channel. Internal outpaint crops
    produced from that approved image are allowed to reach Nano Banana, but they
    are never treated as independent project assets or user inputs.
    """

    transport_engine_version = "2.9.1"
    environment_input_policy = "approved-geometry-only"
    outpaint_detection_policy = "automatic-from-approved-geometry-transparency"
    user_mask_required = False
    internal_outpaint_tiles_allowed = True

    @staticmethod
    def _is_internal_outpaint_tile(project_root: Path, geometry_image: Path) -> bool:
        try:
            relative = geometry_image.resolve().relative_to(project_root.resolve())
        except ValueError:
            return False
        parts = tuple(part.lower() for part in relative.parts)
        return (
            "outpaint-tiles" in parts
            and relative.name.lower() in {"tile-base.png", "geometry-input.webp"}
        )

    def _approval_contract(
        self,
        geometry_image: Path,
        outpaint_mask: Path,
    ) -> dict[str, Any]:
        """Verify the approved geometry or an internal crop derived from it.

        ``outpaint_mask`` is only a private processing plan required by legacy
        method signatures. It is ignored for project approval and is never a
        user-facing or approved project asset.
        """
        geometry_image = Path(geometry_image)
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
        approved = geometry_status == "approved" and pipeline_status == "approved"
        exact_geometry = expected_geometry == geometry_image.resolve()
        internal_tile = approved and self._is_internal_outpaint_tile(
            project_root,
            geometry_image,
        )

        if not approved or not (exact_geometry or internal_tile):
            raise AIEngineError(
                "Для генерации нужен утверждённый результат коррекции геометрии.",
                details={
                    "provider_call_made": False,
                    "credits_spent": False,
                    "reason": "geometry_not_approved",
                    "geometry_status": geometry_status,
                    "pipeline_status": pipeline_status,
                    "expected_geometry": str(expected_geometry) if expected_geometry else None,
                    "received_geometry": str(geometry_image.resolve()),
                    "internal_outpaint_tile": internal_tile,
                },
            )

        return {
            "approval_verified": True,
            "approval_source": (
                "internal-derived-outpaint-tile" if internal_tile else "project.json"
            ),
            "project_id": state.get("id"),
            "geometry_status": geometry_status,
            "pipeline_status": pipeline_status,
            "environment_input_policy": self.environment_input_policy,
            "internal_outpaint_tile": internal_tile,
        }

    @staticmethod
    def _effective_edit_mask(
        geometry_image: Path,
        approved_mask: Path,
        destination: Path,
    ) -> Path:
        """Derive the private compositing plan only from image transparency."""
        with Image.open(geometry_image) as source:
            geometry = ImageOps.exif_transpose(source).convert("RGBA")
        automatic = geometry.getchannel("A").point(
            lambda value: 255 if value < 250 else 0,
            mode="L",
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        automatic.save(destination, format="PNG", optimize=False)
        return destination

    def _build_payload(
        self,
        *,
        prompt: str,
        geometry_image: Path,
        outpaint_mask: Path,
        provider_size: tuple[int, int],
    ) -> dict:
        """Nano Banana receives exactly one visual reference.

        The private outpaint plan is intentionally not transmitted. Missing
        pixels are already encoded inside the geometry reference by the previous
        transport layer as an opaque service pattern.
        """
        provider_prompt, _ = self._provider_prompt(prompt)
        return {
            "model": self.required_model,
            "prompt": provider_prompt,
            "n": 1,
            "size": f"{provider_size[0]}x{provider_size[1]}",
            "quality": "high",
            "output_format": "png",
            "background": "opaque",
            "input_references": [
                {
                    "type": "image_url",
                    "image_url": {"url": self._data_url(geometry_image)},
                },
            ],
        }

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
                "internal_outpaint_tiles_allowed": self.internal_outpaint_tiles_allowed,
            }
        )
        return prepared

    def _tile_prompt(self, original_prompt: str, tile_index: int) -> str:
        return (
            "OUTPAINT TILE RECONSTRUCTION — REQUIRED\n"
            f"Tile {tile_index} is an enlarged crop automatically derived from the approved corrected photograph.\n"
            "The supplied image contains a magenta/cyan service pattern only where visual information is missing.\n"
            "Replace every service-pattern pixel with real photorealistic scene content. Continue the adjacent sky, facade, "
            "building edges, pavement, asphalt, ground lines, shadows, wires and perspective without seams.\n"
            "Preserve every existing photographic pixel around the missing area.\n"
            "Do not return white, black, transparent, checkerboard or flat-colour fills.\n"
            "The complete project instruction remains authoritative:\n\n"
            f"{original_prompt}"
        )


_engine_module.OpenRouterImageEngine = OpenRouterImageEngine
