__version__ = "0.8.1"

# Exactly one runtime layer is active. The hybrid engine subclasses the raw
# OpenRouter transport once and owns Edit / Outpaint / Hybrid execution.
from . import hybrid_engine as _hybrid_engine  # noqa: F401,E402
