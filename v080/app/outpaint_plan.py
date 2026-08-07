from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps


class OutpaintPlanEngine:
    """Builds a private outpaint plan directly from approved geometry alpha.

    This is an internal processing artifact, not a project asset and not a user
    input. The user approves only the corrected geometry image.
    """

    alpha_threshold = 250
    minimum_region_pixels = 16

    def build(self, geometry_image: Path, output_dir: Path) -> dict:
        output_dir.mkdir(parents=True, exist_ok=True)
        with Image.open(geometry_image) as source:
            geometry = ImageOps.exif_transpose(source).convert("RGBA")

        width, height = geometry.size
        alpha = np.asarray(geometry.getchannel("A"), dtype=np.uint8)
        missing = np.where(alpha < self.alpha_threshold, 255, 0).astype(np.uint8)

        # Close tiny interpolation gaps while preserving the actual border wedges.
        missing = cv2.morphologyEx(
            missing,
            cv2.MORPH_CLOSE,
            np.ones((3, 3), dtype=np.uint8),
            iterations=1,
        )

        labels_count, labels, stats, _ = cv2.connectedComponentsWithStats(
            missing,
            connectivity=8,
        )
        cleaned = np.zeros_like(missing, dtype=np.uint8)
        regions: list[dict] = []
        for label_index in range(1, labels_count):
            x, y, region_width, region_height, area = [
                int(value) for value in stats[label_index]
            ]
            if area < self.minimum_region_pixels:
                continue
            cleaned[labels == label_index] = 255
            regions.append(
                {
                    "x": x,
                    "y": y,
                    "width": region_width,
                    "height": region_height,
                    "pixels": area,
                }
            )

        plan_path = output_dir / "auto-outpaint-plan.png"
        Image.fromarray(cleaned, mode="L").save(
            plan_path,
            format="PNG",
            optimize=False,
        )

        missing_pixels = int(np.count_nonzero(cleaned))
        metadata = {
            "path": str(plan_path),
            "detection": "automatic-from-approved-geometry-transparency",
            "user_input_required": False,
            "width": width,
            "height": height,
            "missing_pixels": missing_pixels,
            "missing_ratio": round(missing_pixels / float(max(1, width * height)), 6),
            "region_count": len(regions),
            "regions": regions,
            "outpaint_required": missing_pixels > 0,
        }
        (output_dir / "auto-outpaint-plan.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            "utf-8",
        )
        return metadata
