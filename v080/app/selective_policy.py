from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageChops, ImageFilter, ImageOps

from . import ai_engine as _engine_module
from .system_prompts import ENVIRONMENT_SYSTEM_PROMPT, PROMPT_CONTRACT_VERSION


_PreviousOpenRouterImageEngine = _engine_module.OpenRouterImageEngine
AIEngineError = _engine_module.AIEngineError


class OpenRouterImageEngine(_PreviousOpenRouterImageEngine):
    """Точечное редактирование с неизменяемой базой и единственной моделью Nano Banana."""

    transport_engine_version = "2.7.1"
    required_model = "google/gemini-2.5-flash-image"
    generation_mode = "selective-edit"

    minimum_editable_pixels = 64
    minimum_component_pixels = 64
    semantic_difference_threshold = 18

    # Широкий ответ модели больше не отклоняется целиком. Из него извлекаются
    # только компактные локальные компоненты, пока не исчерпан безопасный бюджет.
    maximum_semantic_edit_ratio = 1.0
    maximum_total_selective_edit_ratio = 0.08
    maximum_component_edit_ratio = 0.03
    maximum_component_bbox_ratio = 0.20
    maximum_component_count = 8
    component_padding_px = 9
    maximum_unfilled_ratio = 0.01

    def __init__(self) -> None:
        super().__init__()
        # Выбор модели не настраивается пользователем и не зависит от окружения.
        self.model = self.required_model

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

        return {
            "model": self.required_model,
            "prompt": compiled_prompt,
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
                {
                    "type": "image_url",
                    "image_url": {"url": self._data_url(outpaint_mask)},
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

        editable_pixels = int(prepared.get("editable_pixels") or 0)
        if editable_pixels < self.minimum_editable_pixels:
            mask_policy = "prompt-localized-edit-with-empty-mandatory-mask"
        else:
            mask_policy = "mandatory-white-mask-plus-prompt-localized-edit"

        prepared.update(
            {
                "provider": "openrouter",
                "model": self.required_model,
                "model_lock": "nano-banana-only",
                "required_model": self.required_model,
                "generation_mode": self.generation_mode,
                "source_contract": "approved-geometry-pixel-preserved-outside-edit-area",
                "mask_role": "mandatory-edit-reference-and-postprocess-constraint",
                "mask_policy": mask_policy,
                "input_reference_count": 2,
                "full_canvas_generation": False,
                "pixel_preservation_required": True,
                "localization_policy": "connected-components-soft-clamp",
                "maximum_total_selective_edit_ratio": self.maximum_total_selective_edit_ratio,
                "maximum_component_edit_ratio": self.maximum_component_edit_ratio,
                "maximum_component_bbox_ratio": self.maximum_component_bbox_ratio,
                "maximum_component_count": self.maximum_component_count,
                "semantic_difference_threshold": self.semantic_difference_threshold,
            }
        )
        return prepared

    @staticmethod
    def _pixel_count(mask: Image.Image) -> int:
        binary = mask.convert("L").point(lambda value: 255 if value >= 128 else 0, mode="L")
        return int(sum(binary.histogram()[128:]))

    def _semantic_change_mask(
        self,
        generated: Image.Image,
        approved: Image.Image,
        mandatory_mask: Image.Image,
    ) -> tuple[Image.Image, dict[str, Any]]:
        difference = ImageChops.difference(
            generated.convert("RGB"),
            approved.convert("RGB"),
        )
        red, green, blue = difference.split()
        maximum = ImageChops.lighter(ImageChops.lighter(red, green), blue)
        changed = maximum.point(
            lambda value: 255 if value >= self.semantic_difference_threshold else 0,
            mode="L",
        )
        changed = changed.filter(ImageFilter.MedianFilter(3)).filter(ImageFilter.MaxFilter(5))

        mandatory = mandatory_mask.convert("L").point(
            lambda value: 255 if value >= 128 else 0,
            mode="L",
        )
        outside_mandatory = ImageOps.invert(mandatory)
        semantic = ImageChops.multiply(changed, outside_mandatory)

        semantic_pixels = self._pixel_count(semantic)
        available_pixels = self._pixel_count(outside_mandatory)
        semantic_ratio = semantic_pixels / float(max(1, available_pixels))
        return semantic, {
            "semantic_edit_pixels": semantic_pixels,
            "semantic_available_pixels": available_pixels,
            "semantic_edit_ratio": round(semantic_ratio, 6),
        }

    def _build_selective_edit_mask(
        self,
        semantic_mask: Image.Image,
        mandatory_mask: Image.Image,
    ) -> tuple[Image.Image, dict[str, Any]]:
        """Извлекает компактные локальные изменения и подавляет глобальную перерисовку."""
        semantic = semantic_mask.convert("L").point(
            lambda value: 255 if value >= 128 else 0,
            mode="L",
        )
        mandatory = mandatory_mask.convert("L").point(
            lambda value: 255 if value >= 128 else 0,
            mode="L",
        )

        semantic_array = np.asarray(semantic, dtype=np.uint8)
        semantic_array = cv2.morphologyEx(
            semantic_array,
            cv2.MORPH_OPEN,
            np.ones((3, 3), dtype=np.uint8),
            iterations=1,
        )
        semantic_array = cv2.morphologyEx(
            semantic_array,
            cv2.MORPH_CLOSE,
            np.ones((5, 5), dtype=np.uint8),
            iterations=1,
        )

        labels_count, labels, stats, _ = cv2.connectedComponentsWithStats(
            semantic_array,
            connectivity=8,
        )
        height, width = semantic_array.shape
        total_pixels = max(1, width * height)
        semantic_budget = max(
            self.minimum_component_pixels,
            int(total_pixels * self.maximum_total_selective_edit_ratio),
        )

        candidates: list[dict[str, Any]] = []
        for label_index in range(1, labels_count):
            x, y, box_width, box_height, area = [
                int(value) for value in stats[label_index]
            ]
            if area < self.minimum_component_pixels:
                continue

            area_ratio = area / float(total_pixels)
            bbox_pixels = box_width * box_height
            bbox_ratio = bbox_pixels / float(total_pixels)
            compactness = area / float(max(1, bbox_pixels))

            if area_ratio > self.maximum_component_edit_ratio:
                continue
            if bbox_ratio > self.maximum_component_bbox_ratio:
                continue

            candidates.append(
                {
                    "label": label_index,
                    "area": area,
                    "area_ratio": area_ratio,
                    "bbox_ratio": bbox_ratio,
                    "compactness": compactness,
                    "x": x,
                    "y": y,
                    "width": box_width,
                    "height": box_height,
                }
            )

        # Сначала берём наиболее содержательные и компактные локальные изменения.
        candidates.sort(
            key=lambda item: (
                item["area"] * max(0.1, item["compactness"]),
                item["area"],
            ),
            reverse=True,
        )

        selected = np.zeros_like(semantic_array, dtype=np.uint8)
        kept_components: list[dict[str, Any]] = []
        remaining_budget = semantic_budget

        padding = max(0, int(self.component_padding_px))
        if padding:
            kernel_size = padding * 2 + 1
            padding_kernel = cv2.getStructuringElement(
                cv2.MORPH_ELLIPSE,
                (kernel_size, kernel_size),
            )
        else:
            padding_kernel = None

        for item in candidates:
            if len(kept_components) >= self.maximum_component_count:
                break
            if remaining_budget <= 0:
                break

            component = np.where(labels == item["label"], 255, 0).astype(np.uint8)
            padded = (
                cv2.dilate(component, padding_kernel, iterations=1)
                if padding_kernel is not None
                else component
            )
            padded = np.where(selected > 0, 0, padded).astype(np.uint8)
            padded_pixels = int(np.count_nonzero(padded))

            selected_component = padded
            selected_pixels = padded_pixels
            if selected_pixels > remaining_budget:
                unpadded = np.where(selected > 0, 0, component).astype(np.uint8)
                unpadded_pixels = int(np.count_nonzero(unpadded))
                if unpadded_pixels > remaining_budget:
                    continue
                selected_component = unpadded
                selected_pixels = unpadded_pixels

            if selected_pixels <= 0:
                continue

            selected = np.maximum(selected, selected_component)
            remaining_budget -= selected_pixels
            kept_components.append(
                {
                    "x": item["x"],
                    "y": item["y"],
                    "width": item["width"],
                    "height": item["height"],
                    "source_pixels": item["area"],
                    "selected_pixels": selected_pixels,
                    "compactness": round(item["compactness"], 6),
                }
            )

        selected_mask = Image.fromarray(selected, mode="L")
        final_mask = ImageChops.lighter(mandatory, selected_mask)

        mandatory_pixels = self._pixel_count(mandatory)
        selected_pixels = self._pixel_count(selected_mask)
        final_pixels = self._pixel_count(final_mask)
        raw_semantic_pixels = self._pixel_count(semantic)

        return final_mask, {
            "localization_policy": "connected-components-soft-clamp",
            "semantic_component_candidates": len(candidates),
            "kept_component_count": len(kept_components),
            "kept_components": kept_components,
            "semantic_budget_pixels": semantic_budget,
            "selected_semantic_pixels": selected_pixels,
            "suppressed_semantic_pixels": max(0, raw_semantic_pixels - selected_pixels),
            "mandatory_edit_pixels": mandatory_pixels,
            "final_edit_pixels": final_pixels,
            "final_edit_ratio": round(final_pixels / float(total_pixels), 6),
            "global_generation_suppressed": raw_semantic_pixels > selected_pixels,
        }

    @staticmethod
    def _unfilled_statistics(candidate: Image.Image, edit_mask: Image.Image) -> dict[str, Any]:
        editable = edit_mask.convert("L").point(
            lambda value: 255 if value >= 128 else 0,
            mode="L",
        )
        editable_pixels = int(sum(editable.histogram()[128:]))
        near_black = candidate.convert("RGB").convert("L").point(
            lambda value: 255 if value <= 4 else 0,
            mode="L",
        )
        black_pixels = int(sum(ImageChops.multiply(near_black, editable).histogram()[128:]))
        ratio = black_pixels / float(max(1, editable_pixels))
        return {
            "editable_pixels": editable_pixels,
            "unfilled_editable_pixels": black_pixels,
            "unfilled_editable_ratio": round(ratio, 6),
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
        generated_path = output_dir / "nano-banana-remapped.png"
        generated_master.save(generated_path, format="PNG", optimize=False)

        with Image.open(geometry_image) as approved_source:
            approved_rgba = ImageOps.exif_transpose(approved_source).convert("RGBA")
        if approved_rgba.size != (width, height):
            raise AIEngineError(
                "Утверждённое изображение не соответствует размеру master canvas.",
                details={"approved_size": approved_rgba.size, "master_size": (width, height)},
            )
        approved_rgb = approved_rgba.convert("RGB")

        effective_mask_path = Path(prepared.get("effective_mask_path") or outpaint_mask)
        with Image.open(effective_mask_path) as mask_source:
            mandatory_mask = ImageOps.exif_transpose(mask_source).convert("L").point(
                lambda value: 255 if value >= 128 else 0,
                mode="L",
            )
        if mandatory_mask.size != (width, height):
            raise AIEngineError(
                "Маска редактирования не соответствует размеру master canvas.",
                details={"mask_size": mandatory_mask.size, "master_size": (width, height)},
            )

        semantic_mask, semantic = self._semantic_change_mask(
            generated_master,
            approved_rgb,
            mandatory_mask,
        )
        raw_semantic_mask_path = output_dir / "raw-semantic-change-mask.png"
        semantic_mask.save(raw_semantic_mask_path, format="PNG", optimize=False)

        final_edit_mask, localized = self._build_selective_edit_mask(
            semantic_mask,
            mandatory_mask,
        )
        final_mask_path = output_dir / "final-edit-mask.png"
        final_edit_mask.save(final_mask_path, format="PNG", optimize=False)

        # Главный контракт: итог всегда строится поверх утверждённого исходника.
        # Вне финальной локальной маски берутся исходные пиксели без изменений.
        candidate = Image.composite(generated_master, approved_rgb, final_edit_mask)
        candidate_path = output_dir / "candidate.png"
        candidate.save(candidate_path, format="PNG", optimize=False)

        outside_edit = ImageOps.invert(final_edit_mask)
        outside_difference = ImageChops.multiply(
            ImageChops.difference(candidate, approved_rgb).convert("L"),
            outside_edit,
        )
        outside_changed_pixels = int(sum(outside_difference.point(
            lambda value: 255 if value > 0 else 0,
            mode="L",
        ).histogram()[128:]))
        if outside_changed_pixels != 0:
            raise AIEngineError(
                "Нарушена защита исходника: обнаружены изменения вне целевой области.",
                details={
                    "reason": "pixel_preservation_failed",
                    "outside_changed_pixels": outside_changed_pixels,
                },
            )

        unfilled = self._unfilled_statistics(candidate, mandatory_mask)
        if (
            unfilled["editable_pixels"] > 0
            and unfilled["unfilled_editable_ratio"] > self.maximum_unfilled_ratio
        ):
            raise AIEngineError(
                "Nano Banana оставила незаполненные участки в обязательной области редактирования.",
                details={
                    "reason": "unfilled_mandatory_edit_area",
                    **unfilled,
                    "transport": prepared,
                    "candidate": str(candidate_path),
                },
            )

        return {
            "candidate": str(candidate_path),
            "environment_master": str(generated_path),
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
            "approved_geometry_preserved": True,
            "approved_geometry_used_as_immutable_base": True,
            "generation_mode": self.generation_mode,
            "provider_model": self.required_model,
            "raw_semantic_change_mask": str(raw_semantic_mask_path),
            "final_edit_mask": str(final_mask_path),
            "outside_changed_pixels": outside_changed_pixels,
            "pixel_preservation_verified": outside_changed_pixels == 0,
            **semantic,
            **localized,
            **unfilled,
        }


_engine_module.OpenRouterImageEngine = OpenRouterImageEngine
