from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps


class GeometryEngine:
    """Perspective correction on the immutable master canvas.

    The source is never modified. The selected facade plane is rectified in
    place instead of being stretched over the complete canvas. The whole source
    is transformed through the same homography, so the unavoidable empty wedges
    remain transparent and become the explicit outpaint mask.
    """

    @staticmethod
    def _ordered_quad(points: list[dict]) -> np.ndarray:
        if len(points) != 4:
            raise ValueError("Perspective grid requires exactly four points")
        pts = np.array(
            [[float(point["x"]), float(point["y"])] for point in points],
            dtype=np.float32,
        )
        if not np.isfinite(pts).all():
            raise ValueError("Perspective grid contains invalid coordinates")
        sums = pts.sum(axis=1)
        diffs = np.diff(pts, axis=1).reshape(-1)
        return np.array(
            [
                pts[np.argmin(sums)],
                pts[np.argmin(diffs)],
                pts[np.argmax(sums)],
                pts[np.argmax(diffs)],
            ],
            dtype=np.float32,
        )

    @staticmethod
    def _destination_rect(
        src: np.ndarray,
        width: int,
        height: int,
    ) -> tuple[np.ndarray, dict]:
        top_width = float(np.linalg.norm(src[1] - src[0]))
        bottom_width = float(np.linalg.norm(src[2] - src[3]))
        left_height = float(np.linalg.norm(src[3] - src[0]))
        right_height = float(np.linalg.norm(src[2] - src[1]))

        rect_width = max(2, min(width, int(round((top_width + bottom_width) / 2.0))))
        rect_height = max(2, min(height, int(round((left_height + right_height) / 2.0))))

        center_x = float(src[:, 0].mean())
        center_y = float(src[:, 1].mean())
        left = int(round(center_x - rect_width / 2.0))
        top = int(round(center_y - rect_height / 2.0))
        left = max(0, min(width - rect_width, left))
        top = max(0, min(height - rect_height, top))
        right = left + rect_width - 1
        bottom = top + rect_height - 1

        dst = np.array(
            [
                [left, top],
                [right, top],
                [right, bottom],
                [left, bottom],
            ],
            dtype=np.float32,
        )
        return dst, {
            "left": left,
            "top": top,
            "right": right,
            "bottom": bottom,
            "width": rect_width,
            "height": rect_height,
        }

    def apply(self, source: Path, project_dir: Path, points: list[dict]) -> dict:
        with Image.open(source) as image:
            oriented = ImageOps.exif_transpose(image).convert("RGBA")
            width, height = oriented.size
            rgba = np.array(oriented)

        src = self._ordered_quad(points)
        if (
            (src[:, 0] < 0).any()
            or (src[:, 0] > width - 1).any()
            or (src[:, 1] < 0).any()
            or (src[:, 1] > height - 1).any()
        ):
            raise ValueError("Perspective grid must stay inside the master canvas")

        dst, destination_rect = self._destination_rect(src, width, height)
        matrix = cv2.getPerspectiveTransform(src, dst)

        corrected = cv2.warpPerspective(
            rgba,
            matrix,
            (width, height),
            flags=cv2.INTER_LANCZOS4,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(0, 0, 0, 0),
        )

        validity_source = np.full((height, width), 255, dtype=np.uint8)
        validity = cv2.warpPerspective(
            validity_source,
            matrix,
            (width, height),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=0,
        )
        mask = np.where(validity < 250, 255, 0).astype(np.uint8)
        corrected[:, :, 3] = np.where(mask == 255, 0, corrected[:, :, 3]).astype(np.uint8)

        target_dir = project_dir / "images" / "stages" / "geometry"
        target_dir.mkdir(parents=True, exist_ok=True)
        candidate = target_dir / "candidate.png"
        Image.fromarray(corrected, "RGBA").save(
            candidate,
            format="PNG",
            optimize=False,
        )

        mask_path = target_dir / "outpaint-mask.png"
        Image.fromarray(mask, "L").save(mask_path, format="PNG", optimize=False)

        transparent_pixels = int(np.count_nonzero(mask))
        transparent_ratio = transparent_pixels / float(width * height)
        metadata = {
            "source": str(source),
            "candidate": str(candidate),
            "outpaint_mask": str(mask_path),
            "width": width,
            "height": height,
            "points": points,
            "destination_rect": destination_rect,
            "matrix": matrix.tolist(),
            "transparent_pixels": transparent_pixels,
            "transparent_ratio": round(transparent_ratio, 6),
            "canvas_preserved": True,
            "lossless": True,
            "rectification_policy": "in-place-plane-rectification",
            "generation_ready": transparent_pixels > 0,
        }
        (target_dir / "geometry.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            "utf-8",
        )
        return metadata
