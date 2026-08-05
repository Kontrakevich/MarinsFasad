from __future__ import annotations

from collections import deque
from pathlib import Path
from PIL import Image, ImageOps


class QualityEngine:
    def inspect(self, master: Path, candidate: Path) -> dict:
        with Image.open(master) as source, Image.open(candidate) as result:
            source = ImageOps.exif_transpose(source).convert("RGB")
            result = ImageOps.exif_transpose(result).convert("RGB")
            same_canvas = source.size == result.size
            black_ratio = self._border_black_ratio(result)
        checks = {
            "canvas_match": same_canvas,
            "black_border_ratio": black_ratio,
            "outpaint_complete": black_ratio < 0.002,
        }
        return {"ok": all([checks["canvas_match"], checks["outpaint_complete"]]), "checks": checks}

    @staticmethod
    def _border_black_ratio(image: Image.Image, threshold: int = 12) -> float:
        width, height = image.size
        px = image.load()
        seen: set[tuple[int, int]] = set()
        queue: deque[tuple[int, int]] = deque()
        for x in range(width):
            queue.extend(((x, 0), (x, height - 1)))
        for y in range(height):
            queue.extend(((0, y), (width - 1, y)))
        while queue:
            x, y = queue.popleft()
            if (x, y) in seen:
                continue
            r, g, b = px[x, y]
            if max(r, g, b) > threshold:
                continue
            seen.add((x, y))
            if x > 0: queue.append((x - 1, y))
            if x + 1 < width: queue.append((x + 1, y))
            if y > 0: queue.append((x, y - 1))
            if y + 1 < height: queue.append((x, y + 1))
        return len(seen) / max(1, width * height)
