from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageFilter, ImageOps

from . import ai_engine as _engine_module
from .system_prompts import ENVIRONMENT_SYSTEM_PROMPT, PROMPT_CONTRACT_VERSION


_PreviousOpenRouterImageEngine = _engine_module.OpenRouterImageEngine
AIEngineError = _engine_module.AIEngineError


class OpenRouterImageEngine(_PreviousOpenRouterImageEngine):
    """Точечное редактирование с неизменяемой базой и единственной моделью Nano Banana."""

    transport_engine_version = "2.7.0"
    required_model = "google/gemini-2.5-flash-image"
    generation_mode = "selective-edit"
    minimum_editable_pixels = 64
    semantic_difference_threshold = 18
    maximum_semantic_edit_ratio = 0.25
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
            # Пустая обязательная маска допустима: Nano Banana может определить
            # локальный объект по тексту. Защита от глобального изменения работает
            # после получения результата через maximum_semantic_edit_ratio.
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
                "maximum_semantic_edit_ratio": self.maximum_semantic_edit_ratio,
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
        # Максимум по каналам лучше отделяет реальное изменение объекта от
        # незначительного цветового шума ресэмплинга.
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
        if semantic["semantic_edit_ratio"] > self.maximum_semantic_edit_ratio:
            raise AIEngineError(
                "Nano Banana попыталась изменить слишком большую часть исходного изображения. Результат отклонён, исходник сохранён.",
                details={
                    "reason": "semantic_edit_area_too_large",
                    "maximum_semantic_edit_ratio": self.maximum_semantic_edit_ratio,
                    **semantic,
                    "provider_output": str(provider_output),
                    "generated_diagnostic": str(generated_path),
                    "transport": prepared,
                },
            )

        final_edit_mask = ImageChops.lighter(mandatory_mask, semantic_mask)
        final_mask_path = output_dir / "final-edit-mask.png"
        final_edit_mask.save(final_mask_path, format="PNG", optimize=False)

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

        final_edit_pixels = self._pixel_count(final_edit_mask)
        total_pixels = width * height
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
            "final_edit_mask": str(final_mask_path),
            "final_edit_pixels": final_edit_pixels,
            "final_edit_ratio": round(final_edit_pixels / float(max(1, total_pixels)), 6),
            "outside_changed_pixels": outside_changed_pixels,
            "pixel_preservation_verified": outside_changed_pixels == 0,
            **semantic,
            **unfilled,
        }


_engine_module.OpenRouterImageEngine = OpenRouterImageEngine
