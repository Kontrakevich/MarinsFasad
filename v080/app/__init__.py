__version__ = "0.8.1"

# One canonical runtime entrypoint. skill_engine owns HYBRID / RELIGHT /
# IMAGE EDIT / OUTPAINT plus DRAFT / STANDARD / HIGH / MAX quality profiles.
from . import skill_engine as _skill_engine  # noqa: F401,E402
