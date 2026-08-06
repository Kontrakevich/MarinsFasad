from __future__ import annotations

from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageChops

from . import ai_engine as _engine_module


_PreviousOpenRouterImageEngine = _engine_module.OpenRouterImageEngine


class OpenRouterImageEngine(_PreviousOpenRouterImageEngine):
    """Non-blocking outpaint QC for selective Nano Banana edits.

    Dark architectural content must never cancel a valid prompt-driven result.
    Potentially unfilled areas are measured and reported as warnings only.
    """

    transport_engine_version = "2.7.2"
    outpaint_qc_policy = "non-blocking-connected-components-warning"
    outpaint_qc_blocking = False

    # The inherited promotion code raises only when the measured ratio exceeds
    # this value. A ratio cannot exceed 1.0, therefore QC remains diagnostic.
    maximum_unfilled_ratio = 1.0
    minimum_unfilled_component_pixels = 512

    def _unfilled_statistics(
        self,
        candidate: Image.Image,
        edit_mask: Image.Image,
    ) -> dict[str, Any]:
        editable = edit_mask.convert("L").point(
            lambda value: 255 if value >= 128 else 0,
            mode="L",
        )
        editable_pixels = self._pixel_count(editable)

        # Only almost-black pixels inside the mandatory area are candidates.
        # Connected-component filtering removes shadows, asphalt texture and
        # isolated dark image details from the warning metric.
        near_black = candidate.convert("RGB").convert("L").point(
            lambda value: 255 if value <= 6 else 0,
            mode="L",
        )
        possible_placeholder = ImageChops.multiply(near_black, editable)
        array = np.asarray(possible_placeholder, dtype=np.uint8)
        array = cv2.morphologyEx(
            array,
            cv2.MORPH_OPEN,
            np.ones((5, 5), dtype=np.uint8),
            iterations=1,
        )
        array = cv2.morphologyEx(
            array,
            cv2.MORPH_CLOSE,
            np.ones((9, 9), dtype=np.uint8),
            iterations=1,
        )

        labels_count, _, stats, _ = cv2.connectedComponentsWithStats(
            array,
            connectivity=8,
        )
        significant_pixels = 0
        component_count = 0
        largest_component_pixels = 0
        for label_index in range(1, labels_count):
            area = int(stats[label_index, cv2.CC_STAT_AREA])
            if area < self.minimum_unfilled_component_pixels:
                continue
            component_count += 1
            significant_pixels += area
            largest_component_pixels = max(largest_component_pixels, area)

        detected_ratio = significant_pixels / float(max(1, editable_pixels))
        warning = component_count > 0
        return {
            "editable_pixels": editable_pixels,
            "unfilled_editable_pixels": significant_pixels,
            "unfilled_editable_ratio": round(detected_ratio, 6),
            "unfilled_component_count": component_count,
            "largest_unfilled_component_pixels": largest_component_pixels,
            "outpaint_qc_warning": warning,
            "outpaint_qc_status": "warning" if warning else "passed",
            "outpaint_qc_blocking": False,
            "outpaint_qc_policy": self.outpaint_qc_policy,
        }


_engine_module.OpenRouterImageEngine = OpenRouterImageEngine
