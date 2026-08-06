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
    """Политика полноформатной генерации по утверждённой геометрии."""

    transport_engine_version = "2.6.0"
    minimum_editable_pixels = 64
    minimum_full_frame_change_ratio = 0.02
    minimum_non_mask_change_ratio = 0.005
    maximum_unfilled_ratio = 0.01

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
            return {
                "approval_verified": False,
                "approval_source": "standalone-engine-call",
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
                "Для генерации можно использовать только точные утверждённые файлы геометрии и маски проекта.",
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

    @staticmethod
    def _effective_edit_mask(
        geometry_image: Path,
        approved_mask: Path,
        destination: Path,
    ) -> Path:
        with Image.open(geometry_image) as geometry_source:
            geometry = ImageOps.exif_transpose(geometry_source).convert("RGBA")
        with Image.open(approved_mask) as mask_source:
            mask = ImageOps.exif_transpose(mask_source).convert("L")

        if geometry.size != mask.size:
            raise AIEngineError(
                "Утверждённая геометрия и маска имеют разные размеры холста.",
                details={
                    "provider_call_made": False,
                    "credits_spent": False,
                    "reason": "mask_canvas_mismatch",
                    "geometry_size": geometry.size,
                    "mask_size": mask.size,
                },
            )

        binary_mask = mask.point(lambda value: 255 if value >= 128 else 0, mode="L")
        transparent_mask = geometry.getchannel("A").point(
            lambda value: 255 if value == 0 else 0,
            mode="L",
        )
        effective = ImageChops.lighter(binary_mask, transparent_mask)
        destination.parent.mkdir(parents=True, exist_ok=True)
        effective.save(destination, format="PNG", optimize=False)
        return destination

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

        # Маска намеренно не отправляется провайдеру: она используется только
        # для контроля заполнения бывших пустых областей. Генератор получает
        # утверждённую исправленную геометрию как единственный визуальный референс
        # и создаёт весь кадр целиком.
        return {
            "model": self.model,
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
        approved_mask = Path(outpaint_mask)
        output_dir = Path(output_dir)

        if not geometry_image.is_file():
            raise AIEngineError(
                "Файл утверждённой геометрии не найден. Запрос к генератору не отправлен.",
                details={"provider_call_made": False, "credits_spent": False},
            )
        if not approved_mask.is_file():
            raise AIEngineError(
                "Файл утверждённой маски не найден. Запрос к генератору не отправлен.",
                details={"provider_call_made": False, "credits_spent": False},
            )

        approval = self._approval_contract(geometry_image, approved_mask)
        effective_mask = self._effective_edit_mask(
            geometry_image,
            approved_mask,
            output_dir / "effective-edit-mask.png",
        )
        mask_stats = self._mask_statistics(effective_mask)

        prepared = super().prepare_environment_inputs(
            prompt=prompt,
            geometry_image=geometry_image,
            outpaint_mask=effective_mask,
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
                "mask_policy": "qc-only-white-mask-or-transparent-geometry",
                "mask_role": "quality-control-only",
                "source_contract": "corrected-approved-geometry-full-frame-reference",
                "approved_geometry_path": str(geometry_image),
                "approved_mask_path": str(approved_mask),
                "effective_mask_path": str(effective_mask),
                "approved_geometry_sha256": self._file_sha256(geometry_image),
                "approved_mask_sha256": self._file_sha256(approved_mask),
                "effective_mask_sha256": self._file_sha256(effective_mask),
                "system_prompt_contract": PROMPT_CONTRACT_VERSION,
                "system_prompt_sha256": self._system_prompt_sha256(),
                "system_prompt_in_request": True,
                "full_canvas_generation": True,
                "generation_mode": "full-frame-reference",
                "input_reference_count": 1,
            }
        )
        return prepared

    @staticmethod
    def _unfilled_statistics(candidate: Image.Image, edit_mask: Image.Image) -> dict[str, Any]:
        candidate_rgb = candidate.convert("RGB")
        editable = edit_mask.point(lambda value: 255 if value >= 128 else 0, mode="L")
        editable_pixels = int(sum(editable.histogram()[128:]))

        luminance = candidate_rgb.convert("L")
        near_black = luminance.point(lambda value: 255 if value <= 4 else 0, mode="L")
        black_in_edit = ImageChops.multiply(near_black, editable)
        black_pixels = int(sum(black_in_edit.histogram()[128:]))
        unfilled_ratio = black_pixels / float(max(1, editable_pixels))
        return {
            "editable_pixels": editable_pixels,
            "unfilled_editable_pixels": black_pixels,
            "unfilled_editable_ratio": round(unfilled_ratio, 6),
        }

    @staticmethod
    def _changed_ratio(
        candidate: Image.Image,
        geometry: Image.Image,
        area_mask: Image.Image | None = None,
    ) -> tuple[int, int, float]:
        difference = ImageChops.difference(
            candidate.convert("RGB"),
            geometry.convert("RGB"),
        ).convert("L")
        changed = difference.point(lambda value: 255 if value >= 6 else 0, mode="L")
        if area_mask is not None:
            binary_area = area_mask.point(
                lambda value: 255 if value >= 128 else 0,
                mode="L",
            )
            changed = ImageChops.multiply(changed, binary_area)
            total = int(sum(binary_area.histogram()[128:]))
        else:
            total = candidate.width * candidate.height
        changed_pixels = int(sum(changed.histogram()[128:]))
        ratio = changed_pixels / float(max(1, total))
        return changed_pixels, total, ratio

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
        cropped = generated.crop(crop_box)
        full_frame_master = cropped.resize(
            (width, height),
            Image.Resampling.LANCZOS,
        )

        environment_master_path = output_dir / "environment-remapped.png"
        candidate_path = output_dir / "candidate.png"
        full_frame_master.save(environment_master_path, format="PNG", optimize=False)
        full_frame_master.save(candidate_path, format="PNG", optimize=False)

        with Image.open(geometry_image) as geometry_source:
            geometry_master = ImageOps.exif_transpose(geometry_source).convert("RGB")
        if geometry_master.size != (width, height):
            raise AIEngineError(
                "Утверждённая геометрия больше не соответствует размеру master canvas.",
                details={
                    "geometry_size": geometry_master.size,
                    "master_size": (width, height),
                },
            )

        effective_mask = Path(prepared.get("effective_mask_path") or outpaint_mask)
        with Image.open(effective_mask) as mask_source:
            edit_mask = ImageOps.exif_transpose(mask_source).convert("L").point(
                lambda value: 255 if value >= 128 else 0,
                mode="L",
            )
        if edit_mask.size != (width, height):
            raise AIEngineError(
                "Контрольная маска больше не соответствует размеру master canvas.",
                details={
                    "mask_size": edit_mask.size,
                    "master_size": (width, height),
                },
            )

        unfilled = self._unfilled_statistics(full_frame_master, edit_mask)
        full_changed, full_total, full_change_ratio = self._changed_ratio(
            full_frame_master,
            geometry_master,
        )
        non_mask = ImageOps.invert(edit_mask)
        non_mask_changed, non_mask_total, non_mask_change_ratio = self._changed_ratio(
            full_frame_master,
            geometry_master,
            non_mask,
        )

        if (
            unfilled["editable_pixels"] > 0
            and unfilled["unfilled_editable_ratio"] > self.maximum_unfilled_ratio
        ):
            raise AIEngineError(
                "Генератор оставил чёрные или незаполненные участки в бывших пустых зонах.",
                details={
                    "transport": prepared,
                    "provider_output": str(provider_output),
                    "candidate": str(candidate_path),
                    **unfilled,
                    "reason": "unfilled_editable_area",
                },
            )

        if full_change_ratio < self.minimum_full_frame_change_ratio:
            raise AIEngineError(
                "Генератор не пересоздал изображение целиком: итог почти совпадает с исправленной геометрией.",
                details={
                    "transport": prepared,
                    "provider_output": str(provider_output),
                    "candidate": str(candidate_path),
                    "full_frame_changed_pixels": full_changed,
                    "full_frame_total_pixels": full_total,
                    "full_frame_change_ratio": round(full_change_ratio, 6),
                    "reason": "provider_full_frame_no_op",
                },
            )

        if non_mask_total > 0 and non_mask_change_ratio < self.minimum_non_mask_change_ratio:
            raise AIEngineError(
                "Генератор изменил только область маски, но не пересоздал остальную часть кадра.",
                details={
                    "transport": prepared,
                    "provider_output": str(provider_output),
                    "candidate": str(candidate_path),
                    "non_mask_changed_pixels": non_mask_changed,
                    "non_mask_total_pixels": non_mask_total,
                    "non_mask_change_ratio": round(non_mask_change_ratio, 6),
                    "reason": "mask_only_generation",
                },
            )

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
            "approved_geometry_preserved": False,
            "approved_geometry_used_as_reference": True,
            "full_canvas_generation": True,
            "generation_mode": "full-frame-reference",
            "full_frame_changed_pixels": full_changed,
            "full_frame_change_ratio": round(full_change_ratio, 6),
            "non_mask_changed_pixels": non_mask_changed,
            "non_mask_change_ratio": round(non_mask_change_ratio, 6),
            "meaningful_generation": True,
            **unfilled,
        }


_engine_module.OpenRouterImageEngine = OpenRouterImageEngine
