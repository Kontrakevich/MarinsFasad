__version__ = "0.8.0"

# Compose the provider transport, Nano Banana selective editing, verbatim prompt
# transport, non-blocking diagnostics, zoomed reconstruction and adaptive tiles.
# The final policy exposes a geometry-only automatic-outpaint contract.
from . import provider_policy as _provider_policy  # noqa: F401,E402
from . import selective_policy as _selective_policy  # noqa: F401,E402
from . import prompt_enforcement_policy as _prompt_enforcement_policy  # noqa: F401,E402
from . import outpaint_qc_policy as _outpaint_qc_policy  # noqa: F401,E402
from . import missing_region_policy as _missing_region_policy  # noqa: F401,E402
from . import tile_planner_policy as _tile_planner_policy  # noqa: F401,E402
from . import runtime_version_policy as _runtime_version_policy  # noqa: F401,E402
from . import geometry_only_outpaint_policy as _geometry_only_outpaint_policy  # noqa: F401,E402
