from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageOps

from . import ai_engine as _engine_module


_BaseOpenRouterImageEngine = _engine_module.OpenRouterImageEngine
AIEngineError = _engine_module.AIEngineError


class OpenRouterImageEngine(_BaseOpenRouterImageEngine):
    """Marins provider policy for safe, meaningful image generation."""

    transport_engine_version = "2.4.0"
    minimum_editable_pixels = 64
    minimum_editable_ratio = 0.00001
    minimum_generated_change_ratio = 0.01

    @staticmethod
    def _extract_supported_sizes(text: str) -> list[tuple[int, int]]:
        source = text or ""
        match = re.search(
            r"supported\s+sizes\s+are\s+(.+)",
            source,
            flags=re.IGNORECASE,
        )
        scope = match.group(1) if match else source
        sizes = _BaseOpenRouterImageEngine._extract_supported_sizes(scope)
        valid_defaults = [
            size
            for size in sizes
            if size in OpenRouterImageEngine.default_supported_output_sizes
        ]
        return valid_defaults or sizes

    @staticmethod
    def _mask_statistics(path: Path) -> dict[str, Any]:
        with Image.open(path) as source:
            mask = ImageOps.exif_transpose(source).convert("L")
            histogram = mask.histogram()
            editable_pixels = int(sum(histogram[128:]))
            total_pixels = int(mask.width * mask.height)
        return {
            "editable_pixels": editable_pixels,
            "total_pixels": total_pixels,
            "editable_ratio": editable_pixels / float(max(1, total_pixels)),
        }

    def _build_payload(
        self,
        *,
        prompt: str,
        geometry_image: Path,
        outpaint_mask: Path,
        provider_size: tuple[int, int],
    ) -> dict:
        execution_contract = (
            "\n\nSTRICT REFERENCE CONTRACT:\n"
            "Reference image 1 is the approved corrected architecture. Preserve every "
            "visible opaque architectural pixel, facade proportion, window, floor, edge, "
            "camera direction and perspective.\n"
            "Reference image 2 is a binary edit map. WHITE pixels are mandatory generation "
            "areas. BLACK pixels are protected architecture. Transparent pixels in reference "
            "image 1 are also mandatory generation areas.\n"
            "Generate continuous photorealistic surroundings in every white or transparent "
            "area. Do not return the input image unchanged. Do not leave black, transparent, "
            "blank, checkerboard or unfilled pixels."
        )
        return super()._build_payload(
            prompt=prompt + execution_contract,
            geometry_image=geometry_image,
            outpaint_mask=outpaint_mask,
            provider_size=provider_size,
        )

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
        mask_stats = self._mask_statistics(outpaint_mask)
        required_pixels = max(
            self.minimum_editable_pixels,
            int(mask_stats["total_pixels"] * self.minimum_editable_ratio),
        )
        if mask_stats["editable_pixels"] < required_pixels:
            raise AIEngineError(
                "Generation cancelled before provider call: the outpaint mask is empty. "
                "Reapply Perspective Grid so transparent areas are visible around the corrected image.",
                details={
                    **mask_stats,
                    "required_editable_pixels": required_pixels,
                    "provider_call_made": False,
                    "credits_spent": False,
                    "reason": "empty_outpaint_mask",
                },
            )

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
        prepared.update(mask_stats)
        prepared["required_editable_pixels"] = required_pixels
        prepared["mask_policy"] = "white-generate-black-preserve"
        return prepared

    def _promote_provider_output(
        self,
        *,
        provider_output: Path,
        geometry_image: Path,
        outpaint_mask: Path,
        prepared: dict,
        output_dir: Path,
        width: int,
        height: int,
    ) -> dict:
        result = super()._promote_provider_output(
            provider_output=provider_output,
            geometry_image=geometry_image,
            outpaint_mask=outpaint_mask,
            prepared=prepared,
            output_dir=output_dir,
            width=width,
            height=height,
        )

        with Image.open(result["candidate"]) as candidate_source:
            candidate = ImageOps.exif_transpose(candidate_source).convert("RGB")
        with Image.open(geometry_image) as geometry_source:
            geometry = ImageOps.exif_transpose(geometry_source).convert("RGB")
        with Image.open(outpaint_mask) as mask_source:
            edit_mask = ImageOps.exif_transpose(mask_source).convert("L").point(
                lambda value: 255 if value >= 128 else 0,
                mode="L",
            )

        editable_pixels = int(sum(edit_mask.histogram()[128:]))
        difference = ImageChops.difference(candidate, geometry).convert("L")
        changed = difference.point(
            lambda value: 255 if value >= 6 else 0,
            mode="L",
        )
        changed_in_edit_area = ImageChops.multiply(changed, edit_mask)
        changed_pixels = int(sum(changed_in_edit_area.histogram()[128:]))
        change_ratio = changed_pixels / float(max(1, editable_pixels))

        result.update(
            {
                "editable_pixels": editable_pixels,
                "generated_changed_pixels": changed_pixels,
                "generated_change_ratio": round(change_ratio, 6),
                "meaningful_generation": change_ratio >= self.minimum_generated_change_ratio,
            }
        )

        if change_ratio < self.minimum_generated_change_ratio:
            raise AIEngineError(
                "Provider returned no meaningful visual change in the outpaint area. "
                "The result was retained for diagnostics but was not promoted as a successful candidate.",
                details={
                    "transport": prepared,
                    "provider_output": str(provider_output),
                    "candidate": result["candidate"],
                    "editable_pixels": editable_pixels,
                    "generated_changed_pixels": changed_pixels,
                    "generated_change_ratio": round(change_ratio, 6),
                    "reason": "provider_no_op",
                },
            )

        return result


_engine_module.OpenRouterImageEngine = OpenRouterImageEngine
