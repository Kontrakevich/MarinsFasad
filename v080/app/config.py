from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "Marins Facade Control Center"
APP_VERSION = "0.8.1"
PORT = int(os.getenv("PORT", "8070"))
ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path(os.getenv("MARINS_DATA_ROOT", ROOT / "data" / "projects"))
STATIC_ROOT = ROOT / "app" / "web"
DATA_ROOT.mkdir(parents=True, exist_ok=True)
