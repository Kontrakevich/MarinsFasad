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
EXPECTED_PROMPT_ADAPTER="1.0.1"

cd "$ROOT"

# Assemble the current frontend, but never use brittle text/grep regression checks
# as a reason to keep the web server offline. Full UI regression checks belong
# to build.sh; start.sh validates only executable runtime invariants.
cp -f "$ROOT/ui_single_window/index.html" "$ROOT/app/web/index.html"
sed -i 's/prompt-workspace-3430/system1-grid-prompt-3480/g; s/system1-command-console-3440/system1-grid-prompt-3480/g; s/system1-console-all-3450/system1-grid-prompt-3480/g; s/system1-grid-console-3460/system1-grid-prompt-3480/g; s/system1-grid-prompt-3470/system1-grid-prompt-3480/g; s/resilient-fullframe-0806/quality-outpaint-3400/g; s/selective-nanobanana-0806/quality-outpaint-3400/g; s/geometry-only-outpaint-0806/quality-outpaint-3400/g; s/stable-nanobanana-3000/quality-outpaint-3400/g; s/working-master-3001/quality-outpaint-3400/g; s/hybrid-edit-3100/quality-outpaint-3400/g; s/hybrid-two-pass-3200/quality-outpaint-3400/g; s/skill-contracts-3300/quality-outpaint-3400/g' "$ROOT/app/web/index.html"
sed -i 's/V0.8.0/V0.8.1 QUALITY/g; s/ORIGINAL MASTER/WORKING MASTER/g; s/NO DOWNSCALE/GENERATION SCALE/g; s/Файл сохраняется без уменьшения и перекодирования. Preview существует отдельно./Оригинал сохраняется в архиве проекта. Для сетки и генерации используется облегчённый рабочий master./g' "$ROOT/app/web/index.html"
cp -f "$ROOT/ui_single_window/styles.css" "$ROOT/app/web/styles.css"
cat "$ROOT/ui_single_window/async-generation-bridge.js" \
    "$ROOT/ui_single_window/app-v080.js" \
    "$ROOT/ui_single_window/grid-ux-patch.js" \
    "$ROOT/ui_single_window/hybrid-mode-patch.js" \
    "$ROOT/ui_single_window/system1-intelligence-patch.js" \
    "$ROOT/ui_single_window/workspace-controls-patch.js" \
    "$ROOT/ui_single_window/command-console-patch.js" \
    "$ROOT/ui_single_window/lower-console-patch.js" \
    "$ROOT/ui_single_window/prompt-workspace-console-patch.js" \
    "$ROOT/ui_single_window/minimum-font-patch.js" \
    > "$ROOT/app/web/app-v080.js"
sed -i 's/Сгенерируйте окружение по всему canvas/Выполните выбранный skill генерации/g' "$ROOT/app/web/app-v080.js"
sed -i 's/Дорисуйте отсутствующее окружение и выполните точные изменения из промпта/Выполните выбранный skill генерации/g' "$ROOT/app/web/app-v080.js"
sed -i 's/Production policy: original resolution\./Рабочий master оптимизирован до размера генерации; исходный файл сохранён в архиве проекта./g' "$ROOT/app/web/app-v080.js"
sed -i 's/V0.8.0 HYBRID/V0.8.1 QUALITY/g; s/V0.8.1 HYBRID/V0.8.1 QUALITY/g; s/V0.8.1 SKILLS/V0.8.1 QUALITY/g' "$ROOT/app/web/app-v080.js"
cp -f "$ROOT/ui_single_window/marins-logo.svg" "$ROOT/app/web/marins-logo.svg"

# Runtime-only deterministic preflight.
python -B - "$EXPECTED_TRANSPORT_ENGINE" "$EXPECTED_PROMPT_CONTRACT" "$EXPECTED_MODEL" "$EXPECTED_APP_VERSION" "$EXPECTED_PROMPT_ADAPTER" <<'PY'
import sys
from app.ai_engine import OpenRouterImageEngine
from app.config import APP_VERSION
from app.intelligence.orchestrator import System1Intelligence
from app.project_engine import ProjectEngine
from app.system_prompts import PROMPT_CONTRACT_VERSION

