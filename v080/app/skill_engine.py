from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageChops, ImageOps

from . import ai_engine as _engine_module
from .hybrid_engine import AIEngineError, OpenRouterImageEngine as _HybridOpenRouterImageEngine
from .prompt_engine import GENERATION_MODE_MARKER


class OpenRouterImageEngine(_HybridOpenRouterImageEngine):
    """Canonical skill-aware runtime.

    OUTPAINT is pixel-preserving outside missing regions. A failed full-frame
    outpaint is not rejected immediately: the runtime retries the missing image
    information as context-rich edge tiles and promotes the repaired master only
    after every missing pixel has been reconstructed.

    RELIGHT is a full-frame photometric transformation with geometry locked.
    IMAGE EDIT keeps requested semantic changes and never restores source pixels
    over them. HYBRID performs semantic edit/relight first and outpaint second.
    """

    transport_engine_version = "3.3.0"
    available_generation_modes = ("hybrid", "relight", "edit", "outpaint")
    skill_contract_version = "outpaint-relight-edit-hybrid-v1"
    outpaint_fallback_mode = "edge-tiles-on-placeholder"
    outpaint_fallback_attempts_per_edge = 2
    outpaint_initial_qc_blocking = False

    @staticmethod
    def _pixel_count_local(mask: Image.Image) -> int:
        binary = mask.convert("L").point(lambda value: 255 if value >= 128 else 0, mode="L")
        return int(sum(binary.histogram()[128:]))

    @staticmethod
    def _outpaint_placeholder_stats(candidate: Image.Image, plan: Image.Image) -> dict[str, Any]:
        """Detect large contiguous blank fills, not legitimate bright/dark scene pixels."""

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
        """Promote a provider image without throwing on the first blank outpaint.

        The previous hybrid layer rejected a white/black outpaint here. That made
        a later repair impossible because generate_environment never received the
        failed candidate. This implementation records the failure and lets the
        top-level skill runtime invoke the edge fallback.
        """

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
            "full_frame_semantic_edit": full_frame_semantic_edit,
            "strong_image_edit_enabled": requested_mode in {"hybrid", "relight", "edit"},
            "initial_outpaint_qc_blocking": False,
            **placeholder,
        }

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
    ) -> list[dict[str, Any]]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        with Image.open(base_image) as source:
            base_rgba = ImageOps.exif_transpose(source).convert("RGBA")
        with Image.open(outpaint_plan) as source:
            plan = ImageOps.exif_transpose(source).convert("L").point(
                lambda value: 255 if value >= 128 else 0,
                mode="L",
            )

        width, height = base_rgba.size
        padding = max(96, int(round(min(width, height) * 0.14)))
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

            # Other transparent areas inside the context crop are filled only as
            # temporary visual context. Final promotion uses true_mask, so these
            # service pixels never enter the delivered image.
            context_rgb = crop[:, :, :3]
            if np.any(all_missing):
                context_rgb = cv2.inpaint(
                    context_rgb,
                    np.where(all_missing, 255, 0).astype(np.uint8),
                    7,
                    cv2.INPAINT_TELEA,
                )

            dilate_radius = max(5, min(16, int(round(min(x2 - x1, y2 - y1) * 0.015))))
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
            Image.fromarray(tile_rgba, mode="RGBA").save(
                geometry_path,
                format="PNG",
                optimize=False,
            )
            Image.fromarray(true_mask, mode="L").save(
                mask_path,
                format="PNG",
                optimize=False,
            )
            targets.append(
                {
                    "side": side,
                    "bbox": (x1, y1, x2, y2),
                    "geometry": geometry_path,
                    "mask": mask_path,
                    "width": x2 - x1,
                    "height": y2 - y1,
                    "missing_pixels": int(np.count_nonzero(true_mask)),
                }
            )

        return targets

    def _edge_tile_prompt(self, original_prompt: str, side: str, attempt: int) -> str:
        operator = self._operator_block(original_prompt)
        retry_note = (
            "The previous local attempt left a blank placeholder. Use real scene texture and structure this time.\n"
            if attempt > 1
            else ""
        )
        return (
            "INTERNAL EDGE OUTPAINT FALLBACK\n"
            f"Edge: {side.upper()}. Attempt: {attempt}/{self.outpaint_fallback_attempts_per_edge}.\n"
            "The transparent area is missing photographic information, not a white/black object.\n"
            "Reconstruct it as a photorealistic continuation of the immediately adjacent scene.\n"
            "Continue perspective lines, sky, facade edges, neighbouring buildings, pavement, vegetation, shadows and lighting naturally.\n"
            "Do not redesign any existing visible content. Never output a blank, solid white, solid black or flat-colour fill.\n"
            f"{retry_note}\n"
            f"{GENERATION_MODE_MARKER}\nOUTPAINT\n\n"
            "ORIGINAL OPERATOR REQUEST — CONTEXT ONLY\n"
            f"{operator}"
        )

    def _run_edge_tile_fallback(
        self,
        *,
        original_prompt: str,
        base_image: Path,
        outpaint_plan: Path,
        output_dir: Path,
    ) -> dict[str, Any]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        with Image.open(base_image) as source:
            base_rgba = ImageOps.exif_transpose(source).convert("RGBA")
        with Image.open(outpaint_plan) as source:
            plan = ImageOps.exif_transpose(source).convert("L").point(
                lambda value: 255 if value >= 128 else 0,
                mode="L",
            )

        targets = self._build_edge_targets(
            base_image=base_image,
            outpaint_plan=outpaint_plan,
            output_dir=output_dir / "targets",
        )
        missing_pixels = self._pixel_count_local(plan)
        if missing_pixels == 0:
            candidate_path = output_dir / "candidate.png"
            base_rgba.convert("RGB").save(candidate_path, format="PNG", optimize=False)
            return {
                "candidate": str(candidate_path),
                "outpaint_fallback_used": False,
                "outpaint_fallback_reason": "no-missing-regions",
                "fallback_provider_calls": 0,
                "fallback_failed_edges": [],
                "fallback_remaining_pixels": 0,
            }
        if not targets:
            raise AIEngineError(
                "Система видит отсутствующие участки изображения, но не смогла построить области локального outpaint.",
                details={
                    "reason": "edge_fallback_plan_empty",
                    "missing_pixels": missing_pixels,
                },
            )

        working = base_rgba.convert("RGB")
        coverage = np.zeros((base_rgba.height, base_rgba.width), dtype=bool)
        provider_calls = 0
        failed_edges: list[str] = []
        attempts_log: list[dict[str, Any]] = []

        for target in targets:
            side = str(target["side"])
            success = False
            for attempt in range(1, self.outpaint_fallback_attempts_per_edge + 1):
                prompt = self._edge_tile_prompt(original_prompt, side, attempt)
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
                with Image.open(target["mask"]) as mask_source:
                    true_mask = ImageOps.exif_transpose(mask_source).convert("L").point(
                        lambda value: 255 if value >= 128 else 0,
                        mode="L",
                    )
                stats = self._outpaint_placeholder_stats(tile_candidate, true_mask)
                attempts_log.append(
                    {
                        "side": side,
                        "attempt": attempt,
                        "candidate": result.get("candidate"),
                        **stats,
                    }
                )
                if stats["outpaint_placeholder_detected"]:
                    continue

                bbox = tuple(target["bbox"])
                current_crop = working.crop(bbox)
                composed = Image.composite(tile_candidate, current_crop, true_mask)
                working.paste(composed, (bbox[0], bbox[1]))
                mask_array = np.asarray(true_mask, dtype=np.uint8) > 0
                coverage[bbox[1]:bbox[3], bbox[0]:bbox[2]] |= mask_array
                success = True
                break

            if not success:
                failed_edges.append(side)

        plan_array = np.asarray(plan, dtype=np.uint8) > 0
        remaining = plan_array & ~coverage
        remaining_pixels = int(np.count_nonzero(remaining))
        candidate_path = output_dir / "candidate.png"
        working.save(candidate_path, format="PNG", optimize=False)
        final_stats = self._outpaint_placeholder_stats(working, plan)

        diagnostics = {
            "candidate": str(candidate_path),
            "outpaint_fallback_used": True,
            "outpaint_fallback_mode": self.outpaint_fallback_mode,
            "outpaint_fallback_reason": "full-frame-placeholder",
            "fallback_provider_calls": provider_calls,
            "fallback_failed_edges": failed_edges,
            "fallback_remaining_pixels": remaining_pixels,
            "fallback_missing_pixels": missing_pixels,
            "fallback_attempts": attempts_log,
            "fallback_final_placeholder": final_stats,
        }
        (output_dir / "fallback.json").write_text(
            json.dumps(diagnostics, ensure_ascii=False, indent=2),
            "utf-8",
        )

        if remaining_pixels > 0 or final_stats["outpaint_placeholder_detected"]:
            raise AIEngineError(
                "Nano Banana не смогла полностью дорисовать окружение даже после локального edge-outpaint fallback.",
                details={
                    "reason": "outpaint_failed_after_edge_fallback",
                    **diagnostics,
                },
            )

        return diagnostics

    def _repair_placeholder_if_needed(
        self,
        *,
        result: dict,
        kwargs: dict,
        mode: str,
    ) -> dict:
        if mode not in {"outpaint", "hybrid"}:
            return result
        if not bool(result.get("outpaint_placeholder_detected")):
            result.setdefault("outpaint_fallback_used", False)
            return result

        prepared = kwargs.get("prepared_input") or {}
        plan_value = (
            result.get("automatic_outpaint_plan")
            or prepared.get("effective_mask_path")
            or kwargs.get("outpaint_mask")
        )
        if not plan_value:
            raise AIEngineError(
                "Не найден внутренний план отсутствующих областей для повторного outpaint.",
                details={"reason": "outpaint_fallback_plan_missing"},
            )

        if mode == "hybrid":
            base_value = result.get("hybrid_intermediate")
            if not base_value:
                raise AIEngineError(
                    "Не найден промежуточный результат image edit для локального outpaint.",
                    details={"reason": "hybrid_intermediate_missing"},
                )
        else:
            base_value = kwargs.get("geometry_image")

        fallback = self._run_edge_tile_fallback(
            original_prompt=str(kwargs.get("prompt") or ""),
            base_image=Path(base_value),
            outpaint_plan=Path(plan_value),
            output_dir=Path(kwargs["output_dir"]) / "edge-outpaint-fallback",
        )
        repaired = dict(result)
        repaired.update(fallback)
        repaired["candidate"] = fallback["candidate"]
        repaired["environment_master"] = fallback["candidate"]
        repaired["outpaint_placeholder_detected"] = False
        repaired["initial_outpaint_placeholder_detected"] = True
        repaired["provider_call_count"] = int(result.get("provider_call_count") or 1) + int(
            fallback.get("fallback_provider_calls") or 0
        )
        return repaired

    def _promote_skill_metadata(self, result: dict, mode: str) -> dict:
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
        result["outpaint_fallback_mode"] = self.outpaint_fallback_mode
        return result

    def generate_environment(self, **kwargs) -> dict:
        # The runtime owns the generation directory lifecycle. Create it before
        # entering the hybrid engine so every path can persist diagnostics.
        output_dir = Path(kwargs["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)

        result = super().generate_environment(**kwargs)
        mode = self._normalize_generation_mode(
            result.get("requested_generation_mode") or result.get("generation_mode")
        )
        result = self._repair_placeholder_if_needed(
            result=result,
            kwargs=kwargs,
            mode=mode,
        )
        result = self._promote_skill_metadata(result, mode)
        result["available_generation_modes"] = list(self.available_generation_modes)

        (output_dir / "generation.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            "utf-8",
        )
        return result


_engine_module.OpenRouterImageEngine = OpenRouterImageEngine
