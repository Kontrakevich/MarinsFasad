__version__ = "0.8.0"

# Runtime policy is intentionally composed in one place only.
# Older policy modules remain in the repository as historical implementation
# notes but are not imported and cannot override the active engine.
from . import stable_engine as _stable_engine  # noqa: F401,E402
