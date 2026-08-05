#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
python -m pip install -r requirements.txt
python -m compileall app
node --check app/web/app.js
rm -rf .test-data
MARINS_DATA_ROOT="$ROOT/.test-data/projects" pytest -q
rm -rf .test-data
echo "Marins Facade v0.8.0 build passed"
