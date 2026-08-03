#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME="$ROOT/.runtime/MarinsFacade_v0.6.0"

if [ ! -f "$RUNTIME/app/main.py" ]; then
  bash "$ROOT/release/setup_v060.sh"
fi

pkill -f "uvicorn app.main:app.*8070" 2>/dev/null || true
cd "$RUNTIME"
mkdir -p data/projects
nohup python -m uvicorn app.main:app --host 0.0.0.0 --port 8070 > /tmp/marins-facade-v060.log 2>&1 &

for attempt in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8070/api/health >/tmp/marins-facade-v060-health.json 2>/dev/null; then
    echo "Marins Facade v0.6.3 started on port 8070"
    cat /tmp/marins-facade-v060-health.json
    exit 0
  fi
  sleep 1
done

echo "Server did not pass health check in 30 seconds. Log:" >&2
tail -100 /tmp/marins-facade-v060.log >&2 || true
exit 1
