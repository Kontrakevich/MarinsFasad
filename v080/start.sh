#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="/tmp/marins-facade-v080.pid"
LOG_FILE="/tmp/marins-facade-v080.log"
if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then kill "$(cat "$PID_FILE")" || true; sleep 1; fi
cd "$ROOT"
nohup setsid python -m uvicorn app.main:app --host 0.0.0.0 --port 8070 >"$LOG_FILE" 2>&1 </dev/null &
echo $! > "$PID_FILE"
for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8070/api/health >/tmp/marins-facade-v080-health.json 2>/dev/null; then
    echo "Marins Facade v0.8.0 started on port 8070"
    cat /tmp/marins-facade-v080-health.json
    exit 0
  fi
  sleep 1
done
tail -100 "$LOG_FILE" >&2 || true
exit 1
