from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageChops, ImageOps

from . import ai_engine as _engine_module
from .hybrid_engine import AIEngineError, OpenRouterImageEngine as _HybridOpenRouterImageEngine
from .prompt_engine import (
    GENERATION_MODE_MARKER,
    GENERATION_QUALITY_MARKER,
    VALID_GENERATION_QUALITIES,
)


class OpenRouterImageEngine(_HybridOpenRouterImageEngine):
    """Canonical skill-aware runtime with quality-controlled outpaint.

    OUTPAINT preserves every valid source pixel. HIGH and MAX quality also run
    context-rich local edge refinement even when the first full-frame outpaint is
    technically valid, because a non-blank result can still look like a low-detail
    patch. Local results are tone-harmonized and feathered only *inside* missing
    regions; valid source pixels are never blended away.

    RELIGHT is a full-frame photometric transformation with geometry locked.
    IMAGE EDIT keeps requested semantic changes. HYBRID performs semantic
    edit/relight first and outpaint/refinement second.
    """

    transport_engine_version = "3.4.0"
    available_generation_modes = ("hybrid", "relight", "edit", "outpaint")
    available_generation_qualities = ("draft", "standard", "high", "max")
    default_generation_quality = "high"
    skill_contract_version = "outpaint-relight-edit-hybrid-quality-v2"
    outpaint_fallback_mode = "quality-aware-edge-refine"
    outpaint_initial_qc_blocking = False

    QUALITY_PROFILES: dict[str, dict[str, Any]] = {
        "draft": {
            "padding_ratio": 0.10,
            "padding_min": 72,
            "padding_max": 160,
            "feather_px": 12,
            "max_attempts": 1,
            "min_attempts": 1,
            "tone_match_strength": 0.35,
            "force_edge_refine": False,
            "quality_threshold": 34.0,
        },
        "standard": {
            "padding_ratio": 0.16,
            "padding_min": 112,
            "padding_max": 256,
            "feather_px": 22,
            "max_attempts": 2,
            "min_attempts": 1,
            "tone_match_strength": 0.50,
            "force_edge_refine": False,
            "quality_threshold": 40.0,
        },
        "high": {
            "padding_ratio": 0.24,
            "padding_min": 192,
            "padding_max": 448,
            "feather_px": 34,
            "max_attempts": 2,
            "min_attempts": 1,
            "tone_match_strength": 0.72,
            "force_edge_refine": True,
            "quality_threshold": 48.0,
        },
        "max": {
            "padding_ratio": 0.34,
            "padding_min": 256,
            "padding_max": 640,
            "feather_px": 48,
            "max_attempts": 3,
            "min_attempts": 2,
            "tone_match_strength": 0.88,
            "force_edge_refine": True,
            "quality_threshold": 56.0,
        },
    }
    outpaint_fallback_attempts_per_edge = 3

    @classmethod
    def _normalize_generation_quality(cls, value: str | None) -> str:
        quality = str(value or "").strip().lower()
        return quality if quality in VALID_GENERATION_QUALITIES else cls.default_generation_quality

    @classmethod
    def _quality_from_prompt(cls, prompt: str) -> str:
        text = str(prompt or "")
        marker = f"{GENERATION_QUALITY_MARKER}\n"
        index = text.find(marker)
        if index >= 0:
            remainder = text[index + len(marker):]
            first_line = remainder.splitlines()[0].strip().lower() if remainder else ""
            if first_line in VALID_GENERATION_QUALITIES:
                return first_line
        for quality in cls.available_generation_qualities:
            if f"Generation quality: {quality.upper()}" in text:
                return quality
        return cls.default_generation_quality

    @classmethod
    def _quality_profile(cls, quality: str | None) -> dict[str, Any]:
        return dict(cls.QUALITY_PROFILES[cls._normalize_generation_quality(quality)])

    @staticmethod
    def _pixel_count_local(mask: Image.Image) -> int:
        binary = mask.convert("L").point(lambda value: 255 if value >= 128 else 0, mode="L")
        return int(sum(binary.histogram()[128:]))

    @staticmethod
    def _outpaint_placeholder_stats(candidate: Image.Image, plan: Image.Image) -> dict[str, Any]:
        """Detect large contiguous blank fills without rejecting valid bright sky."""

        plan_array = np.asarray(
            plan.convert("L").point(lambda value: 255 if value >= 128 else 0, mode="L"),
            dtype=np.uint8,
        )
        editable = plan_array > 0
        editable_pixels = int(np.count_nonzero(editable))
        if editable_pixels == 0:
            return {
                "outpaint_checked_pixels": 0,
                "solid_white_ratio": 0.0,
                "solid_black_ratio": 0.0,
                "largest_placeholder_component_ratio": 0.0,
                "outpaint_placeholder_detected": False,
            }

        rgb = np.asarray(candidate.convert("RGB"), dtype=np.uint8)
        white = np.all(rgb >= 248, axis=2) & editable
        black = np.all(rgb <= 7, axis=2) & editable
        placeholder_map = np.where(white | black, 255, 0).astype(np.uint8)

        white_ratio = float(np.count_nonzero(white)) / float(editable_pixels)
        black_ratio = float(np.count_nonzero(black)) / float(editable_pixels)
        component_ratio = 0.0
        if np.any(placeholder_map):
            count, _, stats, _ = cv2.connectedComponentsWithStats(placeholder_map, connectivity=8)
            if count > 1:
                largest = int(stats[1:, cv2.CC_STAT_AREA].max())
                component_ratio = largest / float(editable_pixels)

        detected = component_ratio >= 0.72
        return {
            "outpaint_checked_pixels": editable_pixels,
            "solid_white_ratio": round(white_ratio, 6),
            "solid_black_ratio": round(black_ratio, 6),
            "largest_placeholder_component_ratio": round(component_ratio, 6),
            "outpaint_placeholder_detected": bool(detected),
        }

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
        """Promote first-pass output but defer placeholder rejection to refinement."""

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        with Image.open(provider_output) as generated_source:
            generated = ImageOps.exif_transpose(generated_source).convert("RGB")
            provider_actual_size = generated.size

        crop_box = self._provider_crop_box(
            provider_actual_size,
            prepared["content_box_normalized"],
        )
        generated_master = generated.crop(crop_box).resize(
            (width, height),
            Image.Resampling.LANCZOS,
        )
        environment_master_path = output_dir / "nano-banana-remapped.png"
        generated_master.save(environment_master_path, format="PNG", optimize=False)

        with Image.open(geometry_image) as geometry_source:
            approved_rgba = ImageOps.exif_transpose(geometry_source).convert("RGBA")
        if approved_rgba.size != (width, height):
            raise AIEngineError(
                "Результат коррекции геометрии не соответствует размеру рабочего холста.",
                details={"geometry_size": approved_rgba.size, "master_size": (width, height)},
            )

        approved_rgb = approved_rgba.convert("RGB")
        plan_path = Path(prepared.get("effective_mask_path") or outpaint_mask)
        with Image.open(plan_path) as plan_source:
            outpaint_plan = ImageOps.exif_transpose(plan_source).convert("L").point(
                lambda value: 255 if value >= 128 else 0,
                mode="L",
            )

        requested_mode = self._normalize_generation_mode(
            prepared.get("requested_generation_mode") or prepared.get("generation_mode")
        )
        generation_quality = self._quality_from_prompt(str(prepared.get("compiled_prompt_ui") or ""))

        if requested_mode == "outpaint":
            candidate = Image.composite(generated_master, approved_rgb, outpaint_plan)
            outside = ImageOps.invert(outpaint_plan)
            outside_difference = ImageChops.multiply(
                ImageChops.difference(candidate, approved_rgb).convert("L"),
                outside,
            )
            outside_changed_pixels = self._pixel_count_local(
                outside_difference.point(lambda value: 255 if value > 0 else 0, mode="L")
            )
            if outside_changed_pixels:
                raise AIEngineError(
                    "Не удалось сохранить исходные пиксели вне области outpaint.",
                    details={
                        "reason": "outpaint_pixel_preservation_failed",
                        "outside_changed_pixels": outside_changed_pixels,
                    },
                )
            placeholder = self._outpaint_placeholder_stats(candidate, outpaint_plan)
            full_frame_semantic_edit = False
            preservation_policy = "pixel-exact-outside-missing-regions"
        else:
            candidate = generated_master
            outside_changed_pixels = None
            placeholder = {
                "outpaint_checked_pixels": 0,
                "solid_white_ratio": 0.0,
                "solid_black_ratio": 0.0,
                "largest_placeholder_component_ratio": 0.0,
                "outpaint_placeholder_detected": False,
            }
            full_frame_semantic_edit = True
            preservation_policy = "prompt-enforced-corrected-architecture"

        candidate_path = output_dir / "candidate.png"
        candidate.save(candidate_path, format="PNG", optimize=False)
        diagnostic_plan_path = output_dir / "automatic-outpaint-plan.png"
        outpaint_plan.save(diagnostic_plan_path, format="PNG", optimize=False)

        return {
            "candidate": str(candidate_path),
            "environment_master": str(environment_master_path),
            "provider_actual_width": provider_actual_size[0],
            "provider_actual_height": provider_actual_size[1],
            "provider_crop_box": {
                "left": crop_box[0],
                "top": crop_box[1],
                "right": crop_box[2],
                "bottom": crop_box[3],
            },
            "master_width": width,
            "master_height": height,
            "remapped_to_master": True,
            "approved_geometry_preserved": requested_mode == "outpaint",
            "geometry_preservation_policy": preservation_policy,
            "pixel_preservation_verified": requested_mode == "outpaint",
            "outside_changed_pixels": outside_changed_pixels,
            "automatic_outpaint_plan": str(diagnostic_plan_path),
            "requested_generation_mode": requested_mode,
            "generation_mode": requested_mode,
            "generation_quality": generation_quality,
            "full_frame_semantic_edit": full_frame_semantic_edit,
            "strong_image_edit_enabled": requested_mode in {"hybrid", "relight", "edit"},
            "initial_outpaint_qc_blocking": False,
            **placeholder,
        }

    def _internal_outpaint_prompt(self, primary_prompt: str) -> str:
        """Second pass sees the complete original prompt, not a shortened clause."""

        quality = self._quality_from_prompt(primary_prompt)
        return (
            "INTERNAL HYBRID PASS 2/2 — OUTPAINT ONLY\n"
            f"{GENERATION_MODE_MARKER}\nOUTPAINT\n\n"
            f"{GENERATION_QUALITY_MARKER}\n{quality.upper()}\n\n"
            "EXECUTION RULE\n"
            "The supplied image already contains the completed semantic edit / relight result. Existing visible pixels and all completed edits are final.\n"
            "Reconstruct only pixels where visual information is missing after perspective correction. Treat the missing region as continuation of the SAME photograph, never as a patch.\n"
            "Match perspective, texture scale, sharpness, photographic noise, colour, weather, lighting, materials and atmosphere. Do not return low-detail filler.\n"
            "The FULL ORIGINAL COMPILED PROMPT below is mandatory scene context. Preserve every descriptive requirement from it. Nested generation-mode text inside that context is historical; this internal pass remains OUTPAINT ONLY.\n\n"
            "FULL ORIGINAL COMPILED PROMPT — MANDATORY CONTEXT\n"
            f"{primary_prompt}"
        )

    @staticmethod
    def _edge_owner_masks(plan: Image.Image) -> list[tuple[str, np.ndarray]]:
        plan_array = np.asarray(
            plan.convert("L").point(lambda value: 255 if value >= 128 else 0, mode="L"),
            dtype=np.uint8,
        )
        missing = plan_array > 0
        if not np.any(missing):
            return []

        height, width = plan_array.shape
        yy, xx = np.indices((height, width))
        distances = np.stack(
            [yy, height - 1 - yy, xx, width - 1 - xx],
            axis=0,
        )
        owner = np.argmin(distances, axis=0)
        sides = ("top", "bottom", "left", "right")
        return [
            (side, missing & (owner == index))
            for index, side in enumerate(sides)
            if np.any(missing & (owner == index))
        ]

    def _build_edge_targets(
        self,
        *,
        base_image: Path,
        outpaint_plan: Path,
        output_dir: Path,
        generation_quality: str,
    ) -> list[dict[str, Any]]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        profile = self._quality_profile(generation_quality)

        with Image.open(base_image) as source:
            base_rgba = ImageOps.exif_transpose(source).convert("RGBA")
        with Image.open(outpaint_plan) as source:
            plan = ImageOps.exif_transpose(source).convert("L").point(
                lambda value: 255 if value >= 128 else 0,
                mode="L",
            )

        width, height = base_rgba.size
        padding = int(round(min(width, height) * float(profile["padding_ratio"])))
        padding = max(int(profile["padding_min"]), min(int(profile["padding_max"]), padding))
        base_array = np.asarray(base_rgba, dtype=np.uint8)
        targets: list[dict[str, Any]] = []

        for side, owner_mask in self._edge_owner_masks(plan):
            ys, xs = np.where(owner_mask)
            x1 = max(0, int(xs.min()) - padding)
            y1 = max(0, int(ys.min()) - padding)
            x2 = min(width, int(xs.max()) + padding + 1)
            y2 = min(height, int(ys.max()) + padding + 1)
            if x2 <= x1 or y2 <= y1:
                continue

            crop = base_array[y1:y2, x1:x2].copy()
            true_mask = np.where(owner_mask[y1:y2, x1:x2], 255, 0).astype(np.uint8)
            all_missing = crop[:, :, 3] < 250

            context_rgb = crop[:, :, :3]
            if np.any(all_missing):
                context_rgb = cv2.inpaint(
                    context_rgb,
                    np.where(all_missing, 255, 0).astype(np.uint8),
                    7,
                    cv2.INPAINT_TELEA,
                )

            dilate_radius = max(7, min(28, int(round(min(x2 - x1, y2 - y1) * 0.022))))
            kernel_size = dilate_radius * 2 + 1
            dilated = cv2.dilate(
                true_mask,
                np.ones((kernel_size, kernel_size), dtype=np.uint8),
                iterations=1,
            )
            tile_rgba = np.dstack(
                [
                    context_rgb,
                    np.where(dilated > 0, 0, 255).astype(np.uint8),
                ]
            )

            tile_dir = output_dir / side
            tile_dir.mkdir(parents=True, exist_ok=True)
            geometry_path = tile_dir / "tile-geometry.png"
            mask_path = tile_dir / "true-missing-region.png"
            context_path = tile_dir / "context-rgb.png"
            Image.fromarray(tile_rgba, mode="RGBA").save(geometry_path, format="PNG", optimize=False)
            Image.fromarray(true_mask, mode="L").save(mask_path, format="PNG", optimize=False)
            Image.fromarray(context_rgb, mode="RGB").save(context_path, format="PNG", optimize=False)
            targets.append(
                {
                    "side": side,
                    "bbox": (x1, y1, x2, y2),
                    "geometry": geometry_path,
                    "mask": mask_path,
                    "context": context_path,
                    "width": x2 - x1,
                    "height": y2 - y1,
                    "padding": padding,
                    "missing_pixels": int(np.count_nonzero(true_mask)),
                }
            )

        return targets

    def _edge_tile_prompt(
        self,
        original_prompt: str,
        side: str,
        attempt: int,
        generation_quality: str,
        max_attempts: int,
    ) -> str:
        retry_note = (
            "The previous local candidate was blank, too soft, too unrelated or visibly patch-like. Improve real texture, continuity and detail.\n"
            if attempt > 1
            else ""
        )
        return (
            "INTERNAL QUALITY EDGE OUTPAINT\n"
            f"{GENERATION_MODE_MARKER}\nOUTPAINT\n\n"
            f"{GENERATION_QUALITY_MARKER}\n{generation_quality.upper()}\n\n"
            f"Edge: {side.upper()}. Candidate: {attempt}/{max_attempts}.\n"
            "The transparent area is missing photographic information. Reconstruct it as continuation of the SAME photograph, not as an inserted patch.\n"
            "Use the broad visible context to continue exact perspective, ground/sky structure, texture frequency, sharpness, photographic noise, colour, lighting, shadows and materials.\n"
            "Do not redesign visible content. Never output a blank, solid fill or low-detail smear.\n"
            "All explicit scene requirements in the FULL ORIGINAL COMPILED PROMPT below are mandatory context. Nested mode text is historical; this local pass is OUTPAINT ONLY.\n"
            f"{retry_note}\n"
            "FULL ORIGINAL COMPILED PROMPT — MANDATORY CONTEXT\n"
            f"{original_prompt}"
        )

    @staticmethod
    def _tile_quality_stats(
        candidate: Image.Image,
        context: Image.Image,
        mask: Image.Image,
    ) -> dict[str, Any]:
        rgb = np.asarray(candidate.convert("RGB"), dtype=np.uint8)
        context_rgb = np.asarray(context.convert("RGB"), dtype=np.uint8)
        mask_u8 = np.asarray(mask.convert("L"), dtype=np.uint8)
        inside = mask_u8 > 0
        inside_pixels = int(np.count_nonzero(inside))
        if inside_pixels == 0:
            return {
                "quality_score": 0.0,
                "boundary_colour_delta": 255.0,
                "inside_detail": 0.0,
                "context_detail": 0.0,
                "detail_ratio": 0.0,
                "low_detail_detected": True,
            }

        band = max(5, min(18, int(round(min(mask_u8.shape) * 0.025))))
        kernel = np.ones((band * 2 + 1, band * 2 + 1), dtype=np.uint8)
        dilated = cv2.dilate(np.where(inside, 255, 0).astype(np.uint8), kernel, iterations=1) > 0
        outer = dilated & ~inside
        distance = cv2.distanceTransform(np.where(inside, 255, 0).astype(np.uint8), cv2.DIST_L2, 5)
        inner_boundary = inside & (distance <= float(band))

        if np.any(inner_boundary) and np.any(outer):
            inside_mean = rgb[inner_boundary].astype(np.float32).mean(axis=0)
            outer_mean = context_rgb[outer].astype(np.float32).mean(axis=0)
            colour_delta = float(np.mean(np.abs(inside_mean - outer_mean)))
        else:
            colour_delta = 32.0

        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        context_gray = cv2.cvtColor(context_rgb, cv2.COLOR_RGB2GRAY)
        lap = cv2.Laplacian(gray, cv2.CV_64F)
        context_lap = cv2.Laplacian(context_gray, cv2.CV_64F)
        inside_detail = float(np.var(lap[inside])) if np.any(inside) else 0.0
        context_detail = float(np.var(context_lap[outer])) if np.any(outer) else inside_detail
        detail_ratio = (inside_detail + 1.0) / (context_detail + 1.0)
        low_detail = bool(context_detail > 18.0 and detail_ratio < 0.22)

        detail_penalty = abs(math.log(max(0.05, min(20.0, detail_ratio)))) * 8.0
        score = 100.0 - min(70.0, colour_delta * 0.72) - min(40.0, detail_penalty)
        if low_detail:
            score -= 18.0
        score = max(0.0, min(100.0, score))
        return {
            "quality_score": round(score, 3),
            "boundary_colour_delta": round(colour_delta, 3),
            "inside_detail": round(inside_detail, 3),
            "context_detail": round(context_detail, 3),
            "detail_ratio": round(detail_ratio, 4),
            "low_detail_detected": low_detail,
        }

    @staticmethod
    def _harmonize_and_blend_inside_missing(
        *,
        generated: Image.Image,
        existing: Image.Image,
        context: Image.Image,
        mask: Image.Image,
        feather_px: int,
        tone_match_strength: float,
    ) -> Image.Image:
        generated_np = np.asarray(generated.convert("RGB"), dtype=np.float32)
        existing_np = np.asarray(existing.convert("RGB"), dtype=np.float32)
        context_np = np.asarray(context.convert("RGB"), dtype=np.uint8)
        mask_u8 = np.asarray(mask.convert("L"), dtype=np.uint8)
        inside = mask_u8 > 0
        if not np.any(inside):
            return existing.convert("RGB")

        band = max(5, min(24, int(feather_px)))
        kernel = np.ones((band * 2 + 1, band * 2 + 1), dtype=np.uint8)
        dilated = cv2.dilate(np.where(inside, 255, 0).astype(np.uint8), kernel, iterations=1) > 0
        outer = dilated & ~inside
        distance = cv2.distanceTransform(np.where(inside, 255, 0).astype(np.uint8), cv2.DIST_L2, 5)
        inner_boundary = inside & (distance <= float(band))

        adjusted = generated_np.copy()
        if np.any(inner_boundary) and np.any(outer):
            inner_mean = generated_np[inner_boundary].mean(axis=0)
            outer_mean = context_np[outer].astype(np.float32).mean(axis=0)
            delta = np.clip(outer_mean - inner_mean, -32.0, 32.0) * float(tone_match_strength)
            adjusted[inside] = np.clip(adjusted[inside] + delta, 0.0, 255.0)

        inpaint_radius = max(5, min(15, int(round(feather_px * 0.35))))
        context_fill = cv2.inpaint(
            context_np,
            np.where(inside, 255, 0).astype(np.uint8),
            inpaint_radius,
            cv2.INPAINT_TELEA,
        ).astype(np.float32)

        alpha = np.clip(distance / max(1.0, float(feather_px)), 0.0, 1.0)
        alpha = alpha[:, :, None]
        blended_missing = adjusted * alpha + context_fill * (1.0 - alpha)

        output = existing_np.copy()
        output[inside] = blended_missing[inside]
        return Image.fromarray(np.clip(output, 0, 255).astype(np.uint8), mode="RGB")

    def _run_edge_tile_refinement(
        self,
        *,
        original_prompt: str,
        base_image: Path,
        outpaint_plan: Path,
        output_dir: Path,
        generation_quality: str,
        seed_candidate: Path | None,
        require_complete: bool,
        reason: str,
    ) -> dict[str, Any]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        quality = self._normalize_generation_quality(generation_quality)
        profile = self._quality_profile(quality)

        with Image.open(base_image) as source:
            base_rgba = ImageOps.exif_transpose(source).convert("RGBA")
        with Image.open(outpaint_plan) as source:
            plan = ImageOps.exif_transpose(source).convert("L").point(
                lambda value: 255 if value >= 128 else 0,
                mode="L",
            )

        missing_pixels = self._pixel_count_local(plan)
        if missing_pixels == 0:
            candidate_path = output_dir / "candidate.png"
            base_rgba.convert("RGB").save(candidate_path, format="PNG", optimize=False)
            return {
                "candidate": str(candidate_path),
                "outpaint_refinement_used": False,
                "outpaint_refinement_reason": "no-missing-regions",
                "fallback_provider_calls": 0,
                "fallback_failed_edges": [],
                "fallback_remaining_pixels": 0,
            }

        targets = self._build_edge_targets(
            base_image=base_image,
            outpaint_plan=outpaint_plan,
            output_dir=output_dir / "targets",
            generation_quality=quality,
        )
        if not targets:
            if require_complete:
                raise AIEngineError(
                    "Система видит отсутствующие участки изображения, но не смогла построить области локального outpaint.",
                    details={"reason": "edge_refinement_plan_empty", "missing_pixels": missing_pixels},
                )
            return {
                "candidate": str(seed_candidate or base_image),
                "outpaint_refinement_used": False,
                "outpaint_refinement_reason": "no-edge-targets",
                "fallback_provider_calls": 0,
                "fallback_failed_edges": [],
                "fallback_remaining_pixels": 0,
            }

        if seed_candidate and Path(seed_candidate).is_file():
            with Image.open(seed_candidate) as source:
                working = ImageOps.exif_transpose(source).convert("RGB")
            coverage = np.asarray(plan, dtype=np.uint8) > 0
        else:
            working = base_rgba.convert("RGB")
            coverage = np.zeros((base_rgba.height, base_rgba.width), dtype=bool)

        provider_calls = 0
        failed_edges: list[str] = []
        attempts_log: list[dict[str, Any]] = []
        selected_log: list[dict[str, Any]] = []
        max_attempts = int(profile["max_attempts"])
        min_attempts = int(profile["min_attempts"])
        threshold = float(profile["quality_threshold"])

        for target in targets:
            side = str(target["side"])
            candidates: list[tuple[float, Image.Image, dict[str, Any], dict[str, Any]]] = []

            with Image.open(target["mask"]) as mask_source:
                true_mask = ImageOps.exif_transpose(mask_source).convert("L").point(
                    lambda value: 255 if value >= 128 else 0,
                    mode="L",
                )
            with Image.open(target["context"]) as context_source:
                context = ImageOps.exif_transpose(context_source).convert("RGB")

            for attempt in range(1, max_attempts + 1):
                prompt = self._edge_tile_prompt(
                    original_prompt,
                    side,
                    attempt,
                    quality,
                    max_attempts,
                )
                attempt_dir = output_dir / "generation" / side / f"attempt-{attempt}"
                previous_internal = getattr(self._runtime, "internal_geometry", None)
                self._runtime.internal_geometry = str(Path(target["geometry"]).resolve())
                try:
                    prepared = self.prepare_environment_inputs(
                        prompt=prompt,
                        geometry_image=Path(target["geometry"]),
                        outpaint_mask=Path(target["mask"]),
                        output_dir=attempt_dir / "transport",
                        width=int(target["width"]),
                        height=int(target["height"]),
                    )
                    result = self._single_pass(
                        prompt=prompt,
                        geometry_image=Path(target["geometry"]),
                        outpaint_mask=Path(target["mask"]),
                        output_dir=attempt_dir,
                        width=int(target["width"]),
                        height=int(target["height"]),
                        prepared_input=prepared,
                    )
                finally:
                    self._runtime.internal_geometry = previous_internal

                provider_calls += 1
                with Image.open(result["candidate"]) as candidate_source:
                    tile_candidate = ImageOps.exif_transpose(candidate_source).convert("RGB")
                placeholder = self._outpaint_placeholder_stats(tile_candidate, true_mask)
                quality_stats = self._tile_quality_stats(tile_candidate, context, true_mask)
                attempt_info = {
                    "side": side,
                    "attempt": attempt,
                    "candidate": result.get("candidate"),
                    **placeholder,
                    **quality_stats,
                }
                attempts_log.append(attempt_info)

                if not placeholder["outpaint_placeholder_detected"]:
                    candidates.append((float(quality_stats["quality_score"]), tile_candidate.copy(), attempt_info, result))

                if (
                    attempt >= min_attempts
                    and candidates
                    and max(item[0] for item in candidates) >= threshold
                    and not bool(max(candidates, key=lambda item: item[0])[2].get("low_detail_detected"))
                ):
                    break

            if not candidates:
                failed_edges.append(side)
                continue

            best_score, best_candidate, best_info, _ = max(candidates, key=lambda item: item[0])
            bbox = tuple(target["bbox"])
            existing_crop = working.crop(bbox)
            blended = self._harmonize_and_blend_inside_missing(
                generated=best_candidate,
                existing=existing_crop,
                context=context,
                mask=true_mask,
                feather_px=int(profile["feather_px"]),
                tone_match_strength=float(profile["tone_match_strength"]),
            )
            working.paste(blended, (bbox[0], bbox[1]))
            mask_array = np.asarray(true_mask, dtype=np.uint8) > 0
            coverage[bbox[1]:bbox[3], bbox[0]:bbox[2]] |= mask_array
            selected_log.append(
                {
                    "side": side,
                    "selected_attempt": best_info["attempt"],
                    "selected_quality_score": round(best_score, 3),
                    "padding": target["padding"],
                    "feather_px": int(profile["feather_px"]),
                    "tone_match_strength": float(profile["tone_match_strength"]),
                }
            )

        plan_array = np.asarray(plan, dtype=np.uint8) > 0
        remaining = plan_array & ~coverage
        remaining_pixels = int(np.count_nonzero(remaining))
        candidate_path = output_dir / "candidate.png"
        working.save(candidate_path, format="PNG", optimize=False)
        final_stats = self._outpaint_placeholder_stats(working, plan)

        diagnostics = {
            "candidate": str(candidate_path),
            "outpaint_refinement_used": True,
            "outpaint_fallback_used": reason == "full-frame-placeholder",
            "outpaint_fallback_mode": self.outpaint_fallback_mode,
            "outpaint_refinement_reason": reason,
            "generation_quality": quality,
            "quality_profile": profile,
            "fallback_provider_calls": provider_calls,
            "fallback_failed_edges": failed_edges,
            "fallback_remaining_pixels": remaining_pixels,
            "fallback_missing_pixels": missing_pixels,
            "fallback_attempts": attempts_log,
            "selected_edge_candidates": selected_log,
            "fallback_final_placeholder": final_stats,
            "full_prompt_context_sha256": self._prompt_sha256(original_prompt),
        }
        (output_dir / "refinement.json").write_text(
            json.dumps(diagnostics, ensure_ascii=False, indent=2),
            "utf-8",
        )

        if require_complete and (remaining_pixels > 0 or final_stats["outpaint_placeholder_detected"]):
            raise AIEngineError(
                "Nano Banana не смогла полностью дорисовать окружение даже после локального quality edge-refinement.",
                details={"reason": "outpaint_failed_after_edge_refinement", **diagnostics},
            )

        return diagnostics

    def _repair_or_refine_outpaint(
        self,
        *,
        result: dict,
        kwargs: dict,
        mode: str,
    ) -> dict:
        if mode not in {"outpaint", "hybrid"}:
            return result

        original_prompt = str(kwargs.get("prompt") or "")
        quality = self._quality_from_prompt(original_prompt)
        profile = self._quality_profile(quality)
        placeholder = bool(result.get("outpaint_placeholder_detected"))
        force_refine = bool(profile["force_edge_refine"])
        if not placeholder and not force_refine:
            result.setdefault("outpaint_fallback_used", False)
            result.setdefault("outpaint_refinement_used", False)
            result["generation_quality"] = quality
            result["quality_profile"] = profile
            return result

        prepared = kwargs.get("prepared_input") or {}
        plan_value = (
            result.get("automatic_outpaint_plan")
            or prepared.get("effective_mask_path")
            or kwargs.get("outpaint_mask")
        )
        if not plan_value:
            raise AIEngineError(
                "Не найден внутренний план отсутствующих областей для quality outpaint.",
                details={"reason": "outpaint_refinement_plan_missing"},
            )

        if mode == "hybrid":
            base_value = result.get("hybrid_intermediate")
            if not base_value:
                raise AIEngineError(
                    "Не найден промежуточный результат image edit для quality outpaint.",
                    details={"reason": "hybrid_intermediate_missing"},
                )
        else:
            base_value = kwargs.get("geometry_image")

        reason = "full-frame-placeholder" if placeholder else "quality-edge-refine"
        seed_candidate = None if placeholder else Path(str(result["candidate"]))
        refinement = self._run_edge_tile_refinement(
            original_prompt=original_prompt,
            base_image=Path(str(base_value)),
            outpaint_plan=Path(str(plan_value)),
            output_dir=Path(kwargs["output_dir"]) / "quality-edge-refinement",
            generation_quality=quality,
            seed_candidate=seed_candidate,
            require_complete=placeholder,
            reason=reason,
        )

        repaired = dict(result)
        repaired.update(refinement)
        repaired["candidate"] = refinement["candidate"]
        repaired["environment_master"] = refinement["candidate"]
        repaired["initial_outpaint_placeholder_detected"] = placeholder
        repaired["outpaint_placeholder_detected"] = False if placeholder else bool(
            refinement.get("fallback_final_placeholder", {}).get("outpaint_placeholder_detected", False)
        )
        repaired["provider_call_count"] = int(result.get("provider_call_count") or 1) + int(
            refinement.get("fallback_provider_calls") or 0
        )
        repaired["generation_quality"] = quality
        repaired["quality_profile"] = profile
        return repaired

    def _promote_skill_metadata(self, result: dict, mode: str, quality: str) -> dict:
        result["active_skill"] = mode
        result["skill_contract_version"] = self.skill_contract_version
        result["generation_quality"] = quality
        result["available_generation_qualities"] = list(self.available_generation_qualities)
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
        result["outpaint_fallback_mode"] = self.outpaint_fallback_mode
        result["full_prompt_context_policy"] = "complete-compiled-prompt-propagated-to-outpaint-and-edge-refinement"
        return result

    def generate_environment(self, **kwargs) -> dict:
        output_dir = Path(kwargs["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        original_prompt = str(kwargs.get("prompt") or "")
        quality = self._quality_from_prompt(original_prompt)

        result = super().generate_environment(**kwargs)
        mode = self._normalize_generation_mode(
            result.get("requested_generation_mode") or result.get("generation_mode")
        )
        result = self._repair_or_refine_outpaint(
            result=result,
            kwargs=kwargs,
            mode=mode,
        )
        result = self._promote_skill_metadata(result, mode, quality)
        result["available_generation_modes"] = list(self.available_generation_modes)

        (output_dir / "generation.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            "utf-8",
        )
        return result


_engine_module.OpenRouterImageEngine = OpenRouterImageEngine
