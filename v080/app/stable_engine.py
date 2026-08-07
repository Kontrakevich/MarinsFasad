from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageChops, ImageFilter, ImageOps

from . import ai_engine as _engine_module
from .prompt_engine import FINAL_COMMAND_MARKER, OPERATOR_PROMPT_MARKER
from .system_prompts import ENVIRONMENT_SYSTEM_PROMPT, PROMPT_CONTRACT_VERSION


_BaseOpenRouterImageEngine = _engine_module.OpenRouterImageEngine
AIEngineError = _engine_module.AIEngineError


class OpenRouterImageEngine(_BaseOpenRouterImageEngine):
    """Single runtime engine for v0.8.

    Contract:
    - the user approves only the corrected geometry image;
    - missing surroundings are detected from its alpha channel;
    - Nano Banana is the only image model;
    - the UI-compiled prompt is sent verbatim;
    - Nano Banana receives one visual reference;
    - existing source pixels are restored outside automatic outpaint and compact
      prompt-driven local changes.

    Older policy modules are intentionally not part of the runtime chain.
    """

    transport_engine_version = "3.0.0"
    required_model = "google/gemini-2.5-flash-image"
    generation_mode = "automatic-outpaint-and-selective-edit"
    environment_input_policy = "approved-geometry-only"
    outpaint_detection_policy = "automatic-from-approved-geometry-transparency"
    provider_input_policy = "single-approved-geometry-reference"
    prompt_transport_policy = "ui-compiled-prompt-sent-verbatim"
    user_mask_required = False

    # Stable single-pass policy. These compatibility attributes are retained so
    # diagnostics/tests from previous builds can still inspect the engine without
    # activating the old tiled-repair pipeline.
    internal_outpaint_tiles_allowed = False
    outpaint_repair_mode = "single-pass"
    outpaint_tile_max_calls = 0
    outpaint_tile_planner = "disabled"
    missing_region_transport_policy = "opaque-marker-single-pass"
    outpaint_qc_blocking = False
    outpaint_qc_policy = "warning-only"

    semantic_difference_threshold = 32
    minimum_component_pixels = 96
    maximum_component_edit_ratio = 0.08
    maximum_component_bbox_ratio = 0.25
    maximum_total_selective_edit_ratio = 0.15
    maximum_component_count = 12
    component_padding_px = 4

    def __init__(self) -> None:
        super().__init__()
        self.model = self.required_model

    @staticmethod
    def _prompt_sha256(prompt: str) -> str:
        return hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    @staticmethod
    def _clean_prompt(prompt: str) -> str:
        exact = str(prompt or "").strip()
        if not exact:
            raise AIEngineError(
                "Промпт генерации пустой.",
                details={
                    "reason": "empty_generation_prompt",
                    "provider_call_made": False,
                    "credits_spent": False,
                },
            )
        return exact

    def _provider_prompt(self, prompt: str) -> tuple[str, bool]:
        exact = self._clean_prompt(prompt)
        is_ui_compiled = (
            OPERATOR_PROMPT_MARKER in exact
            and FINAL_COMMAND_MARKER in exact
        )
        if is_ui_compiled or ENVIRONMENT_SYSTEM_PROMPT in exact:
            return exact, is_ui_compiled
        return (
            f"SYSTEM PROMPT — {PROMPT_CONTRACT_VERSION}\n"
            f"{ENVIRONMENT_SYSTEM_PROMPT}\n\n"
            "PROJECT EXECUTION PROMPT\n"
            f"{exact}",
            False,
        )

    @staticmethod
    def _project_root_from_geometry(geometry_image: Path) -> Path | None:
        resolved = Path(geometry_image).resolve()
        for parent in resolved.parents:
            if (parent / "project.json").is_file():
                return parent
        return None

    def _approval_contract(self, geometry_image: Path) -> dict[str, Any]:
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
                "Не удалось прочитать состояние проекта. Генерация не запущена.",
                details={
                    "reason": "approval_state_unreadable",
                    "provider_call_made": False,
                    "credits_spent": False,
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
                "Для генерации нужен утверждённый результат коррекции геометрии.",
                details={
                    "reason": "geometry_not_approved",
                    "provider_call_made": False,
                    "credits_spent": False,
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
    def _derive_outpaint_plan(geometry_image: Path, destination: Path) -> tuple[Path, dict[str, Any]]:
        with Image.open(geometry_image) as source:
            geometry = ImageOps.exif_transpose(source).convert("RGBA")
        alpha = np.asarray(geometry.getchannel("A"), dtype=np.uint8)
        missing = np.where(alpha < 250, 255, 0).astype(np.uint8)
        missing = cv2.morphologyEx(
            missing,
            cv2.MORPH_CLOSE,
            np.ones((3, 3), dtype=np.uint8),
            iterations=1,
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(missing, mode="L").save(destination, format="PNG", optimize=False)
        missing_pixels = int(np.count_nonzero(missing))
        total_pixels = max(1, geometry.width * geometry.height)
        return destination, {
            "missing_pixels": missing_pixels,
            "missing_ratio": round(missing_pixels / float(total_pixels), 6),
            "outpaint_required": missing_pixels > 0,
            "outpaint_detection": "automatic-from-approved-geometry-transparency",
        }

    @staticmethod
    def _missing_region_marker(size: tuple[int, int]) -> Image.Image:
        width, height = size
        y, x = np.indices((height, width))
        checker = ((x // 16 + y // 16) % 2).astype(np.uint8)
        array = np.zeros((height, width, 3), dtype=np.uint8)
        array[checker == 0] = (255, 0, 255)
        array[checker == 1] = (0, 255, 255)
        return Image.fromarray(array, mode="RGB")

    @classmethod
    def _reference_canvases(
        cls,
        geometry_master: Image.Image,
        mask_master: Image.Image,
        reference_size: tuple[int, int],
    ) -> tuple[Image.Image, Image.Image, tuple[int, int, int, int]]:
        left, top, content_width, content_height = cls._fit_content_box(
            geometry_master.size,
            reference_size,
        )
        geometry_resized = geometry_master.convert("RGBA").resize(
            (content_width, content_height),
            Image.Resampling.LANCZOS,
        )
        private_plan = mask_master.convert("L").resize(
            (content_width, content_height),
            Image.Resampling.NEAREST,
        ).point(lambda value: 255 if value >= 128 else 0, mode="L")
        alpha_missing = geometry_resized.getchannel("A").point(
            lambda value: 255 if value < 250 else 0,
            mode="L",
        )
        missing = ImageChops.lighter(private_plan, alpha_missing)

        base_rgb = geometry_resized.convert("RGB")
        marker = cls._missing_region_marker((content_width, content_height))
        marked = Image.composite(marker, base_rgb, missing)

        geometry_canvas = cls._missing_region_marker(reference_size)
        geometry_canvas.paste(marked, (left, top))
        plan_canvas = Image.new("L", reference_size, 0)
        plan_canvas.paste(missing, (left, top))
        return geometry_canvas, plan_canvas, (left, top, content_width, content_height)

    def _build_payload(
        self,
        *,
        prompt: str,
        geometry_image: Path,
        outpaint_mask: Path,
        provider_size: tuple[int, int],
    ) -> dict:
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
                    "image_url": {"url": self._data_url(Path(geometry_image))},
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
        geometry_image = Path(geometry_image)
        output_dir = Path(output_dir)
        if not geometry_image.is_file():
            raise AIEngineError(
                "Не найден утверждённый результат коррекции геометрии.",
                details={"provider_call_made": False, "credits_spent": False},
            )
        approval = self._approval_contract(geometry_image)
        private_plan, outpaint_stats = self._derive_outpaint_plan(
            geometry_image,
            output_dir / "automatic-outpaint-plan.png",
        )
        exact_prompt = self._clean_prompt(prompt)
        provider_prompt, is_ui_compiled = self._provider_prompt(exact_prompt)

        prepared = super().prepare_environment_inputs(
            prompt=exact_prompt,
            geometry_image=geometry_image,
            outpaint_mask=private_plan,
            output_dir=output_dir,
            width=width,
            height=height,
            forced_max_request_bytes=forced_max_request_bytes,
            forced_target_request_bytes=forced_target_request_bytes,
            supported_sizes=supported_sizes,
        )
        sent_prompt_path = output_dir / "compiled-prompt-sent.txt"
        sent_prompt_path.write_text(provider_prompt + "\n", "utf-8")
        prepared.update(approval)
        prepared.update(outpaint_stats)
        prepared.update(
            {
                "model": self.required_model,
                "model_lock": "nano-banana-only",
                "transport_engine_version": self.transport_engine_version,
                "generation_mode": self.generation_mode,
                "environment_input_policy": self.environment_input_policy,
                "outpaint_detection": self.outpaint_detection_policy,
                "provider_input_policy": self.provider_input_policy,
                "provider_reference_count": 1,
                "input_reference_count": 1,
                "user_outpaint_file_required": False,
                "pixel_preservation_required": True,
                "effective_mask_path": str(private_plan),
                "system_prompt_contract": PROMPT_CONTRACT_VERSION,
                "prompt_transport_policy": self.prompt_transport_policy,
                "compiled_prompt_ui": exact_prompt,
                "compiled_prompt_sent": provider_prompt,
                "compiled_prompt_sent_path": str(sent_prompt_path),
                "compiled_prompt_ui_sha256": self._prompt_sha256(exact_prompt),
                "compiled_prompt_sent_sha256": self._prompt_sha256(provider_prompt),
                "ui_compiled_prompt": is_ui_compiled,
                "prompt_match": exact_prompt == provider_prompt,
            }
        )
        (output_dir / "transport.json").write_text(
            json.dumps(prepared, ensure_ascii=False, indent=2),
            "utf-8",
        )
        return prepared

    @staticmethod
    def _pixel_count(mask: Image.Image) -> int:
        binary = mask.convert("L").point(lambda v: 255 if v >= 128 else 0, mode="L")
        return int(sum(binary.histogram()[128:]))

    def _local_change_mask(
        self,
        generated: Image.Image,
        approved: Image.Image,
        outpaint_plan: Image.Image,
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
        ).filter(ImageFilter.MedianFilter(3))

        mandatory = outpaint_plan.convert("L").point(
            lambda value: 255 if value >= 128 else 0,
            mode="L",
        )
        changed = ImageChops.multiply(changed, ImageOps.invert(mandatory))
        array = np.asarray(changed, dtype=np.uint8)
        array = cv2.morphologyEx(
            array,
            cv2.MORPH_OPEN,
            np.ones((3, 3), dtype=np.uint8),
            iterations=1,
        )
        array = cv2.morphologyEx(
            array,
            cv2.MORPH_CLOSE,
            np.ones((3, 3), dtype=np.uint8),
            iterations=1,
        )

        labels_count, labels, stats, _ = cv2.connectedComponentsWithStats(array, connectivity=8)
        height, width = array.shape
        total_pixels = max(1, width * height)
        budget = int(total_pixels * self.maximum_total_selective_edit_ratio)
        selected = np.zeros_like(array, dtype=np.uint8)
        selected_components: list[dict[str, Any]] = []

        candidates: list[tuple[int, int, int, int, int, int]] = []
        for label_index in range(1, labels_count):
            x, y, box_width, box_height, area = [int(v) for v in stats[label_index]]
            if area < self.minimum_component_pixels:
                continue
            if area / float(total_pixels) > self.maximum_component_edit_ratio:
                continue
            if (box_width * box_height) / float(total_pixels) > self.maximum_component_bbox_ratio:
                continue
            candidates.append((area, label_index, x, y, box_width, box_height))
        candidates.sort(reverse=True)

        remaining = budget
        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE,
            (self.component_padding_px * 2 + 1, self.component_padding_px * 2 + 1),
        )
        for area, label_index, x, y, box_width, box_height in candidates:
            if len(selected_components) >= self.maximum_component_count or remaining <= 0:
                break
            component = np.where(labels == label_index, 255, 0).astype(np.uint8)
            component = cv2.dilate(component, kernel, iterations=1)
            component = np.where(selected > 0, 0, component).astype(np.uint8)
            pixels = int(np.count_nonzero(component))
            if pixels <= 0 or pixels > remaining:
                continue
            selected = np.maximum(selected, component)
            remaining -= pixels
            selected_components.append(
                {
                    "x": x,
                    "y": y,
                    "width": box_width,
                    "height": box_height,
                    "source_pixels": area,
                    "selected_pixels": pixels,
                }
            )

        selected_mask = Image.fromarray(selected, mode="L")
        return selected_mask, {
            "selected_local_component_count": len(selected_components),
            "selected_local_components": selected_components,
            "selected_local_pixels": self._pixel_count(selected_mask),
            "local_edit_budget_pixels": budget,
        }

    @classmethod
    def _placeholder_analysis(
        cls,
        candidate: Image.Image,
        outpaint_plan: Image.Image,
    ) -> tuple[Image.Image, dict[str, Any]]:
        plan = np.asarray(
            outpaint_plan.convert("L").point(lambda v: 255 if v >= 128 else 0, mode="L"),
            dtype=np.uint8,
        )
        editable = plan > 0
        editable_pixels = int(np.count_nonzero(editable))
        empty_mask = Image.new("L", candidate.size, 0)
        if editable_pixels == 0:
            return empty_mask, {
                "outpaint_reconstructed": True,
                "placeholder_component_count": 0,
                "placeholder_ratio": 0.0,
                "solid_white_is_valid_outpaint": False,
            }

        rgb = np.asarray(candidate.convert("RGB"), dtype=np.uint8)
        values = rgb[editable]
        white = np.all(values >= 248, axis=1)
        black = np.all(values <= 7, axis=1)
        magenta = (values[:, 0] >= 235) & (values[:, 1] <= 25) & (values[:, 2] >= 235)
        cyan = (values[:, 0] <= 25) & (values[:, 1] >= 235) & (values[:, 2] >= 235)
        suspicious = white | black | magenta | cyan
        suspicious_ratio = float(np.count_nonzero(suspicious)) / float(max(1, editable_pixels))
        channel_std = float(np.mean(np.std(values.astype(np.float32), axis=0))) if len(values) else 0.0
        flat = channel_std < 2.0
        reconstructed = suspicious_ratio < 0.85 and not flat

        suspicious_full = np.zeros(plan.shape, dtype=np.uint8)
        suspicious_full[editable] = np.where(suspicious, 255, 0).astype(np.uint8)
        count, _, stats, _ = cv2.connectedComponentsWithStats(suspicious_full, connectivity=8)
        components = 0
        for index in range(1, count):
            if int(stats[index, cv2.CC_STAT_AREA]) >= 64:
                components += 1
        return Image.fromarray(suspicious_full, mode="L"), {
            "outpaint_reconstructed": reconstructed,
            "placeholder_component_count": components,
            "placeholder_ratio": round(suspicious_ratio, 6),
            "outpaint_texture_std": round(channel_std, 6),
            "solid_white_is_valid_outpaint": False,
        }

    def _outpaint_reconstruction_statistics(self, candidate_path: Path, plan_path: Path) -> dict[str, Any]:
        with Image.open(candidate_path) as candidate_source, Image.open(plan_path) as plan_source:
            _, stats = self._placeholder_analysis(
                candidate_source.convert("RGB"),
                plan_source.convert("L"),
            )
        return stats

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
        environment_master_path = output_dir / "nano-banana-remapped.png"
        generated_master.save(environment_master_path, format="PNG", optimize=False)

        with Image.open(geometry_image) as geometry_source:
            approved_rgba = ImageOps.exif_transpose(geometry_source).convert("RGBA")
        if approved_rgba.size != (width, height):
            raise AIEngineError(
                "Результат коррекции геометрии не соответствует размеру исходного холста.",
                details={"geometry_size": approved_rgba.size, "master_size": (width, height)},
            )
        approved_rgb = approved_rgba.convert("RGB")

        plan_path = Path(prepared.get("effective_mask_path") or outpaint_mask)
        with Image.open(plan_path) as plan_source:
            outpaint_plan = ImageOps.exif_transpose(plan_source).convert("L").point(
                lambda value: 255 if value >= 128 else 0,
                mode="L",
            )
        if outpaint_plan.size != (width, height):
            raise AIEngineError(
                "Внутренний план outpaint не соответствует размеру исходного холста.",
                details={"plan_size": outpaint_plan.size, "master_size": (width, height)},
            )

        local_mask, local_stats = self._local_change_mask(
            generated_master,
            approved_rgb,
            outpaint_plan,
        )
        final_edit = ImageChops.lighter(outpaint_plan, local_mask)
        candidate = Image.composite(generated_master, approved_rgb, final_edit)
        candidate_path = output_dir / "candidate.png"
        candidate.save(candidate_path, format="PNG", optimize=False)

        outside = ImageOps.invert(final_edit)
        outside_difference = ImageChops.multiply(
            ImageChops.difference(candidate, approved_rgb).convert("L"),
            outside,
        )
        outside_changed_pixels = self._pixel_count(
            outside_difference.point(lambda value: 255 if value > 0 else 0, mode="L")
        )
        if outside_changed_pixels:
            raise AIEngineError(
                "Не удалось гарантировать сохранность исходного изображения вне области изменений.",
                details={
                    "reason": "pixel_preservation_failed",
                    "outside_changed_pixels": outside_changed_pixels,
                },
            )

        diagnostic_plan_path = output_dir / "automatic-outpaint-plan.png"
        outpaint_plan.save(diagnostic_plan_path, format="PNG", optimize=False)
        final_edit_path = output_dir / "final-edit-area.png"
        final_edit.save(final_edit_path, format="PNG", optimize=False)
        _, reconstruction = self._placeholder_analysis(candidate, outpaint_plan)

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
            "approved_geometry_preserved": True,
            "pixel_preservation_verified": True,
            "outside_changed_pixels": outside_changed_pixels,
            "automatic_outpaint_plan": str(diagnostic_plan_path),
            "final_edit_area": str(final_edit_path),
            **local_stats,
            **reconstruction,
        }

    # Compatibility-only helper for old diagnostic tests. Runtime does not split
    # the request into additional billable tile calls anymore.
    def _component_tile_boxes(self, mask: Image.Image) -> list[dict[str, Any]]:
        binary = np.asarray(
            mask.convert("L").point(lambda v: 255 if v >= 128 else 0, mode="L"),
            dtype=np.uint8,
        )
        count, _, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
        output: list[dict[str, Any]] = []
        for index in range(1, count):
            x, y, width, height, area = [int(v) for v in stats[index]]
            output.append(
                {
                    "crop_box": (x, y, x + width, y + height),
                    "mask_pixels": area,
                    "grid_row": 0,
                    "grid_column": 0,
                }
            )
        return output

    def _tile_prompt(self, original_prompt: str, tile_index: int) -> str:
        return (
            f"Служебная диагностика outpaint {tile_index}. "
            "Дорисуй отсутствующее окружение и точно выполни исходный промпт:\n"
            f"{original_prompt}"
        )

    def generate_environment(self, **kwargs) -> dict:
        prompt = self._clean_prompt(kwargs.get("prompt", ""))
        kwargs["prompt"] = prompt
        try:
            result = super().generate_environment(**kwargs)
        except AIEngineError as exc:
            text = str(exc)
            if text.startswith("OPENROUTER_API_KEY"):
                raise AIEngineError(
                    "Не настроен ключ OpenRouter API.",
                    details=getattr(exc, "details", {}),
                ) from exc
            if text.startswith("OpenRouter") or "OpenRouter returned" in text:
                details = dict(getattr(exc, "details", {}) or {})
                details["provider_error"] = text
                raise AIEngineError(
                    "Nano Banana не смогла выполнить генерацию через OpenRouter. Подробности сохранены в диагностике.",
                    details=details,
                ) from exc
            raise

        sent_prompt = str((result.get("request") or {}).get("prompt") or "")
        provider_prompt, is_ui_compiled = self._provider_prompt(prompt)
        if sent_prompt != provider_prompt:
            raise AIEngineError(
                "Промпт был изменён перед отправкой в Nano Banana. Результат не принят.",
                details={
                    "reason": "prompt_transport_mismatch",
                    "ui_prompt_sha256": self._prompt_sha256(prompt),
                    "sent_prompt_sha256": self._prompt_sha256(sent_prompt) if sent_prompt else "",
                    "provider_call_made": True,
                },
            )
        if is_ui_compiled and sent_prompt != prompt:
            raise AIEngineError(
                "Собранный в интерфейсе промпт не был отправлен в Nano Banana дословно.",
                details={"reason": "ui_prompt_not_sent_verbatim"},
            )
        result.update(
            {
                "prompt_match": sent_prompt == prompt,
                "compiled_prompt_sent": sent_prompt,
                "sent_prompt_sha256": self._prompt_sha256(sent_prompt),
                "prompt_transport_policy": self.prompt_transport_policy,
                "provider_input_policy": self.provider_input_policy,
                "provider_reference_count": 1,
                "generation_mode": self.generation_mode,
            }
        )
        output_dir = Path(kwargs["output_dir"])
        (output_dir / "generation.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            "utf-8",
        )
        return result


_engine_module.OpenRouterImageEngine = OpenRouterImageEngine
