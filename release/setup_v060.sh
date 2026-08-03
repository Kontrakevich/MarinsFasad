#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PARTS_DIR="$ROOT/release/v060_xz"
RUNTIME_ROOT="$ROOT/.runtime"
RUNTIME="$RUNTIME_ROOT/MarinsFacade_v0.6.0"
ARCHIVE="$RUNTIME_ROOT/MarinsFacade_v0.6.0.tar.xz"
EXPECTED_SHA256="12a3ecb31f96dcd76ec6de9fc79ba7c56b1fae2d3f8e91825c60a095a534898a"

if [ ! -d "$PARTS_DIR" ]; then
  echo "Build archive parts not found: $PARTS_DIR" >&2
  exit 1
fi

mapfile -t PARTS < <(find "$PARTS_DIR" -maxdepth 1 -type f -name '*.part' | sort)
if [ "${#PARTS[@]}" -ne 4 ]; then
  echo "Expected 4 archive parts, found ${#PARTS[@]}" >&2
  exit 1
fi

mkdir -p "$RUNTIME_ROOT"
cat "${PARTS[@]}" | base64 --decode > "$ARCHIVE"

ACTUAL_SHA256="$(sha256sum "$ARCHIVE" | awk '{print $1}')"
if [ "$ACTUAL_SHA256" != "$EXPECTED_SHA256" ]; then
  echo "Archive checksum mismatch" >&2
  echo "Expected: $EXPECTED_SHA256" >&2
  echo "Actual:   $ACTUAL_SHA256" >&2
  exit 1
fi

rm -rf "$RUNTIME"
tar -xJf "$ARCHIVE" -C "$RUNTIME_ROOT"

python -m pip install --upgrade pip
python -m pip install -r "$RUNTIME/requirements.txt"

cd "$RUNTIME"
python -m compileall app
pytest -q

echo "Marins Facade v0.6.0 installed in $RUNTIME"
