__version__ = "0.8.0"

# Load provider-specific policies before app.main imports the image engine.
from . import provider_policy as _provider_policy  # noqa: F401,E402
