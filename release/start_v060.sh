#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME="$ROOT/.runtime/MarinsFacade_v0.6.0"
PID_FILE="/tmp/marins-facade-v060.pid"
LOG_FILE="/tmp/marins-facade-v060.log"
HEALTH_FILE="/tmp/marins-facade-v060-health.json"

if [ ! -f "$RUNTIME/app/main.py" ]; then
  bash "$ROOT/release/setup_v071.sh"
fi

if [ -f "$PID_FILE" ]; then
  OLD_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
    kill "$OLD_PID" 2>/dev/null || true
    for _ in $(seq 1 20); do
      kill -0 "$OLD_PID" 2>/dev/null || break
      sleep 0.25
    done
    kill -9 "$OLD_PID" 2>/dev/null || true
  fi
  rm -f "$PID_FILE"
fi

cd "$RUNTIME"
mkdir -p data/projects
: > "$LOG_FILE"

# Fully detach the web server from the terminal and launcher process.
setsid env PYTHONUNBUFFERED=1 python -m uvicorn app.main:app --host 0.0.0.0 --port 8070 \
  </dev/null >>"$LOG_FILE" 2>&1 &
SERVER_PID=$!
echo "$SERVER_PID" > "$PID_FILE"

for attempt in $(seq 1 40); do
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    echo "Server process exited during startup. Log:" >&2
    tail -200 "$LOG_FILE" >&2 || true
    exit 1
  fi
  if curl -fsS http://127.0.0.1:8070/api/health >"$HEALTH_FILE" 2>/dev/null; then
    sleep 2
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
      echo "Server passed health check but then exited. Log:" >&2
      tail -200 "$LOG_FILE" >&2 || true
      exit 1
    fi
    echo "Marins Facade started persistently on port 8070"
    echo "PID: $SERVER_PID"
    cat "$HEALTH_FILE"
    exit 0
  fi
  sleep 1
done

echo "Server did not pass health check in 40 seconds. Log:" >&2
tail -200 "$LOG_FILE" >&2 || true
exit 1
