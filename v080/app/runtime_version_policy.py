from __future__ import annotations

from . import ai_engine as _engine_module


_PreviousOpenRouterImageEngine = _engine_module.OpenRouterImageEngine


class OpenRouterImageEngine(_PreviousOpenRouterImageEngine):
    transport_engine_version = "2.7.2"


_engine_module.OpenRouterImageEngine = OpenRouterImageEngine
