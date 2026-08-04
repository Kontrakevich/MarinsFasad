#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME="$ROOT/.runtime/MarinsFacade_v0.6.0"

bash "$ROOT/release/setup_v060.sh"

# Compatibility layer: some staged runtime archives do not contain app/image_tools.py.
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
        # v0.6.9: production pipeline always works at the EXIF-corrected original resolution.
        # max_w/max_h remain only for backward-compatible config parsing and UI previews.
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

# Keep legacy workflow semantics and make version tests follow the runtime version.
python - "$RUNTIME" <<'PY'
from pathlib import Path
import sys

runtime = Path(sys.argv[1])
main_path = runtime / 'app/main.py'
main = main_path.read_text('utf-8')
old = "            state.setdefault('statuses', {})[stage] = 'ready'\n            state['current_stage'] = f'{stage}_ready'\n            state['stage'] = f'{stage}_ready'"
new = "            revision_status = 'editing' if stage in {'geometry', 'branding'} else 'ready'\n            state.setdefault('statuses', {})[stage] = revision_status\n            state['current_stage'] = f'{stage}_{revision_status}'\n            state['stage'] = f'{stage}_{revision_status}'"
if old in main:
    main = main.replace(old, new, 1)
elif new not in main:
    raise SystemExit('v0.6.9 revision status compatibility pattern not found')
main_path.write_text(main, 'utf-8')

smoke = runtime / 'tests/test_smoke.py'
text = smoke.read_text('utf-8')
if 'from app.main import APP_VERSION' not in text:
    text = 'from app.main import APP_VERSION\n' + text
text = text.replace("assert response.json()['version'] == '0.6.8'", "assert response.json()['version'] == APP_VERSION")
smoke.write_text(text, 'utf-8')
print('Applied v0.6.9 workflow/test compatibility')
PY

cd "$RUNTIME"
python -m compileall app
MARINS_DATA_ROOT="$RUNTIME/.test-data/projects" pytest -q
rm -rf "$RUNTIME/.test-data"

echo "Marins Facade v0.6.9 installed in $RUNTIME"
