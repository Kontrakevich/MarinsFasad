from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps


class GeometryEngine:
    """Perspective correction on the immutable master canvas.

    The source is never modified. The whole source is transformed through one
    homography. Areas for which the corrected image has no visual information
    remain transparent and are detected automatically by the outpaint stage.
    No separate project mask is created or approved.
    """

    @staticmethod
    def _ordered_quad(points: list[dict], width: int, height: int) -> np.ndarray:
        if len(points) != 4:
            raise ValueError("Нужно указать четыре точки перспективной сетки.")

        normalized: list[list[float]] = []
        for index, point in enumerate(points, start=1):
            try:
                x = float(point["x"])
                y = float(point["y"])
            except (KeyError, TypeError, ValueError):
                raise ValueError(f"Координаты точки {index} переданы неверно.")
            if not np.isfinite(x) or not np.isfinite(y):
                raise ValueError(f"Координаты точки {index} должны быть конечными числами.")
            normalized.append(
                [
                    max(0.0, min(float(width - 1), x)),
                    max(0.0, min(float(height - 1), y)),
                ]
            )

        pts = np.array(normalized, dtype=np.float32)
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

        src = self._ordered_quad(points, width, height)
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
        missing = validity < 250
        corrected[:, :, 3] = np.where(missing, 0, corrected[:, :, 3]).astype(np.uint8)

        target_dir = project_dir / "images" / "stages" / "geometry"
        target_dir.mkdir(parents=True, exist_ok=True)
        candidate = target_dir / "candidate.png"
        Image.fromarray(corrected, "RGBA").save(
            candidate,
            format="PNG",
            optimize=False,
        )

        # Remove the obsolete project mask left by earlier builds.
        (target_dir / "outpaint-mask.png").unlink(missing_ok=True)

        missing_pixels = int(np.count_nonzero(missing))
        missing_ratio = missing_pixels / float(width * height)
        normalized_points = [
            {"x": float(point[0]), "y": float(point[1])}
            for point in src.tolist()
        ]
        metadata = {
            "source": str(source),
            "candidate": str(candidate),
            "width": width,
            "height": height,
            "points": normalized_points,
            "destination_rect": destination_rect,
            "matrix": matrix.tolist(),
            "missing_pixels": missing_pixels,
            "missing_ratio": round(missing_ratio, 6),
            "canvas_preserved": True,
            "lossless": True,
            "rectification_policy": "in-place-plane-rectification",
            "outpaint_detection": "automatic-from-candidate-transparency",
            "outpaint_required": missing_pixels > 0,
        }
        (target_dir / "geometry.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            "utf-8",
        )
        return metadata
