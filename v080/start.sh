#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="/tmp/marins-facade-v080.pid"
LOG_FILE="/tmp/marins-facade-v080.log"
HEALTH_FILE="/tmp/marins-facade-v080-health.json"
EXPECTED_TRANSPORT_ENGINE="2.7.2"
EXPECTED_PROMPT_CONTRACT="environment-system-v1.3"
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
sed -i 's/resilient-fullframe-0806/selective-nanobanana-0806/g' "$ROOT/app/web/index.html"
cp -f "$ROOT/ui_single_window/styles.css" "$ROOT/app/web/styles.css"
cat "$ROOT/ui_single_window/async-generation-bridge.js" "$ROOT/ui_single_window/app-v080.js" > "$ROOT/app/web/app-v080.js"
sed -i 's/Сгенерируйте окружение по всему canvas/Внесите только указанные точечные изменения через Nano Banana/g' "$ROOT/app/web/app-v080.js"
cp -f "$ROOT/ui_single_window/marins-logo.svg" "$ROOT/app/web/marins-logo.svg"

grep -q 'selective-nanobanana-0806' "$ROOT/app/web/index.html"
grep -q 'Внесите только указанные точечные изменения через Nano Banana' "$ROOT/app/web/app-v080.js"
grep -q 'TRANSIENT_HTTP_STATUSES' "$ROOT/app/web/app-v080.js"
grep -q 'background-job-polling' "$ROOT/app/main.py"
grep -q 'outpaint_qc_policy' "$ROOT/app/outpaint_qc_policy.py"
grep -q 'opaque-chroma-marker-with-nano-banana-auto-retry' "$ROOT/app/missing_region_policy.py"
grep -q 'transport_engine_version = "2.7.2"' "$ROOT/app/runtime_version_policy.py"

find "$ROOT" -type d -name __pycache__ -prune -exec rm -rf {} +
find "$ROOT" -type f -name '*.pyc' -delete
python -B - "$EXPECTED_TRANSPORT_ENGINE" "$EXPECTED_PROMPT_CONTRACT" "$EXPECTED_MODEL" <<'PY'
import sys
from app.ai_engine import OpenRouterImageEngine
from app.main import health
from app.system_prompts import ENVIRONMENT_SYSTEM_PROMPT, PROMPT_CONTRACT_VERSION

expected_engine, expected_prompt, expected_model = sys.argv[1:4]
engine = OpenRouterImageEngine()
actual = OpenRouterImageEngine.transport_engine_version
if actual != expected_engine:
    raise SystemExit(f"Transport engine mismatch: expected {expected_engine}, got {actual}")
if PROMPT_CONTRACT_VERSION != expected_prompt:
    raise SystemExit(f"Prompt contract mismatch: expected {expected_prompt}, got {PROMPT_CONTRACT_VERSION}")
if engine.model != expected_model or engine.required_model != expected_model:
    raise SystemExit(f"Model lock mismatch: expected {expected_model}, got {engine.model}")
if engine.generation_mode != "selective-edit":
    raise SystemExit("Selective edit mode is not active")
if engine.transmit_max_request_bytes > 32 * 1024 * 1024:
    raise SystemExit(f"Unsafe transmit ceiling: {engine.transmit_max_request_bytes}")
if OpenRouterImageEngine._select_provider_size(8064, 6048) != (1536, 1024):
    raise SystemExit("Provider output size policy is not active")
if not ENVIRONMENT_SYSTEM_PROMPT:
    raise SystemExit("Environment system prompt is not configured")
if engine.maximum_total_selective_edit_ratio > 0.08:
    raise SystemExit("Selective soft-clamp budget is not active")
if engine.maximum_component_edit_ratio > 0.03:
    raise SystemExit("Local component guard is not active")
if engine.outpaint_qc_blocking is not False:
    raise SystemExit("Outpaint QC must be warning-only")
if engine.outpaint_qc_policy != "non-blocking-connected-components-warning":
    raise SystemExit("Non-blocking outpaint QC policy is not active")
if engine.missing_region_transport_policy != "opaque-chroma-marker-with-nano-banana-auto-retry":
    raise SystemExit("Missing-region reconstruction policy is not active")
if engine.outpaint_auto_retry_limit != 1:
    raise SystemExit("Automatic outpaint reconstruction retry is not active")
if health().get("generation_mode") != "background-job-polling":
    raise SystemExit("Background generation polling is not active")
print(f"Transport engine {actual} verified")
print(f"System prompt contract: {PROMPT_CONTRACT_VERSION}")
print(f"Image model locked: {engine.model}")
print("Generation mode: background job + resilient browser polling")
print("Edit mode: exact local changes with soft-clamped delta compositing")
print("Base image: pixel-preserved outside final edit area")
print("Missing regions: opaque service marker; transparent pixels are never flattened to white")
print("Outpaint reconstruction: one automatic Nano Banana correction attempt")
print("Solid white wedges: rejected as non-generated content")
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
    and payload.get('transport_policy') == 'provider-aware-temporary-copy'
    and payload.get('generation_mode') == 'background-job-polling'
    and payload.get('image_model') == expected_model
)
raise SystemExit(0 if ok else 1)
PY
    then
      echo "Marins Facade v0.8.0 standalone started on port 8070 (PID $NEW_PID)"
      echo "Transport engine: $EXPECTED_TRANSPORT_ENGINE"
      echo "Prompt contract: $EXPECTED_PROMPT_CONTRACT"
      echo "Image model: $EXPECTED_MODEL"
      echo "Missing regions: Nano Banana reconstruction required"
      cat "$HEALTH_FILE"
      exit 0
    fi
  fi
  sleep 1
done

echo "Server did not expose the required v0.8 selective-edit health signature." >&2
tail -100 "$LOG_FILE" >&2 || true
cleanup_failed_start
exit 1
