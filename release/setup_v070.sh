#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME="$ROOT/.runtime/MarinsFacade_v0.6.0"

bash "$ROOT/release/setup_v069.sh"
python "$ROOT/release/patch_v070.py" "$RUNTIME"

cd "$RUNTIME"
python -m compileall app
MARINS_DATA_ROOT="$RUNTIME/.test-data/projects" pytest -q
rm -rf "$RUNTIME/.test-data"

echo "Marins Facade v0.7.0 installed in $RUNTIME"
