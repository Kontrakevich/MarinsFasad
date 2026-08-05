#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="/tmp/marins-facade-v080.pid"
LOG_FILE="/tmp/marins-facade-v080.log"
HEALTH_FILE="/tmp/marins-facade-v080-health.json"
EXPECTED_TRANSPORT_ENGINE="2.1.0"

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
python - "$EXPECTED_TRANSPORT_ENGINE" <<'PY'
import sys
from app.ai_engine import OpenRouterImageEngine
expected = sys.argv[1]
actual = OpenRouterImageEngine.transport_engine_version
if actual != expected:
    raise SystemExit(f"Transport engine mismatch: expected {expected}, got {actual}")
print(f"Transport engine {actual} verified")
PY

: > "$LOG_FILE"
nohup setsid python -m uvicorn app.main:app --host 0.0.0.0 --port 8070 >"$LOG_FILE" 2>&1 </dev/null &
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
    if python - "$HEALTH_FILE" <<'PY'
import json, sys
payload = json.load(open(sys.argv[1], encoding='utf-8'))
ok = (
    payload.get('runtime') == 'standalone-v080'
    and payload.get('version') == '0.8.0'
    and payload.get('transport_policy') == 'provider-aware-temporary-copy'
)
raise SystemExit(0 if ok else 1)
PY
    then
      echo "Marins Facade v0.8.0 standalone started on port 8070 (PID $NEW_PID)"
      echo "Transport engine: $EXPECTED_TRANSPORT_ENGINE"
      cat "$HEALTH_FILE"
      exit 0
    fi
  fi
  sleep 1
done

echo "Server did not expose the required v0.8 transport health signature." >&2
tail -100 "$LOG_FILE" >&2 || true
cleanup_failed_start
exit 1
