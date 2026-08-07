__version__ = "0.8.1"

# One canonical runtime entrypoint. skill_engine extends the stable two-pass
# hybrid transport with explicit OUTPAINT / RELIGHT / IMAGE EDIT skill contracts.
from . import skill_engine as _skill_engine  # noqa: F401,E402