expected_engine, expected_prompt, expected_model, expected_version, expected_adapter = sys.argv[1:6]
engine = OpenRouterImageEngine()

checks = {
    "transport": OpenRouterImageEngine.transport_engine_version == expected_engine,
    "app_version": APP_VERSION == expected_version,
    "prompt_contract": PROMPT_CONTRACT_VERSION == expected_prompt,
    "model_lock": engine.model == expected_model and engine.required_model == expected_model,
    "prompt_adapter": engine.nano_banana_prompt_adapter_version == expected_adapter,
    "system1": System1Intelligence.version == "1.0.0" and hasattr(ProjectEngine, "_system1_original_read"),
}
failed = [name for name, ok in checks.items() if not ok]
if failed:
    raise SystemExit("Runtime preflight failed: " + ", ".join(failed))

print("Runtime preflight passed")
print(f"App version: {APP_VERSION}")
print(f"Transport engine: {OpenRouterImageEngine.transport_engine_version}")
print(f"Prompt contract: {PROMPT_CONTRACT_VERSION}")
print(f"Image model: {engine.model}")
print(f"Nano Banana Prompt Adapter: {engine.nano_banana_prompt_adapter_version}")
print("System №1 Intelligence: active")
PY

# Replace the old process only after runtime preflight succeeds.
OLD_PID=""
if [ -f "$PID_FILE" ]; then
  OLD_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
fi
if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
  kill "$OLD_PID" 2>/dev/null || true
  for _ in $(seq 1 20); do
    kill -0 "$OLD_PID" 2>/dev/null || break
    sleep 0.1
  done
fi

PORT_PIDS="$(fuser 8070/tcp 2>/dev/null || true)"
if [ -n "$PORT_PIDS" ]; then
  kill $PORT_PIDS 2>/dev/null || true
  sleep 0.2
fi

: > "$LOG_FILE"
PYTHONDONTWRITEBYTECODE=1 nohup setsid python -B -m uvicorn app.main:app --host 0.0.0.0 --port 8070 >"$LOG_FILE" 2>&1 </dev/null &
NEW_PID=$!
echo "$NEW_PID" > "$PID_FILE"

cleanup_failed_start() {
  kill "$NEW_PID" 2>/dev/null || true
  sleep 0.2
  kill -9 "$NEW_PID" 2>/dev/null || true
  rm -f "$PID_FILE"
}

for _ in $(seq 1 60); do
  if ! kill -0 "$NEW_PID" 2>/dev/null; then
    echo "Marins Facade process exited during startup." >&2
    tail -120 "$LOG_FILE" >&2 || true
    rm -f "$PID_FILE"
    exit 1
  fi

  if curl -fsS http://127.0.0.1:8070/api/health >"$HEALTH_FILE" 2>/dev/null; then
    if python -B - "$HEALTH_FILE" "$EXPECTED_MODEL" "$EXPECTED_APP_VERSION" "$EXPECTED_PROMPT_ADAPTER" <<'PY'
import json, sys
payload = json.load(open(sys.argv[1], encoding="utf-8"))
expected_model, expected_version, expected_adapter = sys.argv[2:5]
ok = (
    payload.get("runtime") == "standalone-v080"
    and payload.get("version") == expected_version
    and payload.get("image_model") == expected_model
    and payload.get("nano_banana_prompt_adapter") == expected_adapter
)
raise SystemExit(0 if ok else 1)
PY
    then
      echo "Marins Facade v0.8.1 started on port 8070 (PID $NEW_PID)"
      echo "Frontend cache key: system1-grid-prompt-3480"
      echo "Prompt editor loop guard: active"
      cat "$HEALTH_FILE"
      exit 0
    fi
  fi
  sleep 0.2
done

echo "Server did not expose the required health endpoint." >&2
tail -120 "$LOG_FILE" >&2 || true
cleanup_failed_start
exit 1
