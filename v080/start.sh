#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="/tmp/marins-facade-v080.pid"
LOG_FILE="/tmp/marins-facade-v080.log"
HEALTH_FILE="/tmp/marins-facade-v080-health.json"
EXPECTED_TRANSPORT_ENGINE="3.2.0"
EXPECTED_PROMPT_CONTRACT="environment-system-v1.5-hybrid"
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
sed -i 's/resilient-fullframe-0806/hybrid-two-pass-3200/g; s/selective-nanobanana-0806/hybrid-two-pass-3200/g; s/geometry-only-outpaint-0806/hybrid-two-pass-3200/g; s/stable-nanobanana-3000/hybrid-two-pass-3200/g; s/working-master-3001/hybrid-two-pass-3200/g; s/hybrid-edit-3100/hybrid-two-pass-3200/g' "$ROOT/app/web/index.html"
sed -i 's/V0.8.0/V0.8.1 HYBRID/g; s/ORIGINAL MASTER/WORKING MASTER/g; s/NO DOWNSCALE/GENERATION SCALE/g; s/Файл сохраняется без уменьшения и перекодирования. Preview существует отдельно./Оригинал сохраняется в архиве проекта. Для сетки и генерации используется облегчённый рабочий master./g' "$ROOT/app/web/index.html"
cp -f "$ROOT/ui_single_window/styles.css" "$ROOT/app/web/styles.css"
cat "$ROOT/ui_single_window/async-generation-bridge.js" "$ROOT/ui_single_window/app-v080.js" "$ROOT/ui_single_window/grid-ux-patch.js" "$ROOT/ui_single_window/hybrid-mode-patch.js" > "$ROOT/app/web/app-v080.js"
sed -i 's/Сгенерируйте окружение по всему canvas/Выполните image edit и дорисуйте отсутствующее окружение/g' "$ROOT/app/web/app-v080.js"
sed -i 's/Дорисуйте отсутствующее окружение и выполните точные изменения из промпта/Выполните image edit и дорисуйте отсутствующее окружение/g' "$ROOT/app/web/app-v080.js"
sed -i 's/Production policy: original resolution\./Рабочий master оптимизирован до размера генерации; исходный файл сохранён в архиве проекта./g' "$ROOT/app/web/app-v080.js"
sed -i 's/V0.8.0 HYBRID/V0.8.1 HYBRID/g' "$ROOT/app/web/app-v080.js"
cp -f "$ROOT/ui_single_window/marins-logo.svg" "$ROOT/app/web/marins-logo.svg"

grep -q 'HYBRID · EDIT + OUTPAINT' "$ROOT/app/web/app-v080.js"
grep -q 'const ZOOM_STEP = 0.05' "$ROOT/app/web/app-v080.js"
grep -q 'requestGridFullscreen' "$ROOT/app/web/app-v080.js"
grep -q 'hybrid_engine' "$ROOT/app/__init__.py"
grep -q 'transport_engine_version = "3.2.0"' "$ROOT/app/hybrid_engine.py"
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
if engine.available_generation_modes != ("hybrid", "edit", "outpaint"):
    raise SystemExit("Hybrid generation modes are not active")
if engine.default_generation_mode != "hybrid":
    raise SystemExit("Hybrid must be the default generation mode")
if engine.outpaint_repair_mode != "hybrid-second-pass":
    raise SystemExit("Hybrid second-pass outpaint is not active")
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
print("Hybrid Engine 3.2.0 verified")
print(f"App version: {APP_VERSION}")
print(f"Prompt contract: {PROMPT_CONTRACT_VERSION}")
print(f"Image model locked: {engine.model}")
print("HYBRID: semantic image edit first; outpaint second when missing regions exist")
print("IMAGE EDIT: object cleanup, wires, poles, weather and atmosphere")
print("OUTPAINT: strict missing-region reconstruction")
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
    echo "Marins Facade v0.8.1 Hybrid process exited during startup." >&2
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
      echo "Marins Facade v0.8.1 Hybrid started on port 8070 (PID $NEW_PID)"
      echo "Transport engine: $EXPECTED_TRANSPORT_ENGINE"
      echo "Prompt contract: $EXPECTED_PROMPT_CONTRACT"
      echo "Image model: $EXPECTED_MODEL"
      echo "Default generation mode: HYBRID two-pass"
      cat "$HEALTH_FILE"
      exit 0
    fi
  fi
  sleep 1
done

echo "Server did not expose the required v0.8.1 Hybrid runtime." >&2
tail -100 "$LOG_FILE" >&2 || true
cleanup_failed_start
exit 1
