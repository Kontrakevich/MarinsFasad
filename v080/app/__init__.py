__version__ = "0.8.0"

# Load provider transport policy first, then apply the final Nano Banana-only
# selective-edit contract before app.main imports the image engine.
from . import provider_policy as _provider_policy  # noqa: F401,E402
from . import selective_policy as _selective_policy  # noqa: F401,E402
