__version__ = "0.8.1"

# Canonical generation runtime. skill_engine owns HYBRID / RELIGHT /
# IMAGE EDIT / OUTPAINT plus DRAFT / STANDARD / HIGH / MAX quality profiles.
from . import skill_engine as _skill_engine  # noqa: F401,E402

# Final transport resilience layer: retry only transient OpenRouter gateway/network
# failures without changing generation semantics or duplicating user jobs.
from . import provider_retry as _provider_retry  # noqa: F401,E402

# Deterministic Intent -> Skill preflight. A strict OUTPAINT request containing
# semantic edits is promoted to HYBRID before prompt transport.
from .intelligence import intent_integration as _intent_skill_router  # noqa: F401,E402

# System №1 Intelligence is native and observational: Layer 1 technical diagnosis
# always precedes the gated Layer 2 human/logical alignment analysis.
from .intelligence import integration as _system1_intelligence  # noqa: F401,E402
