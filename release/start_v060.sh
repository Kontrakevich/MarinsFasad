#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "Legacy launcher release/start_v060.sh redirected to Marins Facade v0.8.0"
exec bash "$ROOT/v080/start.sh"
