from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps


class GeometryEngine:
    """Perspective correction on the immutable master canvas.

    The source is never modified. The corrected candidate is saved as lossless PNG
    at exactly the master width and height. Areas outside the transformed source
    remain transparent and become explicit outpaint masks for the next stage.
    """

    @staticmethod
    def _ordered_quad(points: list[dict]) -> np.ndarray:
        if len(points) != 4:
            raise ValueError("Perspective grid requires exactly four points")
        pts = np.array([[float(p["x"]), float(p["y"])] for p in points], dtype=np.float32)
        if not np.isfinite(pts).all():
            raise ValueError("Perspective grid contains invalid coordinates")
        sums = pts.sum(axis=1)
        diffs = np.diff(pts, axis=1).reshape(-1)
        return np.array([
            pts[np.argmin(sums)],      # top-left
            pts[np.argmin(diffs)],     # top-right
            pts[np.argmax(sums)],      # bottom-right
            pts[np.argmax(diffs)],     # bottom-left
        ], dtype=np.float32)

    def apply(self, source: Path, project_dir: Path, points: list[dict]) -> dict:
        with Image.open(source) as im:
            oriented = ImageOps.exif_transpose(im).convert("RGBA")
            width, height = oriented.size
            rgba = np.array(oriented)

        src = self._ordered_quad(points)
        if (src[:, 0] < 0).any() or (src[:, 0] > width).any() or (src[:, 1] < 0).any() or (src[:, 1] > height).any():
            raise ValueError("Perspective grid must stay inside the master canvas")

        dst = np.array([
            [0, 0],
            [width - 1, 0],
            [width - 1, height - 1],
            [0, height - 1],
        ], dtype=np.float32)
        matrix = cv2.getPerspectiveTransform(src, dst)
        corrected = cv2.warpPerspective(
            rgba,
            matrix,
            (width, height),
            flags=cv2.INTER_LANCZOS4,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(0, 0, 0, 0),
        )

        target_dir = project_dir / "images" / "stages" / "geometry"
        target_dir.mkdir(parents=True, exist_ok=True)
        candidate = target_dir / "candidate.png"
        Image.fromarray(corrected, "RGBA").save(candidate, format="PNG", optimize=False)

        mask = np.where(corrected[:, :, 3] == 0, 255, 0).astype(np.uint8)
        mask_path = target_dir / "outpaint-mask.png"
        Image.fromarray(mask, "L").save(mask_path, format="PNG", optimize=False)

        transparent_pixels = int(np.count_nonzero(mask))
        metadata = {
            "source": str(source),
            "candidate": str(candidate),
            "outpaint_mask": str(mask_path),
            "width": width,
            "height": height,
            "points": points,
            "matrix": matrix.tolist(),
            "transparent_pixels": transparent_pixels,
            "transparent_ratio": round(transparent_pixels / float(width * height), 6),
            "canvas_preserved": True,
            "lossless": True,
        }
        (target_dir / "geometry.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), "utf-8")
        return metadata
