from __future__ import annotations

import sys
from pathlib import Path


# Keep direct `pytest` and IDE test runs independent from shell environment.
V080_ROOT = Path(__file__).resolve().parents[1]
root = str(V080_ROOT)
if root not in sys.path:
    sys.path.insert(0, root)
