#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="/tmp/marins-facade-v080.pid"
LOG_FILE="/tmp/marins-facade-v080.log"
HEALTH_FILE="/tmp/marins-facade-v080-health.json"
EXPECTED_TRANSPORT_ENGINE="2.9.1"
EXPECTED_PROMPT_CONTRACT="environment-system-v1.4"
EXPECTED_MODEL="google/gemini-2.5-flash-image"

if [ -f "/tmp/marins-facade-v060.pid" ]; then
  LEGACY_PID="$(cat /tmp/marins-facade-v060.pid 2>/dev/null || true)"
  if [ -n "$LEGACY_PID" ] && kill -0 "$LEGACY_PID" 2>/dev/null; then
    kill "$LEGACY_PID" 2>/dev/null || true
    sleep 1
    kill -9 "$LEGACY_PID" 2>/dev/null || true
  fi
  rm -f /tmp/marins-facade-v060.pid
fi

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
  sleep 2
fi
if ss -ltnp 2>/dev/null | grep -q ':8070 '; then
  PORT_PIDS="$(fuser 8070/tcp 2>/dev/null || true)"
  [ -z "$PORT_PIDS" ] || kill -9 $PORT_PIDS 2>/dev/null || true
  sleep 1
fi

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
grep -q 'approved-geometry-only' "$ROOT/app/main.py"
grep -q 'automatic-from-approved-geometry' "$ROOT/app/main.py"
grep -q 'single-approved-geometry-reference' "$ROOT/app/prompt_enforcement_policy.py"
grep -q 'transport_engine_version = "2.9.1"' "$ROOT/app/geometry_only_outpaint_policy.py"
grep -q 'internal-derived-outpaint-tile' "$ROOT/app/geometry_only_outpaint_policy.py"
! grep -q 'geometry_outpaint_mask' "$ROOT/app/main.py"

find "$ROOT" -type d -name __pycache__ -prune -exec rm -rf {} +
find "$ROOT" -type f -name '*.pyc' -delete
python -B - "$EXPECTED_TRANSPORT_ENGINE" "$EXPECTED_PROMPT_CONTRACT" "$EXPECTED_MODEL" <<'PY'
import sys
from app.ai_engine import OpenRouterImageEngine
from app.main import health
from app.system_prompts import PROMPT_CONTRACT_VERSION

expected_engine, expected_prompt, expected_model = sys.argv[1:4]
engine = OpenRouterImageEngine()
actual = OpenRouterImageEngine.transport_engine_version
if actual != expected_engine:
    raise SystemExit(f"Transport engine mismatch: expected {expected_engine}, got {actual}")
if PROMPT_CONTRACT_VERSION != expected_prompt:
    raise SystemExit(f"Prompt contract mismatch: expected {expected_prompt}, got {PROMPT_CONTRACT_VERSION}")
if engine.model != expected_model or engine.required_model != expected_model:
    raise SystemExit(f"Model lock mismatch: expected {expected_model}, got {engine.model}")
if engine.environment_input_policy != "approved-geometry-only":
    raise SystemExit("Geometry-only environment input is not active")
if engine.outpaint_detection_policy != "automatic-from-approved-geometry-transparency":
    raise SystemExit("Automatic outpaint detection is not active")
if engine.user_mask_required is not False:
    raise SystemExit("A user mask must never be required")
if engine.internal_outpaint_tiles_allowed is not True:
    raise SystemExit("Internal outpaint tiles must be allowed")
if engine.provider_input_policy != "single-approved-geometry-reference":
    raise SystemExit("Nano Banana must receive one geometry reference")
health_payload = health()
if health_payload.get("generation_mode") != "background-job-polling":
    raise SystemExit("Background generation polling is not active")
if health_payload.get("environment_input") != "approved-geometry-only":
    raise SystemExit("Health signature does not expose geometry-only input")
print(f"Transport engine {actual} verified")
print(f"Prompt contract: {PROMPT_CONTRACT_VERSION}")
print(f"Image model locked: {engine.model}")
print("Environment input: approved corrected geometry only")
print("Outpaint detection: automatic from missing transparent regions")
print("User mask: does not exist")
print("Internal outpaint tiles: derived from approved geometry and allowed")
print("Provider input: one approved geometry reference")
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
    echo "Marins Facade v0.8.0 process exited during startup." >&2
    tail -100 "$LOG_FILE" >&2 || true
    rm -f "$PID_FILE"
    exit 1
  fi
  if curl -fsS http://127.0.0.1:8070/api/health >"$HEALTH_FILE" 2>/dev/null; then
    if python -B - "$HEALTH_FILE" "$EXPECTED_MODEL" <<'PY'
import json, sys
payload = json.load(open(sys.argv[1], encoding='utf-8'))
expected_model = sys.argv[2]
ok = (
    payload.get('runtime') == 'standalone-v080'
    and payload.get('version') == '0.8.0'
    and payload.get('generation_mode') == 'background-job-polling'
    and payload.get('image_model') == expected_model
    and payload.get('environment_input') == 'approved-geometry-only'
    and payload.get('outpaint_detection') == 'automatic-from-approved-geometry'
)
raise SystemExit(0 if ok else 1)
PY
    then
      echo "Marins Facade v0.8.0 standalone started on port 8070 (PID $NEW_PID)"
      echo "Transport engine: $EXPECTED_TRANSPORT_ENGINE"
      echo "Prompt contract: $EXPECTED_PROMPT_CONTRACT"
      echo "Image model: $EXPECTED_MODEL"
      echo "Environment input: approved geometry only"
      echo "Outpaint: automatic"
      cat "$HEALTH_FILE"
      exit 0
    fi
  fi
  sleep 1
done

echo "Server did not expose the required geometry-only automatic-outpaint signature." >&2
tail -100 "$LOG_FILE" >&2 || true
cleanup_failed_start
exit 1
