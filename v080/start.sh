#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="/tmp/marins-facade-v080.pid"
LOG_FILE="/tmp/marins-facade-v080.log"
HEALTH_FILE="/tmp/marins-facade-v080-health.json"
EXPECTED_TRANSPORT_ENGINE="3.4.0"
EXPECTED_PROMPT_CONTRACT="environment-system-v1.7-quality-outpaint"
EXPECTED_MODEL="google/gemini-2.5-flash-image"
EXPECTED_APP_VERSION="0.8.1"

if [ -f "$PID_FILE" ]; then
  OLD_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
    kill "$OLD_PID" 2>/dev/null || true
    sleep 1
  fi
fi

PORT_PIDS="$(fuser 8070/tcp 2>/dev/null || true)"
if [ -n "$PORT_PIDS" ]; then
  kill $PORT_PIDS 2>/dev/null || true
  sleep 1
fi

cd "$ROOT"
cp -f "$ROOT/ui_single_window/index.html" "$ROOT/app/web/index.html"
sed -i 's/resilient-fullframe-0806/quality-outpaint-3400/g; s/selective-nanobanana-0806/quality-outpaint-3400/g; s/geometry-only-outpaint-0806/quality-outpaint-3400/g; s/stable-nanobanana-3000/quality-outpaint-3400/g; s/working-master-3001/quality-outpaint-3400/g; s/hybrid-edit-3100/quality-outpaint-3400/g; s/hybrid-two-pass-3200/quality-outpaint-3400/g; s/skill-contracts-3300/quality-outpaint-3400/g' "$ROOT/app/web/index.html"
sed -i 's/V0.8.0/V0.8.1 QUALITY/g; s/ORIGINAL MASTER/WORKING MASTER/g; s/NO DOWNSCALE/GENERATION SCALE/g; s/Файл сохраняется без уменьшения и перекодирования. Preview существует отдельно./Оригинал сохраняется в архиве проекта. Для сетки и генерации используется облегчённый рабочий master./g' "$ROOT/app/web/index.html"
cp -f "$ROOT/ui_single_window/styles.css" "$ROOT/app/web/styles.css"
cat "$ROOT/ui_single_window/async-generation-bridge.js" "$ROOT/ui_single_window/app-v080.js" "$ROOT/ui_single_window/grid-ux-patch.js" "$ROOT/ui_single_window/hybrid-mode-patch.js" > "$ROOT/app/web/app-v080.js"
sed -i 's/Сгенерируйте окружение по всему canvas/Выполните выбранный skill генерации/g' "$ROOT/app/web/app-v080.js"
sed -i 's/Дорисуйте отсутствующее окружение и выполните точные изменения из промпта/Выполните выбранный skill генерации/g' "$ROOT/app/web/app-v080.js"
sed -i 's/Production policy: original resolution\./Рабочий master оптимизирован до размера генерации; исходный файл сохранён в архиве проекта./g' "$ROOT/app/web/app-v080.js"
sed -i 's/V0.8.0 HYBRID/V0.8.1 QUALITY/g; s/V0.8.1 HYBRID/V0.8.1 QUALITY/g; s/V0.8.1 SKILLS/V0.8.1 QUALITY/g' "$ROOT/app/web/app-v080.js"
cp -f "$ROOT/ui_single_window/marins-logo.svg" "$ROOT/app/web/marins-logo.svg"

grep -q 'RELIGHT · NEW LIGHTING' "$ROOT/app/web/app-v080.js"
grep -q 'environment-quality' "$ROOT/app/web/app-v080.js"
grep -q 'const ZOOM_STEP = 0.05' "$ROOT/app/web/app-v080.js"
grep -q 'requestGridFullscreen' "$ROOT/app/web/app-v080.js"
grep -q 'skill_engine' "$ROOT/app/__init__.py"
grep -q 'transport_engine_version = "3.4.0"' "$ROOT/app/skill_engine.py"
grep -q 'quality-aware-edge-refine' "$ROOT/app/skill_engine.py"
grep -q "$EXPECTED_PROMPT_CONTRACT" "$ROOT/app/system_prompts.py"

python -B - "$EXPECTED_TRANSPORT_ENGINE" "$EXPECTED_PROMPT_CONTRACT" "$EXPECTED_MODEL" "$EXPECTED_APP_VERSION" <<'PY'
import sys
from app.ai_engine import OpenRouterImageEngine
from app.config import APP_VERSION
from app.image_engine import ImageEngine
from app.system_prompts import PROMPT_CONTRACT_VERSION

expected_engine, expected_prompt, expected_model, expected_version = sys.argv[1:5]
engine = OpenRouterImageEngine()
image_engine = ImageEngine()
if OpenRouterImageEngine.transport_engine_version != expected_engine:
    raise SystemExit(f"Transport engine mismatch: expected {expected_engine}, got {OpenRouterImageEngine.transport_engine_version}")
if APP_VERSION != expected_version:
    raise SystemExit(f"App version mismatch: expected {expected_version}, got {APP_VERSION}")
