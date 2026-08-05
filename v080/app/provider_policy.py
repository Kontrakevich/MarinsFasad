from __future__ import annotations

import re

from . import ai_engine as _engine_module


_BaseOpenRouterImageEngine = _engine_module.OpenRouterImageEngine


class OpenRouterImageEngine(_BaseOpenRouterImageEngine):
    """Provider policy applied before the application imports the engine.

    OpenRouter error messages contain both the rejected requested size and the
    valid sizes. Only values after `Supported sizes are` may be considered for
    the automatic retry.
    """

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


# Replace the module export before app.main or tests import it.
_engine_module.OpenRouterImageEngine = OpenRouterImageEngine
AIEngineError = _engine_module.AIEngineError
