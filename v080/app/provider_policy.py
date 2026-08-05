from __future__ import annotations

import hashlib
import json
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

    @staticmethod
    def _project_root_from_geometry(geometry_image: Path) -> Path | None:
        resolved = geometry_image.resolve()
        for parent in resolved.parents:
            if (parent / "project.json").is_file():
                return parent
        return None

    def _approval_contract(
        self,
        geometry_image: Path,
        outpaint_mask: Path,
    ) -> dict[str, Any]:
        project_root = self._project_root_from_geometry(geometry_image)
        if project_root is None:
            # Unit tests and standalone engine calls may use temporary files.
            return {
                "approval_verified": False,
                "approval_source": "standalone-engine-call",
            }

        try:
            state = json.loads((project_root / "project.json").read_text("utf-8"))
        except Exception as exc:
            raise AIEngineError(
                "Generation cancelled before provider call: project approval state is unreadable",
                details={
                    "provider_call_made": False,
                    "credits_spent": False,
                    "reason": "approval_state_unreadable",
                    "exception": type(exc).__name__,
                },
            ) from exc

        geometry_status = (state.get("geometry") or {}).get("status")
        pipeline_status = (state.get("pipeline") or {}).get("geometry")
        assets = state.get("assets") or {}
        expected_geometry_rel = assets.get("geometry_candidate")
        expected_mask_rel = assets.get("geometry_outpaint_mask")
        expected_geometry = (
            (project_root / expected_geometry_rel).resolve()
            if expected_geometry_rel
            else None
        )
        expected_mask = (
            (project_root / expected_mask_rel).resolve()
            if expected_mask_rel
            else None
        )

        verified = (
            geometry_status == "approved"
            and pipeline_status == "approved"
            and expected_geometry == geometry_image.resolve()
            and expected_mask == outpaint_mask.resolve()
        )
        if not verified:
            raise AIEngineError(
                "Generation cancelled before provider call: corrected geometry and mask are not the exact approved project assets",
                details={
                    "provider_call_made": False,
                    "credits_spent": False,
                    "reason": "geometry_not_approved",
                    "geometry_status": geometry_status,
                    "pipeline_status": pipeline_status,
                    "expected_geometry": str(expected_geometry) if expected_geometry else None,
                    "received_geometry": str(geometry_image.resolve()),
                    "expected_mask": str(expected_mask) if expected_mask else None,
                    "received_mask": str(outpaint_mask.resolve()),
                },
            )

        return {
            "approval_verified": True,
            "approval_source": "project.json",
            "project_id": state.get("id"),
            "geometry_status": geometry_status,
            "pipeline_status": pipeline_status,
        }

    def _build_payload(
        self,
        *,
        prompt: str,
        geometry_image: Path,
        outpaint_mask: Path,
        provider_size: tuple[int, int],
    ) -> dict:
        project_prompt = prompt.strip()
        if ENVIRONMENT_SYSTEM_PROMPT in project_prompt:
            compiled_prompt = project_prompt
        else:
            compiled_prompt = (
                f"SYSTEM PROMPT — {PROMPT_CONTRACT_VERSION}\n"
                f"{ENVIRONMENT_SYSTEM_PROMPT}\n\n"
                "PROJECT EXECUTION PROMPT\n"
                f"{project_prompt}"
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

        approval = self._approval_contract(geometry_image, outpaint_mask)
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
                    **approval,
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
        prepared.update(approval)
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
