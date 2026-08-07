#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

cp -f "$ROOT/ui_single_window/index.html" "$ROOT/app/web/index.html"
sed -i 's/resilient-fullframe-0806/skill-contracts-3300/g; s/selective-nanobanana-0806/skill-contracts-3300/g; s/geometry-only-outpaint-0806/skill-contracts-3300/g; s/stable-nanobanana-3000/skill-contracts-3300/g; s/working-master-3001/skill-contracts-3300/g; s/hybrid-edit-3100/skill-contracts-3300/g; s/hybrid-two-pass-3200/skill-contracts-3300/g' "$ROOT/app/web/index.html"
sed -i 's/V0.8.0/V0.8.1 SKILLS/g; s/ORIGINAL MASTER/WORKING MASTER/g; s/NO DOWNSCALE/GENERATION SCALE/g; s/Файл сохраняется без уменьшения и перекодирования. Preview существует отдельно./Оригинал сохраняется в архиве проекта. Для сетки и генерации используется облегчённый рабочий master./g' "$ROOT/app/web/index.html"
cp -f "$ROOT/ui_single_window/styles.css" "$ROOT/app/web/styles.css"
cat "$ROOT/ui_single_window/async-generation-bridge.js" "$ROOT/ui_single_window/app-v080.js" "$ROOT/ui_single_window/grid-ux-patch.js" "$ROOT/ui_single_window/hybrid-mode-patch.js" > "$ROOT/app/web/app-v080.js"
sed -i 's/Сгенерируйте окружение по всему canvas/Выполните выбранный skill генерации/g' "$ROOT/app/web/app-v080.js"
sed -i 's/Дорисуйте отсутствующее окружение и выполните точные изменения из промпта/Выполните выбранный skill генерации/g' "$ROOT/app/web/app-v080.js"
sed -i 's/Production policy: original resolution\./Рабочий master оптимизирован до размера генерации; исходный файл сохранён в архиве проекта./g' "$ROOT/app/web/app-v080.js"
sed -i 's/V0.8.0 HYBRID/V0.8.1 SKILLS/g; s/V0.8.1 HYBRID/V0.8.1 SKILLS/g' "$ROOT/app/web/app-v080.js"
cp -f "$ROOT/ui_single_window/marins-logo.svg" "$ROOT/app/web/marins-logo.svg"

grep -q 'skill-contracts-3300' "$ROOT/app/web/index.html"
grep -q 'TRANSIENT_HTTP_STATUSES' "$ROOT/app/web/app-v080.js"
grep -q 'const ZOOM_STEP = 0.05' "$ROOT/app/web/app-v080.js"
grep -q 'requestGridFullscreen' "$ROOT/app/web/app-v080.js"
grep -q 'RELIGHT · NEW LIGHTING' "$ROOT/app/web/app-v080.js"
grep -q 'IMAGE EDIT' "$ROOT/app/web/app-v080.js"
grep -q 'OUTPAINT' "$ROOT/app/web/app-v080.js"
grep -q '__MARINS_GENERATION_MODE__' "$ROOT/app/web/app-v080.js"
grep -q 'skill_engine' "$ROOT/app/__init__.py"
grep -q 'transport_engine_version = "3.3.0"' "$ROOT/app/skill_engine.py"
grep -q 'edge-tiles-on-placeholder' "$ROOT/app/skill_engine.py"
grep -q '_run_edge_tile_fallback' "$ROOT/app/skill_engine.py"
grep -q 'environment-system-v1.6-skill-contracts' "$ROOT/app/system_prompts.py"
grep -q 'generation-sized-working-master' "$ROOT/app/image_engine.py"

find "$ROOT" -type d -name __pycache__ -prune -exec rm -rf {} +
find "$ROOT" -type f -name '*.pyc' -delete
python -m pip install -r requirements.txt

python - <<'PY'
import cv2
import numpy
from app.ai_engine import OpenRouterImageEngine
from app.geometry_engine import GeometryEngine
from app.image_engine import ImageEngine
from app.outpaint_plan import OutpaintPlanEngine
from app.prompt_engine import PromptEngine
from app.system_prompts import PROMPT_CONTRACT_VERSION

engine = OpenRouterImageEngine()
image_engine = ImageEngine()
assert GeometryEngine
assert OutpaintPlanEngine
assert OpenRouterImageEngine.transport_engine_version == "3.3.0"
assert engine.model == "google/gemini-2.5-flash-image"
assert engine.required_model == "google/gemini-2.5-flash-image"
assert engine.available_generation_modes == ("hybrid", "relight", "edit", "outpaint")
assert engine.default_generation_mode == "hybrid"
assert engine.environment_input_policy == "approved-geometry-only"
assert engine.outpaint_detection_policy == "automatic-from-approved-geometry-transparency"
assert engine.provider_input_policy == "single-approved-geometry-reference"
assert engine.missing_region_transport_policy == "native-transparency-single-reference"
assert engine.user_mask_required is False
assert engine.internal_outpaint_tiles_allowed is False
assert engine.outpaint_repair_mode == "hybrid-second-pass"
assert engine.skill_contract_version == "outpaint-relight-edit-hybrid-v1"
assert engine.outpaint_fallback_mode == "edge-tiles-on-placeholder"
assert engine.outpaint_fallback_attempts_per_edge == 2
assert engine.outpaint_initial_qc_blocking is False
assert PROMPT_CONTRACT_VERSION == "environment-system-v1.6-skill-contracts"
assert PromptEngine._normalize_mode("relight") == "relight"
assert PromptEngine._normalize_mode("edit") == "edit"
assert PromptEngine._normalize_mode("outpaint") == "outpaint"
assert PromptEngine._normalize_mode("anything") == "hybrid"
assert image_engine._generation_canvas(8064, 6048) == engine._select_provider_size(8064, 6048)
assert image_engine._fit_size((8064, 6048), (1536, 1024)) == (1365, 1024)
print(f"OpenCV {cv2.__version__} and NumPy {numpy.__version__} verified")
print("Skill Engine 3.3.0 verified")
print("Skills: HYBRID / RELIGHT / IMAGE EDIT / OUTPAINT")
print("OUTPAINT: full-frame attempt -> automatic edge-tile fallback on blank placeholder")
print("OUTPAINT fallback: TOP / BOTTOM / LEFT / RIGHT, up to 2 attempts per edge")
print("RELIGHT: full-frame photometric change; corrected geometry preserved")
print("IMAGE EDIT: requested semantic edits retained; no source-pixel restoration over edits")
print("HYBRID: edit/relight first, outpaint second, edge fallback when required")
print("Working master: generation-sized before Perspective Grid")
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

echo "Marins Facade v0.8.1 skill-contract build passed"
