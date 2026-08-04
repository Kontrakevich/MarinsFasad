#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME="$ROOT/.runtime/MarinsFacade_v0.6.0"

bash "$ROOT/release/setup_v060.sh"

# Compatibility layer: some staged runtime archives do not contain app/image_tools.py.
# Create a minimal production-safe module before applying the v0.6.9 patch.
if [ ! -f "$RUNTIME/app/image_tools.py" ]; then
  cat > "$RUNTIME/app/image_tools.py" <<'PY'
from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageOps


def prepare_technical_photos(source: str | Path, output: str | Path, max_w: int = 0, max_h: int = 0) -> dict:
    source = Path(source)
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as im:
        im = ImageOps.exif_transpose(im)
        work = im.copy()
        if out.suffix.lower() in {'.jpg', '.jpeg'}:
            work.convert('RGB').save(out, quality=100, subsampling=0)
        else:
            work.save(out, format='PNG', optimize=False)
        return {
            'source': str(source),
            'output': str(out),
            'resolution': list(work.size),
        }


def make_preview(source: str | Path, output: str | Path, max_size: tuple[int, int] = (1600, 1200)) -> str:
    source = Path(source)
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as im:
        im = ImageOps.exif_transpose(im)
        preview = im.copy()
        preview.thumbnail(max_size, resample=Image.Resampling.LANCZOS)
        preview.convert('RGB').save(out, quality=90, optimize=True)
    return str(out)
PY
  echo "Created compatibility app/image_tools.py"
fi

python "$ROOT/release/patch_v069.py" "$RUNTIME"

cd "$RUNTIME"
python -m compileall app
MARINS_DATA_ROOT="$RUNTIME/.test-data/projects" pytest -q
rm -rf "$RUNTIME/.test-data"

echo "Marins Facade v0.6.9 installed in $RUNTIME"
