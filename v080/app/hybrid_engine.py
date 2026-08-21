from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageChops, ImageOps

from . import ai_engine as _engine_module
from .prompt_engine import (
    FINAL_COMMAND_MARKER,
    GENERATION_MODE_MARKER,
    OPERATOR_PROMPT_MARKER,
    VALID_GENERATION_MODES,
)
from .system_prompts import ENVIRONMENT_SYSTEM_PROMPT, PROMPT_CONTRACT_VERSION


_BaseOpenRouterImageEngine = _engine_module.OpenRouterImageEngine
AIEngineError = _engine_module.AIEngineError


class OpenRouterImageEngine(_BaseOpenRouterImageEngine):
    """Single active v0.8.1 runtime: strong image edit + automatic outpaint.

    EDIT performs one strong semantic image-edit pass.
    OUTPAINT reconstructs only missing transparent regions and preserves all
    existing visible pixels exactly.
    HYBRID performs the primary semantic edit first, reapplies the original
    missing-alpha geometry, then runs a dedicated OUTPAINT-only second pass.
    """

    transport_engine_version = "3.2.0"
    required_model = "google/gemini-2.5-flash-image"
    default_generation_mode = "hybrid"
    generation_mode = "hybrid"
    available_generation_modes = ("hybrid", "edit", "outpaint")
    environment_input_policy = "approved-geometry-only"
    outpaint_detection_policy = "automatic-from-approved-geometry-transparency"
    provider_input_policy = "single-approved-geometry-reference"
    prompt_transport_policy = "primary-ui-prompt-verbatim-plus-internal-outpaint-pass"
    user_mask_required = False
    internal_outpaint_tiles_allowed = False
    outpaint_repair_mode = "hybrid-second-pass"
    outpaint_tile_max_calls = 0
    outpaint_tile_planner = "disabled"
    missing_region_transport_policy = "native-transparency-single-reference"
    outpaint_qc_blocking = True
    outpaint_qc_policy = "reject-solid-white-black-placeholder"

    _runtime = threading.local()

    def __init__(self) -> None:
        super().__init__()
        self.model = self.required_model

    @staticmethod
    def _prompt_sha256(prompt: str) -> str:
        return hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    @classmethod
    def _normalize_generation_mode(cls, value: str | None) -> str:
        mode = str(value or "").strip().lower()
        return mode if mode in VALID_GENERATION_MODES else cls.default_generation_mode

    @classmethod
    def _mode_from_prompt(cls, prompt: str) -> str:
        text = str(prompt or "")
        marker = f"{GENERATION_MODE_MARKER}\n"
        index = text.find(marker)
        if index >= 0:
            remainder = text[index + len(marker):]
            first_line = remainder.splitlines()[0].strip().lower() if remainder else ""
            if first_line in VALID_GENERATION_MODES:
                return first_line
        for mode in cls.available_generation_modes:
            if f"Generation mode: {mode.upper()}" in text:
                return mode
        return cls.default_generation_mode

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
        is_ui_compiled = OPERATOR_PROMPT_MARKER in exact and FINAL_COMMAND_MARKER in exact
        # A prompt containing an explicit generation-mode marker is already a
        # complete execution contract. Never prepend another conflicting mode.
        if is_ui_compiled or ENVIRONMENT_SYSTEM_PROMPT in exact or GENERATION_MODE_MARKER in exact:
            return exact, is_ui_compiled
        return (
            f"SYSTEM PROMPT — {PROMPT_CONTRACT_VERSION}\n"
            f"{ENVIRONMENT_SYSTEM_PROMPT}\n\n"
            f"{GENERATION_MODE_MARKER}\nHYBRID\n\n"
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
        expected_geometry = (project_root / expected_rel).resolve() if expected_rel else None
        received = geometry_image.resolve()
        internal_geometry = getattr(self._runtime, "internal_geometry", None)
        internal_allowed = bool(
            internal_geometry
            and Path(internal_geometry).resolve() == received
            and geometry_status == "approved"
            and pipeline_status == "approved"
        )
        exact_approved = bool(
            geometry_status == "approved"
            and pipeline_status == "approved"
            and expected_geometry == received
        )
        if not (exact_approved or internal_allowed):
            raise AIEngineError(
                "Для генерации нужен утверждённый результат коррекции геометрии.",
                details={
                    "reason": "geometry_not_approved",
                    "provider_call_made": False,
                    "credits_spent": False,
                    "geometry_status": geometry_status,
                    "pipeline_status": pipeline_status,
                    "expected_geometry": str(expected_geometry) if expected_geometry else None,
                    "received_geometry": str(received),
                },
            )
        return {
            "approval_verified": True,
            "approval_source": "internal-hybrid-intermediate" if internal_allowed else "project.json",
            "project_id": state.get("id"),
            "geometry_status": geometry_status,
            "pipeline_status": pipeline_status,
            "environment_input_policy": self.environment_input_policy,
        }

    @staticmethod
    def _derive_outpaint_plan(
        geometry_image: Path,
        destination: Path,
    ) -> tuple[Path, dict[str, Any]]:
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
        geometry_canvas = Image.new("RGBA", reference_size, (0, 0, 0, 0))
        geometry_canvas.paste(geometry_resized, (left, top))
        plan_canvas = Image.new("L", reference_size, 0)
        plan_canvas.paste(private_plan, (left, top))
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
                }
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
        requested_mode = self._mode_from_prompt(exact_prompt)
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
                "generation_mode": requested_mode,
                "requested_generation_mode": requested_mode,
                "available_generation_modes": list(self.available_generation_modes),
                "environment_input_policy": self.environment_input_policy,
                "outpaint_detection": self.outpaint_detection_policy,
                "provider_input_policy": self.provider_input_policy,
                "provider_reference_count": 1,
                "input_reference_count": 1,
                "user_outpaint_file_required": False,
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
                "visual_reference_policy": "native-alpha-no-service-pattern",
            }
        )
        (output_dir / "transport.json").write_text(
            json.dumps(prepared, ensure_ascii=False, indent=2),
            "utf-8",
        )
        return prepared

    @staticmethod
    def _pixel_count(mask: Image.Image) -> int:
        binary = mask.convert("L").point(lambda value: 255 if value >= 128 else 0, mode="L")
        return int(sum(binary.histogram()[128:]))

    @staticmethod
    def _outpaint_placeholder_stats(candidate: Image.Image, plan: Image.Image) -> dict[str, Any]:
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
                "outpaint_placeholder_detected": False,
            }
        rgb = np.asarray(candidate.convert("RGB"), dtype=np.uint8)
        values = rgb[editable]
        white_ratio = float(np.count_nonzero(np.all(values >= 248, axis=1))) / float(editable_pixels)
        black_ratio = float(np.count_nonzero(np.all(values <= 7, axis=1))) / float(editable_pixels)
        detected = white_ratio >= 0.95 or black_ratio >= 0.95
        return {
            "outpaint_checked_pixels": editable_pixels,
            "solid_white_ratio": round(white_ratio, 6),
            "solid_black_ratio": round(black_ratio, 6),
            "outpaint_placeholder_detected": detected,
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
        crop_box = self._provider_crop_box(provider_actual_size, prepared["content_box_normalized"])
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
            outside_changed_pixels = self._pixel_count(
                outside_difference.point(lambda value: 255 if value > 0 else 0, mode="L")
            )
            if outside_changed_pixels:
                raise AIEngineError(
                    "Не удалось сохранить результат edit вне областей outpaint.",
                    details={
                        "reason": "outpaint_pixel_preservation_failed",
                        "outside_changed_pixels": outside_changed_pixels,
                    },
                )
            placeholder = self._outpaint_placeholder_stats(candidate, outpaint_plan)
            if placeholder["outpaint_placeholder_detected"]:
                raise AIEngineError(
                    "Nano Banana не реконструировала отсутствующие участки изображения: обнаружена сплошная белая или чёрная заливка.",
                    details={
                        "reason": "outpaint_placeholder_detected",
                        **placeholder,
                    },
                )
            full_frame_semantic_edit = False
            preservation_policy = "pixel-exact-outside-missing-regions"
        else:
            candidate = generated_master
            outside_changed_pixels = None
            placeholder = {
                "outpaint_checked_pixels": 0,
                "solid_white_ratio": 0.0,
                "solid_black_ratio": 0.0,
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
            "strong_image_edit_enabled": requested_mode in {"hybrid", "edit"},
            **placeholder,
        }

    @staticmethod
    def _operator_block(prompt: str) -> str:
        text = str(prompt or "")
        if OPERATOR_PROMPT_MARKER not in text:
            return text.strip()
        start = text.index(OPERATOR_PROMPT_MARKER) + len(OPERATOR_PROMPT_MARKER)
        end = text.find(GENERATION_MODE_MARKER, start)
        return text[start:end if end >= 0 else None].strip()

    def _internal_outpaint_prompt(self, primary_prompt: str) -> str:
        operator = self._operator_block(primary_prompt)
        return (
            "INTERNAL HYBRID PASS 2/2 — OUTPAINT ONLY\n"
            "The supplied image is the completed semantic image-edit result. Existing visible pixels, weather, lighting, object removals and all operator edits are final and immutable.\n"
            "Only reconstruct pixels where the supplied image has no visual information: transparent regions created by perspective correction.\n"
            "Continue adjacent sky, facade edges, buildings, pavement, vegetation, shadows and urban context photorealistically with matching perspective and lighting.\n"
            "Do not undo, reinterpret, recolour or geometrically modify any existing visible area. Do not return blank, white, black or flat-colour wedges.\n\n"
            f"{GENERATION_MODE_MARKER}\nOUTPAINT\n\n"
            "ORIGINAL OPERATOR REQUEST — CONTEXT ONLY, ALREADY EXECUTED IN PASS 1\n"
            f"{operator}"
        )

    @staticmethod
    def _reapply_geometry_alpha(edit_candidate: Path, geometry_image: Path, destination: Path) -> Path:
        with Image.open(edit_candidate) as edit_source:
            edited = ImageOps.exif_transpose(edit_source).convert("RGBA")
        with Image.open(geometry_image) as geometry_source:
            geometry = ImageOps.exif_transpose(geometry_source).convert("RGBA")
        if edited.size != geometry.size:
            raise AIEngineError(
                "Промежуточный результат image edit не совпадает с рабочим холстом.",
                details={"edit_size": edited.size, "geometry_size": geometry.size},
            )
        edited.putalpha(geometry.getchannel("A"))
        destination.parent.mkdir(parents=True, exist_ok=True)
        edited.save(destination, format="PNG", optimize=False)
        return destination

    def _verify_sent_prompt(self, result: dict, prompt: str) -> None:
        sent_prompt = str((result.get("request") or {}).get("prompt") or "")
        provider_prompt, _ = self._provider_prompt(prompt)
        if sent_prompt != provider_prompt:
            raise AIEngineError(
                "Промпт был изменён перед отправкой в Nano Banana. Результат не принят.",
                details={
                    "reason": "prompt_transport_mismatch",
                    "expected_sha256": self._prompt_sha256(provider_prompt),
                    "sent_sha256": self._prompt_sha256(sent_prompt) if sent_prompt else "",
                    "provider_call_made": True,
                },
            )

    def _single_pass(self, **kwargs) -> dict:
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
        self._verify_sent_prompt(result, prompt)
        return result

    def generate_environment(self, **kwargs) -> dict:
        primary_prompt = self._clean_prompt(kwargs.get("prompt", ""))
        kwargs["prompt"] = primary_prompt
        requested_mode = self._mode_from_prompt(primary_prompt)
        output_dir = Path(kwargs["output_dir"])
        width = int(kwargs["width"])
        height = int(kwargs["height"])
        geometry_image = Path(kwargs["geometry_image"])

        primary = self._single_pass(**kwargs)
        primary.update(
            {
                "primary_prompt_match": True,
                "primary_prompt_sha256": self._prompt_sha256(primary_prompt),
                "requested_generation_mode": requested_mode,
                "generation_mode": requested_mode,
                "strong_image_edit_enabled": requested_mode in {"hybrid", "edit"},
            }
        )

        prepared = kwargs.get("prepared_input") or {}
        outpaint_required = bool(prepared.get("outpaint_required"))
        if requested_mode != "hybrid" or not outpaint_required:
            primary["provider_call_count"] = 1
            primary["hybrid_two_pass"] = False
            primary["outpaint_second_pass_skipped"] = requested_mode == "hybrid" and not outpaint_required
            (output_dir / "generation.json").write_text(
                json.dumps(primary, ensure_ascii=False, indent=2),
                "utf-8",
            )
            return primary

        intermediate = self._reapply_geometry_alpha(
            Path(primary["candidate"]),
            geometry_image,
            output_dir / "hybrid" / "edit-result-with-original-missing-alpha.png",
        )
        outpaint_prompt = self._internal_outpaint_prompt(primary_prompt)
        second_dir = output_dir / "hybrid" / "outpaint-pass"
        self._runtime.internal_geometry = str(intermediate.resolve())
        try:
            second_prepared = self.prepare_environment_inputs(
                prompt=outpaint_prompt,
                geometry_image=intermediate,
                outpaint_mask=Path(kwargs["outpaint_mask"]),
                output_dir=second_dir / "transport",
                width=width,
                height=height,
            )
            second = self._single_pass(
                prompt=outpaint_prompt,
                geometry_image=intermediate,
                outpaint_mask=Path(kwargs["outpaint_mask"]),
                output_dir=second_dir,
                width=width,
                height=height,
                prepared_input=second_prepared,
            )
        finally:
            self._runtime.internal_geometry = None

        result = dict(second)
        result.update(
            {
                "generation_mode": "hybrid",
                "requested_generation_mode": "hybrid",
                "hybrid_two_pass": True,
                "provider_call_count": 2,
                "strong_image_edit_enabled": True,
                "primary_prompt_match": True,
                "primary_prompt_sha256": self._prompt_sha256(primary_prompt),
                "primary_edit_candidate": primary.get("candidate"),
                "primary_duration_seconds": primary.get("duration_seconds"),
                "outpaint_duration_seconds": second.get("duration_seconds"),
                "duration_seconds": round(
                    float(primary.get("duration_seconds") or 0)
                    + float(second.get("duration_seconds") or 0),
                    3,
                ),
                "primary_usage": primary.get("usage") or {},
                "outpaint_usage": second.get("usage") or {},
                "primary_request": primary.get("request") or {},
                "outpaint_request": second.get("request") or {},
                "hybrid_intermediate": str(intermediate),
                "prompt_transport_policy": self.prompt_transport_policy,
                "provider_input_policy": self.provider_input_policy,
                "provider_reference_count": 1,
            }
        )
        (output_dir / "generation.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            "utf-8",
        )
        return result


_engine_module.OpenRouterImageEngine = OpenRouterImageEngine
