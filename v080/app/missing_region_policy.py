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
    """Reconstructs missing geometry as zoomed Nano Banana edit tiles.

    A thin border wedge is too small in a full-frame request and can be ignored by
    the provider. The first pass still executes the exact UI prompt. Any remaining
    missing regions are then divided into context crops, enlarged by the normal
    provider transport, reconstructed by Nano Banana and composited only through
    the original mandatory mask.
    """

    transport_engine_version = "2.8.0"
    missing_region_transport_policy = "opaque-marker-plus-zoomed-nano-banana-tiles"
    outpaint_repair_mode = "component-tiles"
    outpaint_tile_core_span = 520
    outpaint_tile_context = 72
    outpaint_tile_min_pixels = 96
    outpaint_tile_max_calls = 8
    placeholder_min_component_pixels = 192
    placeholder_max_editable_ratio = 0.003

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

        # Never transmit transparency. Some gateways flatten transparent pixels
        # to white before the model sees them. The marker makes absence explicit.
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
                "outpaint_repair_mode": self.outpaint_repair_mode,
                "outpaint_tile_max_calls": self.outpaint_tile_max_calls,
                "solid_white_is_valid_outpaint": False,
            }
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "transport.json").write_text(
            json.dumps(prepared, ensure_ascii=False, indent=2),
            "utf-8",
        )
        return prepared

    def _placeholder_analysis(
        self,
        candidate: Image.Image,
        editable: Image.Image,
    ) -> tuple[Image.Image, dict[str, Any]]:
        candidate = candidate.convert("RGB")
        editable = editable.convert("L").point(
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
            & (channel_min >= 252)
            & ((channel_max - channel_min) <= 2)
        )
        near_solid_black = editable_array & (channel_max <= 2)
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
            near_solid_white | near_solid_black | marker_magenta | marker_cyan,
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

        labels_count, labels, stats, _ = cv2.connectedComponentsWithStats(
            placeholder,
            connectivity=8,
        )
        significant = np.zeros_like(placeholder, dtype=np.uint8)
        component_count = 0
        placeholder_pixels = 0
        largest_component = 0
        for label_index in range(1, labels_count):
            area = int(stats[label_index, cv2.CC_STAT_AREA])
            if area < self.placeholder_min_component_pixels:
                continue
            significant[labels == label_index] = 255
            component_count += 1
            placeholder_pixels += area
            largest_component = max(largest_component, area)

        placeholder_ratio = placeholder_pixels / float(max(1, editable_pixels))
        reconstructed = (
            editable_pixels == 0
            or (
                component_count == 0
                and placeholder_ratio <= self.placeholder_max_editable_ratio
            )
        )
        return Image.fromarray(significant, mode="L"), {
            "outpaint_reconstructed": reconstructed,
            "editable_pixels": editable_pixels,
            "placeholder_component_count": component_count,
            "placeholder_pixels": placeholder_pixels,
            "placeholder_ratio": round(placeholder_ratio, 6),
            "largest_placeholder_component_pixels": largest_component,
            "solid_white_is_valid_outpaint": False,
        }

    def _outpaint_reconstruction_statistics(
        self,
        candidate_path: Path,
        mask_path: Path,
    ) -> dict[str, Any]:
        with Image.open(candidate_path) as candidate_source:
            candidate = ImageOps.exif_transpose(candidate_source).convert("RGB")
        with Image.open(mask_path) as mask_source:
            editable = ImageOps.exif_transpose(mask_source).convert("L")
        _, stats = self._placeholder_analysis(candidate, editable)
        return stats

    @staticmethod
    def _expand_box(
        box: tuple[int, int, int, int],
        canvas_size: tuple[int, int],
        padding: int,
    ) -> tuple[int, int, int, int]:
        x0, y0, x1, y1 = box
        width, height = canvas_size
        return (
            max(0, x0 - padding),
            max(0, y0 - padding),
            min(width, x1 + padding),
            min(height, y1 + padding),
        )

    def _component_tile_boxes(self, mask: Image.Image) -> list[dict[str, Any]]:
        binary = np.asarray(
            mask.convert("L").point(
                lambda value: 255 if value >= 128 else 0,
                mode="L",
            ),
            dtype=np.uint8,
        )
        labels_count, labels, stats, _ = cv2.connectedComponentsWithStats(
            binary,
            connectivity=8,
        )
        canvas_height, canvas_width = binary.shape
        tiles: list[dict[str, Any]] = []
        span = max(256, int(self.outpaint_tile_core_span))

        for label_index in range(1, labels_count):
            x, y, width, height, area = [
                int(value) for value in stats[label_index]
            ]
            if area < self.outpaint_tile_min_pixels:
                continue

            if width >= height and width > span:
                starts = range(x, x + width, span)
                segments = [
                    (start, y, min(x + width, start + span), y + height)
                    for start in starts
                ]
            elif height > width and height > span:
                starts = range(y, y + height, span)
                segments = [
                    (x, start, x + width, min(y + height, start + span))
                    for start in starts
                ]
            else:
                segments = [(x, y, x + width, y + height)]

            for segment in segments:
                sx0, sy0, sx1, sy1 = segment
                segment_labels = labels[sy0:sy1, sx0:sx1] == label_index
                ys, xs = np.where(segment_labels)
                if xs.size < self.outpaint_tile_min_pixels:
                    continue
                tight = (
                    sx0 + int(xs.min()),
                    sy0 + int(ys.min()),
                    sx0 + int(xs.max()) + 1,
                    sy0 + int(ys.max()) + 1,
                )
                tight_width = max(1, tight[2] - tight[0])
                tight_height = max(1, tight[3] - tight[1])
                adaptive_padding = min(
                    int(self.outpaint_tile_context),
                    max(40, int(min(tight_width, tight_height) * 0.85)),
                )
                crop_box = self._expand_box(
                    tight,
                    (canvas_width, canvas_height),
                    adaptive_padding,
                )
                tiles.append(
                    {
                        "component": label_index,
                        "crop_box": crop_box,
                        "mask_pixels": int(xs.size),
                    }
                )

        tiles.sort(key=lambda item: item["mask_pixels"], reverse=True)
        return tiles[: self.outpaint_tile_max_calls]

    def _tile_prompt(self, original_prompt: str, tile_index: int) -> str:
        return (
            "OUTPAINT TILE RECONSTRUCTION — REQUIRED\n"
            f"Tile {tile_index} is a zoomed crop from the approved photograph.\n"
            "Reference image 1 contains an opaque magenta/cyan checkerboard only where visual information is missing.\n"
            "Reference image 2 is an aligned binary mask: WHITE pixels are the only editable pixels; BLACK pixels are immutable.\n"
            "Replace every white-mask and checkerboard pixel with real photorealistic scene content. Continue adjacent sky, facade, "
            "building edges, pavement, asphalt, ground lines, shadows and perspective without seams.\n"
            "Do not return white, black, transparent, checkerboard or flat-color fills. Do not change any black-mask pixel.\n"
            "The complete project instruction remains authoritative:\n\n"
            f"{original_prompt}"
        )

    def _repair_with_tiles(
        self,
        *,
        candidate_path: Path,
        editable_mask_path: Path,
        original_prompt: str,
        output_dir: Path,
    ) -> tuple[Path, dict[str, Any]]:
        with Image.open(candidate_path) as candidate_source:
            working = ImageOps.exif_transpose(candidate_source).convert("RGB")
        with Image.open(editable_mask_path) as mask_source:
            full_mask = ImageOps.exif_transpose(mask_source).convert("L").point(
                lambda value: 255 if value >= 128 else 0,
                mode="L",
            )
        if full_mask.size != working.size:
            full_mask = full_mask.resize(working.size, Image.Resampling.NEAREST)

        tile_boxes = self._component_tile_boxes(full_mask)
        tile_reports: list[dict[str, Any]] = []

        for tile_index, tile in enumerate(tile_boxes, start=1):
            crop_box = tuple(tile["crop_box"])
            crop_image = working.crop(crop_box)
            crop_mask = full_mask.crop(crop_box)
            marker = self._missing_region_marker(crop_image.size)
            marked_crop = Image.composite(marker, crop_image, crop_mask)

            tile_dir = output_dir / "outpaint-tiles" / f"tile-{tile_index:02d}"
            tile_dir.mkdir(parents=True, exist_ok=True)
            tile_base_path = tile_dir / "tile-base.png"
            tile_mask_path = tile_dir / "tile-mask.png"
            marked_crop.save(tile_base_path, format="PNG", optimize=False)
            crop_mask.save(tile_mask_path, format="PNG", optimize=False)

            tile_result = super().generate_environment(
                prompt=self._tile_prompt(original_prompt, tile_index),
                geometry_image=tile_base_path,
                outpaint_mask=tile_mask_path,
                output_dir=tile_dir / "generation",
                width=crop_image.width,
                height=crop_image.height,
                prepared_input=None,
            )
            with Image.open(tile_result["candidate"]) as repaired_source:
                repaired = ImageOps.exif_transpose(repaired_source).convert("RGB")
            if repaired.size != crop_image.size:
                repaired = repaired.resize(crop_image.size, Image.Resampling.LANCZOS)

            merged_crop = Image.composite(repaired, crop_image, crop_mask)
            working.paste(merged_crop, (crop_box[0], crop_box[1]))
            _, tile_stats = self._placeholder_analysis(merged_crop, crop_mask)
            tile_reports.append(
                {
                    "tile": tile_index,
                    "crop_box": {
                        "left": crop_box[0],
                        "top": crop_box[1],
                        "right": crop_box[2],
                        "bottom": crop_box[3],
                    },
                    "mask_pixels": tile["mask_pixels"],
                    "provider_model": tile_result.get("model"),
                    "prompt_match": tile_result.get("prompt_match"),
                    "reconstruction": tile_stats,
                }
            )

        repaired_path = output_dir / "candidate.png"
        working.save(repaired_path, format="PNG", optimize=False)
        _, final_stats = self._placeholder_analysis(working, full_mask)
        return repaired_path, {
            "mode": self.outpaint_repair_mode,
            "tile_count": len(tile_reports),
            "maximum_tile_calls": self.outpaint_tile_max_calls,
            "tiles": tile_reports,
            "final": final_stats,
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
        effective_mask = Path(
            ((first.get("transport") or {}).get("effective_mask_path"))
            or ((prepared_input or {}).get("effective_mask_path"))
            or outpaint_mask
        )
        first_stats = self._outpaint_reconstruction_statistics(
            Path(first["candidate"]),
            effective_mask,
        )
        first.update(
            {
                "missing_region_transport_policy": self.missing_region_transport_policy,
                "outpaint_repair_mode": self.outpaint_repair_mode,
                "outpaint_reconstruction": first_stats,
                "outpaint_tile_repair_used": False,
            }
        )
        self._write_result_metadata(output_dir, first)
        if first_stats["outpaint_reconstructed"]:
            return first

        repaired_path, repair = self._repair_with_tiles(
            candidate_path=Path(first["candidate"]),
            editable_mask_path=effective_mask,
            original_prompt=original_prompt,
            output_dir=output_dir,
        )
        final_stats = repair["final"]
        first.update(
            {
                "candidate": str(repaired_path),
                "outpaint_reconstruction": final_stats,
                "outpaint_tile_repair_used": True,
                "outpaint_tile_repair": repair,
                "first_attempt_outpaint_reconstruction": first_stats,
            }
        )
        self._write_result_metadata(output_dir, first)
        if final_stats["outpaint_reconstructed"]:
            return first

        raise AIEngineError(
            "Nano Banana не смогла реконструировать отдельные увеличенные фрагменты отсутствующей области.",
            details={
                "reason": "outpaint_tile_reconstruction_failed",
                "provider_call_made": True,
                "tile_count": repair["tile_count"],
                "first_attempt": first_stats,
                "tile_repair": repair,
                "candidate": str(repaired_path),
                "transport": first.get("transport"),
            },
        )


_engine_module.OpenRouterImageEngine = OpenRouterImageEngine
