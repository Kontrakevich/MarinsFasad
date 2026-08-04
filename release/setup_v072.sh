#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME="$ROOT/.runtime/MarinsFacade_v0.7.2"
LEGACY="$ROOT/.runtime/MarinsFacade_v0.6.0"
BACKUP="$ROOT/.runtime/.v072_projects_backup"

rm -rf "$BACKUP"
for source in "$RUNTIME/data/projects" "$LEGACY/data/projects"; do
  if [ -d "$source" ]; then
    mkdir -p "$BACKUP"
    cp -a "$source/." "$BACKUP/"
    break
  fi
done

# Materialize the historic staged source once, then freeze it as a separate consolidated runtime.
rm -rf "$LEGACY"
bash "$ROOT/release/setup_v071.sh"
rm -rf "$RUNTIME"
cp -a "$LEGACY" "$RUNTIME"
python "$ROOT/release/consolidate_v072.py" "$RUNTIME"

if [ -d "$BACKUP" ]; then
  mkdir -p "$RUNTIME/data/projects"
  cp -a "$BACKUP/." "$RUNTIME/data/projects/"
  rm -rf "$BACKUP"
fi

cd "$RUNTIME"
python -m compileall app
node --check app/web/app.js
rm -rf .test-data
MARINS_DATA_ROOT="$RUNTIME/.test-data/projects" pytest -q
rm -rf .test-data

echo "Marins Facade consolidated v0.7.2 installed in $RUNTIME"