if PROMPT_CONTRACT_VERSION != expected_prompt:
    raise SystemExit(f"Prompt contract mismatch: expected {expected_prompt}, got {PROMPT_CONTRACT_VERSION}")
if engine.model != expected_model or engine.required_model != expected_model:
    raise SystemExit(f"Model lock mismatch: expected {expected_model}, got {engine.model}")
if engine.available_generation_modes != ("hybrid", "relight", "edit", "outpaint"):
    raise SystemExit("Skill generation modes are not active")
if engine.available_generation_qualities != ("draft", "standard", "high", "max"):
    raise SystemExit("Generation quality profiles are not active")
if engine.default_generation_quality != "high":
    raise SystemExit("HIGH must be the default generation quality")
if engine.default_generation_mode != "hybrid":
    raise SystemExit("Hybrid must be the default generation mode")
if engine.outpaint_repair_mode != "hybrid-second-pass":
    raise SystemExit("Hybrid second-pass outpaint is not active")
if engine.outpaint_fallback_mode != "quality-aware-edge-refine":
    raise SystemExit("Quality-aware edge refinement is not active")
if engine.skill_contract_version != "outpaint-relight-edit-hybrid-quality-v2":
    raise SystemExit("Quality skill contract is not active")
if engine.missing_region_transport_policy != "native-transparency-single-reference":
    raise SystemExit("Native transparent reference transport is not active")
if engine.environment_input_policy != "approved-geometry-only":
    raise SystemExit("Geometry-only input policy is inactive")
if engine.provider_input_policy != "single-approved-geometry-reference":
    raise SystemExit("Nano Banana must receive one visual reference per pass")
if engine.user_mask_required is not False:
    raise SystemExit("User mask must not exist")
if image_engine._generation_canvas(8064, 6048) != engine._select_provider_size(8064, 6048):
    raise SystemExit("Working-master scale does not match generation scale")
print("Skill Engine 3.4.0 verified")
print(f"App version: {APP_VERSION}")
print(f"Prompt contract: {PROMPT_CONTRACT_VERSION}")
print(f"Image model locked: {engine.model}")
print("Default skill: HYBRID")
print("Generation quality: DRAFT / STANDARD / HIGH / MAXIMUM; default HIGH")
print("OUTPAINT HIGH/MAX: automatic context-rich edge refinement")
print("OUTPAINT seams: tone harmonization + feather only inside missing regions")
print("Prompt: complete compiled context propagated to outpaint/refinement")
print("Original source: archived; working master reduced before Perspective Grid")
PY

: > "$LOG_FILE"
PYTHONDONTWRITEBYTECODE=1 nohup setsid python -B -m uvicorn app.main:app --host 0.0.0.0 --port 8070 >"$LOG_FILE" 2>&1 </dev/null &
NEW_PID=$!
echo "$NEW_PID" > "$PID_FILE"

cleanup_failed_start() {
  kill "$NEW_PID" 2>/dev/null || true
  sleep 1
  kill -9 "$NEW_PID" 2>/dev/null || true
  rm -f "$PID_FILE"
}

for _ in $(seq 1 30); do
  if ! kill -0 "$NEW_PID" 2>/dev/null; then
    echo "Marins Facade v0.8.1 Quality process exited during startup." >&2
    tail -100 "$LOG_FILE" >&2 || true
    rm -f "$PID_FILE"
    exit 1
  fi
  if curl -fsS http://127.0.0.1:8070/api/health >"$HEALTH_FILE" 2>/dev/null; then
    if python -B - "$HEALTH_FILE" "$EXPECTED_MODEL" "$EXPECTED_APP_VERSION" <<'PY'
import json, sys
payload = json.load(open(sys.argv[1], encoding='utf-8'))
expected_model, expected_version = sys.argv[2:4]
ok = (
    payload.get('runtime') == 'standalone-v080'
    and payload.get('version') == expected_version
    and payload.get('generation_mode') == 'background-job-polling'
    and payload.get('image_model') == expected_model
    and payload.get('environment_input') == 'approved-geometry-only'
    and payload.get('outpaint_detection') == 'automatic-from-approved-geometry'
)
raise SystemExit(0 if ok else 1)
PY
    then
      echo "Marins Facade v0.8.1 Quality started on port 8070 (PID $NEW_PID)"
      echo "Transport engine: $EXPECTED_TRANSPORT_ENGINE"
      echo "Prompt contract: $EXPECTED_PROMPT_CONTRACT"
      echo "Image model: $EXPECTED_MODEL"
      echo "Default skill: HYBRID"
      echo "Default quality: HIGH"
      echo "Outpaint refinement: quality-aware-edge-refine"
      cat "$HEALTH_FILE"
      exit 0
    fi
  fi
  sleep 1
done

echo "Server did not expose the required v0.8.1 Quality runtime." >&2
tail -100 "$LOG_FILE" >&2 || true
cleanup_failed_start
exit 1
