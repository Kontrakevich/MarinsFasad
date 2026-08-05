from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageOps

from . import ai_engine as _engine_module
from .system_prompts import ENVIRONMENT_SYSTEM_PROMPT, PROMPT_CONTRACT_VERSION


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

    @staticmethod
    def _file_sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _system_prompt_sha256() -> str:
        return hashlib.sha256(ENVIRONMENT_SYSTEM_PROMPT.encode("utf-8")).hexdigest()

    def _build_payload(
        self,
        *,
        prompt: str,
        geometry_image: Path,
        outpaint_mask: Path,
        provider_size: tuple[int, int],
    ) -> dict:
        compiled_prompt = (
            f"SYSTEM PROMPT — {PROMPT_CONTRACT_VERSION}\n"
            f"{ENVIRONMENT_SYSTEM_PROMPT}\n\n"
            "PROJECT EXECUTION PROMPT\n"
            f"{prompt.strip()}"
        )
        return super()._build_payload(
            prompt=compiled_prompt,
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
        geometry_image = Path(geometry_image)
        outpaint_mask = Path(outpaint_mask)
        if not geometry_image.is_file():
            raise AIEngineError(
                "Approved geometry file is missing; provider call cancelled",
                details={"provider_call_made": False, "credits_spent": False},
            )
        if not outpaint_mask.is_file():
            raise AIEngineError(
                "Approved outpaint mask is missing; provider call cancelled",
                details={"provider_call_made": False, "credits_spent": False},
            )

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
        prepared.update(
            {
                "required_editable_pixels": required_pixels,
                "mask_policy": "white-generate-black-preserve",
                "source_contract": "corrected-approved-geometry",
                "approved_geometry_sha256": self._file_sha256(geometry_image),
                "approved_mask_sha256": self._file_sha256(outpaint_mask),
                "system_prompt_contract": PROMPT_CONTRACT_VERSION,
                "system_prompt_sha256": self._system_prompt_sha256(),
                "system_prompt_in_request": True,
            }
        )
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
                "system_prompt_contract": PROMPT_CONTRACT_VERSION,
                "approved_geometry_sha256": prepared.get("approved_geometry_sha256"),
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
