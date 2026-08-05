#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="/tmp/marins-facade-v080.pid"
LOG_FILE="/tmp/marins-facade-v080.log"
HEALTH_FILE="/tmp/marins-facade-v080-health.json"

# Stop the previously recorded v0.8.0 process.
if [ -f "$PID_FILE" ]; then
  OLD_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
    kill "$OLD_PID" 2>/dev/null || true
    sleep 1
  fi
fi

# Port 8070 may still be occupied by a legacy v0.6/v0.7 runtime.
# Stop any process listening there before starting the standalone runtime.
PORT_PIDS="$(fuser 8070/tcp 2>/dev/null || true)"
if [ -n "$PORT_PIDS" ]; then
  kill $PORT_PIDS 2>/dev/null || true
  sleep 2
fi
if ss -ltnp 2>/dev/null | grep -q ':8070 '; then
  echo "Port 8070 is still occupied after graceful stop; forcing release." >&2
  PORT_PIDS="$(fuser 8070/tcp 2>/dev/null || true)"
  [ -z "$PORT_PIDS" ] || kill -9 $PORT_PIDS 2>/dev/null || true
  sleep 1
fi

cd "$ROOT"
: > "$LOG_FILE"
nohup setsid python -m uvicorn app.main:app --host 0.0.0.0 --port 8070 >"$LOG_FILE" 2>&1 </dev/null &
NEW_PID=$!
echo "$NEW_PID" > "$PID_FILE"

for _ in $(seq 1 30); do
  if ! kill -0 "$NEW_PID" 2>/dev/null; then
    echo "Marins Facade v0.8.0 process exited during startup." >&2
    tail -100 "$LOG_FILE" >&2 || true
    exit 1
  fi
  if curl -fsS http://127.0.0.1:8070/api/health >"$HEALTH_FILE" 2>/dev/null; then
    if python - "$HEALTH_FILE" <<'PY'
import json, sys
payload = json.load(open(sys.argv[1], encoding='utf-8'))
raise SystemExit(0 if payload.get('runtime') == 'standalone-v080' and payload.get('version') == '0.8.0' else 1)
PY
    then
      echo "Marins Facade v0.8.0 standalone started on port 8070 (PID $NEW_PID)"
      cat "$HEALTH_FILE"
      exit 0
    fi
  fi
  sleep 1
done

echo "Server did not expose the standalone-v080 health signature." >&2
tail -100 "$LOG_FILE" >&2 || true
exit 1
