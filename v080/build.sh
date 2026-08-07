#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

cp -f "$ROOT/ui_single_window/index.html" "$ROOT/app/web/index.html"
sed -i 's/resilient-fullframe-0806/stable-nanobanana-3000/g; s/selective-nanobanana-0806/stable-nanobanana-3000/g; s/geometry-only-outpaint-0806/stable-nanobanana-3000/g' "$ROOT/app/web/index.html"
cp -f "$ROOT/ui_single_window/styles.css" "$ROOT/app/web/styles.css"
cat "$ROOT/ui_single_window/async-generation-bridge.js" "$ROOT/ui_single_window/app-v080.js" "$ROOT/ui_single_window/grid-ux-patch.js" > "$ROOT/app/web/app-v080.js"
sed -i 's/Сгенерируйте окружение по всему canvas/Дорисуйте отсутствующее окружение и выполните точные изменения из промпта/g' "$ROOT/app/web/app-v080.js"
sed -i 's/Внесите только указанные точечные изменения через Nano Banana/Дорисуйте отсутствующее окружение и выполните точные изменения из промпта/g' "$ROOT/app/web/app-v080.js"
sed -i 's/Автоматически дорисуйте отсутствующее окружение/Дорисуйте отсутствующее окружение и выполните точные изменения из промпта/g' "$ROOT/app/web/app-v080.js"
cp -f "$ROOT/ui_single_window/marins-logo.svg" "$ROOT/app/web/marins-logo.svg"

grep -q 'stable-nanobanana-3000' "$ROOT/app/web/index.html"
grep -q 'TRANSIENT_HTTP_STATUSES' "$ROOT/app/web/app-v080.js"
grep -q 'const ZOOM_STEP = 0.05' "$ROOT/app/web/app-v080.js"
grep -q 'requestGridFullscreen' "$ROOT/app/web/app-v080.js"
grep -q 'stable_engine' "$ROOT/app/__init__.py"
grep -q 'transport_engine_version = "3.0.0"' "$ROOT/app/stable_engine.py"

find "$ROOT" -type d -name __pycache__ -prune -exec rm -rf {} +
find "$ROOT" -type f -name '*.pyc' -delete
python -m pip install -r requirements.txt

python - <<'PY'
import cv2
import numpy
from app.ai_engine import OpenRouterImageEngine
from app.geometry_engine import GeometryEngine
from app.outpaint_plan import OutpaintPlanEngine

engine = OpenRouterImageEngine()
assert GeometryEngine
assert OutpaintPlanEngine
assert OpenRouterImageEngine.transport_engine_version == "3.0.0"
assert engine.model == "google/gemini-2.5-flash-image"
assert engine.required_model == "google/gemini-2.5-flash-image"
assert engine.environment_input_policy == "approved-geometry-only"
assert engine.outpaint_detection_policy == "automatic-from-approved-geometry-transparency"
assert engine.provider_input_policy == "single-approved-geometry-reference"
assert engine.user_mask_required is False
assert engine.internal_outpaint_tiles_allowed is False
print(f"OpenCV {cv2.__version__} and NumPy {numpy.__version__} verified")
print("Stable engine 3.0.0 verified")
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
OPENROUTER_API_KEY="" \
OPENROUTER_IMAGE_MODEL="must-be-ignored/test-model" \
OPENROUTER_CAPABILITY_TIMEOUT="1" \
OPENROUTER_IMAGE_TIMEOUT="5" \
MARINS_DATA_ROOT="$ROOT/.test-data/projects" \
python -m pytest -vv --timeout=60 --timeout-method=thread
rm -rf .test-data

echo "Marins Facade v0.8.0 stable Nano Banana build passed"
