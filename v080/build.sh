#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

cp -f "$ROOT/ui_single_window/index.html" "$ROOT/app/web/index.html"
cp -f "$ROOT/ui_single_window/styles.css" "$ROOT/app/web/styles.css"
cp -f "$ROOT/ui_single_window/app-v080.js" "$ROOT/app/web/app-v080.js"
cp -f "$ROOT/ui_single_window/marins-logo.svg" "$ROOT/app/web/marins-logo.svg"

find "$ROOT" -type d -name __pycache__ -prune -exec rm -rf {} +
find "$ROOT" -type f -name '*.pyc' -delete
python -m pip install -r requirements.txt
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
engine = OpenRouterImageEngine()
assert OpenRouterImageEngine.transport_engine_version == "2.4.0"
assert engine.transmit_max_request_bytes <= 32 * 1024 * 1024
assert OpenRouterImageEngine._select_provider_size(8064, 6048) == (1536, 1024)
assert engine.minimum_editable_pixels >= 64
print(
    f"Transport engine {OpenRouterImageEngine.transport_engine_version}; "
    f"transmit ceiling {engine.transmit_max_request_bytes} bytes; "
    "empty-mask credit guard active; 8064x6048 provider canvas 1536x1024"
)
PY
echo "Marins Facade v0.8.0 meaningful-generation build passed"
