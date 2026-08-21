#!/usr/bin/env bash
set -uo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

bash "$ROOT/build.sh"
BUILD_STATUS=$?
if [ "$BUILD_STATUS" -ne 0 ]; then
  echo ""
  echo "WARNING: full build/tests did not pass. Starting the last preflight-valid runtime so the UI remains available." >&2
  echo "start.sh will repeat deterministic runtime checks before replacing any healthy server." >&2
fi

bash "$ROOT/start.sh"
START_STATUS=$?
if [ "$START_STATUS" -ne 0 ]; then
  echo ""
  echo "ERROR: runtime preflight/start failed. UI was not started." >&2
  echo "Server log: /tmp/marins-facade-v080.log" >&2
  exit "$START_STATUS"
fi

if [ "$BUILD_STATUS" -ne 0 ]; then
  echo ""
  echo "Marins Facade is running, but the full regression build needs attention." >&2
fi

exit 0
