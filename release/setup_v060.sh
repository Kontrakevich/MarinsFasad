#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
B64="$ROOT/release/MarinsFacade_v0.6.0.zip.b64"
RUNTIME_ROOT="$ROOT/.runtime"
RUNTIME="$RUNTIME_ROOT/MarinsFacade_v0.6.0"
ZIP="$RUNTIME_ROOT/MarinsFacade_v0.6.0.zip"

if [ ! -f "$B64" ]; then
  echo "Build archive not found: $B64" >&2
  exit 1
fi

mkdir -p "$RUNTIME_ROOT"
base64 --decode "$B64" > "$ZIP"
rm -rf "$RUNTIME"
unzip -q "$ZIP" -d "$RUNTIME_ROOT"

python -m pip install --upgrade pip
python -m pip install -r "$RUNTIME/requirements.txt"

cd "$RUNTIME"
python -m compileall app
pytest -q

echo "Marins Facade v0.6.0 installed in $RUNTIME"
