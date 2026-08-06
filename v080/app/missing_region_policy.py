from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageChops, ImageOps

from . import ai_engine as _engine_module


_PreviousOpenRouterImageEngine = _engine_module.OpenRouterImageEngine
AIEngineError = _engine_module.AIEngineError


class OpenRouterImageEngine(_PreviousOpenRouterImageEngine):
    """Makes missing geometry regions explicit and requires real Nano Banana outpaint."""

    # Keep the transport protocol version compatible with the existing v0.8
    # regression contract while extending the final policy layer.
    transport_engine_version = "2.7.1"
    missing_region_transport_policy = "opaque-chroma-marker-with-nano-banana-auto-retry"
    outpaint_auto_retry_limit = 1
    placeholder_min_component_pixels = 256
    placeholder_max_editable_ratio = 0.01

    @staticmethod
    def _missing_region_marker(size: tuple[int, int]) -> Image.Image:
        width, height = size
        y, x = np.indices((height, width))
        checker = ((x // 18) + (y // 18)) % 2
        marker = np.empty((height, width, 3), dtype=np.uint8)
        marker[checker == 0] = (255, 0, 255)
        marker[checker == 1] = (0, 255, 255)
        return Image.fromarray(marker, mode="RGB")

    @staticmethod
    def _reference_canvases(
        geometry_master: Image.Image,
        mask_master: Image.Image,
        reference_size: tuple[int, int],
    ) -> tuple[Image.Image, Image.Image, tuple[int, int, int, int]]:
        geometry_canvas, mask_canvas, content_box = (
            _PreviousOpenRouterImageEngine._reference_canvases(
                geometry_master,
                mask_master,
                reference_size,
            )
        )

        geometry_rgba = geometry_canvas.convert("RGBA")
        mandatory = mask_canvas.convert("L").point(
            lambda value: 255 if value >= 128 else 0,
            mode="L",
        )
        transparent = geometry_rgba.getchannel("A").point(
            lambda value: 255 if value < 250 else 0,
            mode="L",
        )
        missing = ImageChops.lighter(mandatory, transparent)

        # Never transmit transparent pixels. Gateways and image providers often
        # flatten them to white, which previously looked like a generated result.
        marker = OpenRouterImageEngine._missing_region_marker(reference_size)
        marked_rgb = Image.composite(marker, geometry_rgba.convert("RGB"), missing)
        marked_rgba = marked_rgb.convert("RGBA")
        marked_rgba.putalpha(255)
        return marked_rgba, mandatory, content_box

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
        prepared.update(
            {
                "missing_region_transport_policy": self.missing_region_transport_policy,
                "missing_region_marker": "opaque-magenta-cyan-checkerboard",
                "transparent_pixels_transmitted": False,
                "outpaint_auto_retry_limit": self.outpaint_auto_retry_limit,
                "solid_white_is_valid_outpaint": False,
            }
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "transport.json").write_text(
            json.dumps(prepared, ensure_ascii=False, indent=2),
            "utf-8",
        )
        return prepared

    def _outpaint_reconstruction_statistics(
        self,
        candidate_path: Path,
        mask_path: Path,
    ) -> dict[str, Any]:
        with Image.open(candidate_path) as candidate_source:
            candidate = ImageOps.exif_transpose(candidate_source).convert("RGB")
        with Image.open(mask_path) as mask_source:
            editable = ImageOps.exif_transpose(mask_source).convert("L").point(
                lambda value: 255 if value >= 128 else 0,
                mode="L",
            )

        if editable.size != candidate.size:
            editable = editable.resize(candidate.size, Image.Resampling.NEAREST)

        rgb = np.asarray(candidate, dtype=np.uint8)
        editable_array = np.asarray(editable, dtype=np.uint8) >= 128
        editable_pixels = int(np.count_nonzero(editable_array))

        channel_min = rgb.min(axis=2)
        channel_max = rgb.max(axis=2)
        near_solid_white = (
            editable_array
            & (channel_min >= 248)
            & ((channel_max - channel_min) <= 4)
        )
        marker_magenta = (
            editable_array
            & (rgb[:, :, 0] >= 220)
            & (rgb[:, :, 1] <= 45)
            & (rgb[:, :, 2] >= 220)
        )
        marker_cyan = (
            editable_array
            & (rgb[:, :, 0] <= 45)
            & (rgb[:, :, 1] >= 220)
            & (rgb[:, :, 2] >= 220)
        )
        placeholder = np.where(
            near_solid_white | marker_magenta | marker_cyan,
            255,
            0,
        ).astype(np.uint8)
        placeholder = cv2.morphologyEx(
            placeholder,
            cv2.MORPH_OPEN,
            np.ones((3, 3), dtype=np.uint8),
            iterations=1,
        )
        placeholder = cv2.morphologyEx(
            placeholder,
            cv2.MORPH_CLOSE,
            np.ones((7, 7), dtype=np.uint8),
            iterations=1,
        )

        labels_count, _, stats, _ = cv2.connectedComponentsWithStats(
            placeholder,
            connectivity=8,
        )
        significant_pixels = 0
        significant_components = 0
        largest_component_pixels = 0
        for label_index in range(1, labels_count):
            area = int(stats[label_index, cv2.CC_STAT_AREA])
            if area < self.placeholder_min_component_pixels:
                continue
            significant_components += 1
            significant_pixels += area
            largest_component_pixels = max(largest_component_pixels, area)

        placeholder_ratio = significant_pixels / float(max(1, editable_pixels))
        largest_ratio = largest_component_pixels / float(max(1, editable_pixels))
        reconstructed = (
            editable_pixels == 0
            or (
                significant_components == 0
                and placeholder_ratio <= self.placeholder_max_editable_ratio
            )
        )
        return {
            "outpaint_reconstructed": reconstructed,
            "editable_pixels": editable_pixels,
            "placeholder_component_count": significant_components,
            "placeholder_pixels": significant_pixels,
            "placeholder_ratio": round(placeholder_ratio, 6),
            "largest_placeholder_component_pixels": largest_component_pixels,
            "largest_placeholder_component_ratio": round(largest_ratio, 6),
            "solid_white_is_valid_outpaint": False,
        }

    @staticmethod
    def _write_result_metadata(output_dir: Path, result: dict) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "generation.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            "utf-8",
        )

    def generate_environment(
        self,
        *,
        prompt: str,
        geometry_image: Path,
        outpaint_mask: Path,
        output_dir: Path,
        width: int,
        height: int,
        prepared_input: dict | None = None,
    ) -> dict:
        original_prompt = str(prompt or "").strip()
        first = super().generate_environment(
            prompt=original_prompt,
            geometry_image=geometry_image,
            outpaint_mask=outpaint_mask,
            output_dir=output_dir,
            width=width,
            height=height,
            prepared_input=prepared_input,
        )
        first_mask = Path(
            ((first.get("transport") or {}).get("effective_mask_path"))
            or ((prepared_input or {}).get("effective_mask_path"))
            or outpaint_mask
        )
        first_stats = self._outpaint_reconstruction_statistics(
            Path(first["candidate"]),
            first_mask,
        )
        first.update(
            {
                "missing_region_transport_policy": self.missing_region_transport_policy,
                "outpaint_reconstruction": first_stats,
                "outpaint_retry_count": 0,
            }
        )
        self._write_result_metadata(output_dir, first)
        if first_stats["outpaint_reconstructed"]:
            return first

        retry_prompt = (
            f"{original_prompt}\n\n"
            "OUTPAINT RECONSTRUCTION — AUTOMATIC CORRECTION ATTEMPT\n"
            "The previous attempt left solid white or service-marker areas inside the mandatory edit map. "
            "This is invalid. Reference image 1 contains magenta/cyan checkerboard only where visual information is missing. "
            "Replace every checkerboard, transparent, blank, white or unfinished masked pixel with a photorealistic continuation "
            "of the adjacent sky, buildings, ground, pavement and urban environment. Preserve every operator instruction above "
            "exactly and preserve all unaffected source content. Do not output solid fills, borders, wedges or placeholders."
        )
        retry_dir = output_dir / "outpaint-retry-1"
        retry = super().generate_environment(
            prompt=retry_prompt,
            geometry_image=geometry_image,
            outpaint_mask=outpaint_mask,
            output_dir=retry_dir,
            width=width,
            height=height,
            prepared_input=None,
        )
        retry_mask = Path(
            ((retry.get("transport") or {}).get("effective_mask_path"))
            or outpaint_mask
        )
        retry_stats = self._outpaint_reconstruction_statistics(
            Path(retry["candidate"]),
            retry_mask,
        )
        retry.update(
            {
                "missing_region_transport_policy": self.missing_region_transport_policy,
                "outpaint_reconstruction": retry_stats,
                "outpaint_retry_count": 1,
                "outpaint_retry_reason": "solid-white-or-service-marker-detected",
                "original_compiled_prompt": original_prompt,
                "operator_prompt_preserved_verbatim": original_prompt in retry_prompt,
                "first_attempt_outpaint_reconstruction": first_stats,
            }
        )
        self._write_result_metadata(retry_dir, retry)
        self._write_result_metadata(output_dir, retry)
        if retry_stats["outpaint_reconstructed"]:
            return retry

        raise AIEngineError(
            "Nano Banana не реконструировала отсутствующие участки изображения после автоматической повторной попытки.",
            details={
                "reason": "outpaint_reconstruction_failed_after_retry",
                "provider_call_made": True,
                "outpaint_retry_count": 1,
                "first_attempt": first_stats,
                "retry_attempt": retry_stats,
                "first_candidate": first.get("candidate"),
                "retry_candidate": retry.get("candidate"),
                "transport": retry.get("transport"),
            },
        )


_engine_module.OpenRouterImageEngine = OpenRouterImageEngine
