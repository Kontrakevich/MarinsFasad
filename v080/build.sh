#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

# The exact v0.7 files remain preserved in ui_v07_original.
# Production uses a single-window composition styled with the same v0.7
# architectural visual system and the original Perspective Grid behaviour.
cp -f "$ROOT/ui_single_window/index.html" "$ROOT/app/web/index.html"
cp -f "$ROOT/ui_single_window/styles.css" "$ROOT/app/web/styles.css"
cp -f "$ROOT/ui_single_window/app-v080.js" "$ROOT/app/web/app-v080.js"

python - <<'PY'
from pathlib import Path
path = Path('app/web/index.html')
text = path.read_text('utf-8')
text = text.replace('styles.css?v=single-window-0801', 'styles.css?v=v07-single-window-0802')
text = text.replace('app-v080.js?v=single-window-0801', 'app-v080.js?v=v07-single-window-0802')
path.write_text(text, 'utf-8')
PY

python -m pip install -r requirements.txt
python -m compileall app
node --check app/web/app-v080.js
rm -rf .test-data
MARINS_DATA_ROOT="$ROOT/.test-data/projects" pytest -q
rm -rf .test-data
echo "Marins Facade v0.8.0 single-window v0.7-style build passed"
