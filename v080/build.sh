#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

cp -f "$ROOT/ui_single_window/index.html" "$ROOT/app/web/index.html"
sed -i 's/resilient-fullframe-0806/geometry-only-outpaint-0806/g; s/selective-nanobanana-0806/geometry-only-outpaint-0806/g' "$ROOT/app/web/index.html"
cp -f "$ROOT/ui_single_window/styles.css" "$ROOT/app/web/styles.css"
cat "$ROOT/ui_single_window/async-generation-bridge.js" "$ROOT/ui_single_window/app-v080.js" > "$ROOT/app/web/app-v080.js"
sed -i 's/Сгенерируйте окружение по всему canvas/Автоматически дорисуйте отсутствующее окружение/g' "$ROOT/app/web/app-v080.js"
sed -i 's/Внесите только указанные точечные изменения через Nano Banana/Автоматически дорисуйте отсутствующее окружение/g' "$ROOT/app/web/app-v080.js"
cp -f "$ROOT/ui_single_window/marins-logo.svg" "$ROOT/app/web/marins-logo.svg"

grep -q 'geometry-only-outpaint-0806' "$ROOT/app/web/index.html"
grep -q 'Автоматически дорисуйте отсутствующее окружение' "$ROOT/app/web/app-v080.js"
grep -q 'TRANSIENT_HTTP_STATUSES' "$ROOT/app/web/app-v080.js"
grep -q 'background-job-polling' "$ROOT/app/main.py"
grep -q 'approved-geometry-only' "$ROOT/app/main.py"
grep -q 'automatic-from-approved-geometry' "$ROOT/app/main.py"
grep -q 'single-approved-geometry-reference' "$ROOT/app/prompt_enforcement_policy.py"
grep -q 'approved-geometry-only' "$ROOT/app/geometry_only_outpaint_policy.py"
grep -q 'OutpaintPlanEngine' "$ROOT/app/outpaint_plan.py"
! grep -q 'geometry_outpaint_mask' "$ROOT/app/main.py"

find "$ROOT" -type d -name __pycache__ -prune -exec rm -rf {} +
find "$ROOT" -type f -name '*.pyc' -delete
python -m pip install -r requirements.txt

python - <<'PY'
import cv2
import numpy
from app.geometry_engine import GeometryEngine
from app.outpaint_plan import OutpaintPlanEngine
assert cv2.__version__
assert numpy.__version__
assert GeometryEngine
assert OutpaintPlanEngine
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
OPENROUTER_API_KEY="" \
OPENROUTER_IMAGE_MODEL="must-be-ignored/test-model" \
OPENROUTER_CAPABILITY_TIMEOUT="1" \
OPENROUTER_IMAGE_TIMEOUT="5" \
MARINS_DATA_ROOT="$ROOT/.test-data/projects" \
python -m pytest -vv --timeout=60 --timeout-method=thread
rm -rf .test-data

python - <<'PY'
import os
from app.ai_engine import OpenRouterImageEngine
from app.main import health
from app.system_prompts import PROMPT_CONTRACT_VERSION

os.environ["OPENROUTER_IMAGE_MODEL"] = "must-be-ignored/test-model"
engine = OpenRouterImageEngine()
assert OpenRouterImageEngine.transport_engine_version == "2.9.0"
assert engine.model == "google/gemini-2.5-flash-image"
assert engine.required_model == "google/gemini-2.5-flash-image"
assert engine.environment_input_policy == "approved-geometry-only"
assert engine.outpaint_detection_policy == "automatic-from-approved-geometry-transparency"
assert engine.user_mask_required is False
assert engine.provider_input_policy == "single-approved-geometry-reference"
assert PROMPT_CONTRACT_VERSION == "environment-system-v1.4"
assert health()["generation_mode"] == "background-job-polling"
assert health()["environment_input"] == "approved-geometry-only"
assert health()["outpaint_detection"] == "automatic-from-approved-geometry"
print(
    f"Transport engine {OpenRouterImageEngine.transport_engine_version}; "
    f"model {engine.model}; "
    f"prompt contract {PROMPT_CONTRACT_VERSION}; "
    "approved geometry is the only project input; "
    "missing surroundings are detected automatically; "
    "Nano Banana receives one geometry reference"
)
PY

echo "Marins Facade v0.8.0 geometry-only automatic outpaint build passed"
