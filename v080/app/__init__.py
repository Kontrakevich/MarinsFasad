__version__ = "0.8.0"

# Runtime policy is intentionally composed in one place only.
# Obsolete policy layers were removed so nothing can override the active engine.
from . import stable_engine as _stable_engine  # noqa: F401,E402
