#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
mkdir -p data/projects
if pgrep -f "uvicorn app.main:app.*8070" >/dev/null 2>&1; then
  exit 0
fi
nohup python -m uvicorn app.main:app --host 0.0.0.0 --port 8070 > /tmp/marins-fasad.log 2>&1 &
