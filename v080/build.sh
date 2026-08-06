#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

cp -f "$ROOT/ui_single_window/index.html" "$ROOT/app/web/index.html"
cp -f "$ROOT/ui_single_window/styles.css" "$ROOT/app/web/styles.css"
cat "$ROOT/ui_single_window/async-generation-bridge.js" "$ROOT/ui_single_window/app-v080.js" > "$ROOT/app/web/app-v080.js"
cp -f "$ROOT/ui_single_window/marins-logo.svg" "$ROOT/app/web/marins-logo.svg"

grep -q 'resilient-fullframe-0806' "$ROOT/app/web/index.html"
grep -q 'TRANSIENT_HTTP_STATUSES' "$ROOT/app/web/app-v080.js"
grep -q 'background-job-polling' "$ROOT/app/main.py"

find "$ROOT" -type d -name __pycache__ -prune -exec rm -rf {} +
find "$ROOT" -type f -name '*.pyc' -delete
python -m pip install -r requirements.txt

python - <<'PY'
import cv2
import numpy
from app.geometry_engine import GeometryEngine

assert cv2.__version__
assert numpy.__version__
assert GeometryEngine
print(f"OpenCV {cv2.__version__} and NumPy {numpy.__version__} verified")
PY

python -m compileall -f app

if command -v node >/dev/null 2>&1; then
  node --check app/web/app-v080.js
  echo "Frontend JavaScript syntax check passed"
else
  echo "Node.js not found; skipping optional frontend JavaScript syntax check"
fi

export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
rm -rf .test-data
MARINS_DATA_ROOT="$ROOT/.test-data/projects" python -m pytest -q
rm -rf .test-data
python - <<'PY'
from app.ai_engine import OpenRouterImageEngine
from app.main import health
from app.system_prompts import PROMPT_CONTRACT_VERSION

engine = OpenRouterImageEngine()
assert OpenRouterImageEngine.transport_engine_version == "2.6.0"
assert engine.transmit_max_request_bytes <= 32 * 1024 * 1024
assert OpenRouterImageEngine._select_provider_size(8064, 6048) == (1536, 1024)
assert PROMPT_CONTRACT_VERSION == "environment-system-v1.2"
assert health()["generation_mode"] == "background-job-polling"
assert engine.minimum_full_frame_change_ratio > 0
assert engine.minimum_non_mask_change_ratio > 0
print(
    f"Transport engine {OpenRouterImageEngine.transport_engine_version}; "
    f"transmit ceiling {engine.transmit_max_request_bytes} bytes; "
    f"prompt contract {PROMPT_CONTRACT_VERSION}; "
    "background generation polling active; "
    "transient Codespaces 502/503/504 retries active; "
    "full-frame geometry-reference generation active; "
    "mask is QC-only"
)
PY
echo "Marins Facade v0.8.0 resilient full-frame environment generation build passed"
