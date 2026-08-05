#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

# Source-of-truth UI: compact single-window composition based on v0.7.
cp -f "$ROOT/ui_single_window/index.html" "$ROOT/app/web/index.html"
cp -f "$ROOT/ui_single_window/styles.css" "$ROOT/app/web/styles.css"
cp -f "$ROOT/ui_single_window/app-v080.js" "$ROOT/app/web/app-v080.js"
cp -f "$ROOT/ui_single_window/marins-logo.svg" "$ROOT/app/web/marins-logo.svg"

python -m pip install -r requirements.txt
python -m compileall app
node --check app/web/app-v080.js
rm -rf .test-data
MARINS_DATA_ROOT="$ROOT/.test-data/projects" pytest -q
rm -rf .test-data
echo "Marins Facade v0.8.0 compact unified-grid UI build passed"
