from __future__ import annotations

import math
from typing import Any

import numpy as np
from PIL import Image

from . import ai_engine as _engine_module


_PreviousOpenRouterImageEngine = _engine_module.OpenRouterImageEngine


class OpenRouterImageEngine(_PreviousOpenRouterImageEngine):
    """Plans separate zoomed crops for each side of a connected border mask."""

    outpaint_tile_grid_columns = 3
    outpaint_tile_grid_rows = 3
    outpaint_tile_planner = "adaptive-3x3-border-grid"

    def _component_tile_boxes(self, mask: Image.Image) -> list[dict[str, Any]]:
        binary = np.asarray(
            mask.convert("L").point(
                lambda value: 255 if value >= 128 else 0,
                mode="L",
            ),
            dtype=np.uint8,
        )
        canvas_height, canvas_width = binary.shape
        columns = min(
            self.outpaint_tile_grid_columns,
            max(1, math.ceil(canvas_width / float(self.outpaint_tile_core_span))),
        )
        rows = min(
            self.outpaint_tile_grid_rows,
            max(1, math.ceil(canvas_height / float(self.outpaint_tile_core_span))),
        )

        tiles: list[dict[str, Any]] = []
        for row in range(rows):
            core_top = int(round(row * canvas_height / rows))
            core_bottom = int(round((row + 1) * canvas_height / rows))
            for column in range(columns):
                core_left = int(round(column * canvas_width / columns))
                core_right = int(round((column + 1) * canvas_width / columns))
                cell = binary[core_top:core_bottom, core_left:core_right]
                ys, xs = np.where(cell >= 128)
                if xs.size < self.outpaint_tile_min_pixels:
                    continue

                tight = (
                    core_left + int(xs.min()),
                    core_top + int(ys.min()),
                    core_left + int(xs.max()) + 1,
                    core_top + int(ys.max()) + 1,
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
                        "component": row * columns + column + 1,
                        "grid_row": row,
                        "grid_column": column,
                        "crop_box": crop_box,
                        "mask_pixels": int(xs.size),
                    }
                )

        # Border cells are kept before a possible central cell. This guarantees
        # that the four sides and corners are repaired within the eight-call cap.
        def priority(item: dict[str, Any]) -> tuple[int, int]:
            border = (
                item["grid_row"] in {0, rows - 1}
                or item["grid_column"] in {0, columns - 1}
            )
            return (1 if border else 0, item["mask_pixels"])

        tiles.sort(key=priority, reverse=True)
        return tiles[: self.outpaint_tile_max_calls]


_engine_module.OpenRouterImageEngine = OpenRouterImageEngine
