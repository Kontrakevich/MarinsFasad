#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME="$ROOT/.runtime/MarinsFacade_v0.7.2"
LOG="/tmp/marins-facade-v072.log"
HEALTH="/tmp/marins-facade-v072-health.json"

if [ ! -f "$RUNTIME/app/main.py" ]; then
  bash "$ROOT/release/setup_v072.sh"
fi

pkill -f "uvicorn app.main:app.*8070" 2>/dev/null || true
cd "$RUNTIME"
mkdir -p data/projects
nohup python -m uvicorn app.main:app --host 0.0.0.0 --port 8070 > "$LOG" 2>&1 &
PID=$!

for attempt in $(seq 1 40); do
  if curl -fsS --max-time 3 http://127.0.0.1:8070/api/health > "$HEALTH" 2>/dev/null; then
    echo "Marins Facade consolidated v0.7.2 started on port 8070"
    cat "$HEALTH"
    echo
    echo "PID: $PID"
    echo "Log: $LOG"
    exit 0
  fi
  if ! kill -0 "$PID" 2>/dev/null; then
    break
  fi
  sleep 1
done

echo "Server failed startup validation. Diagnostics:" >&2
echo "=== PROCESS ===" >&2
ps -fp "$PID" >&2 || true
echo "=== PORT ===" >&2
ss -ltnp | grep ':8070' >&2 || true
echo "=== LOG ===" >&2
tail -160 "$LOG" >&2 || true
exit 1
