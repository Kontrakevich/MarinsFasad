#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

# Preserve the exact v0.7 visual shell. Only the JavaScript API layer is replaced.
cp -f "$ROOT/ui_v07_original/index.html" "$ROOT/app/web/index.html"
cp -f "$ROOT/ui_v07_original/styles.css" "$ROOT/app/web/styles.css"
python - <<'PY'
from pathlib import Path
path = Path('app/web/index.html')
text = path.read_text('utf-8')
text = text.replace('/static/styles.css?v=0.6.1', '/static/styles.css?v=v07-grid-080')
text = text.replace('<script src="/static/app.js?v=0.6.1"></script>', '<script src="/static/app-v080.js?v=v07-grid-080"></script>')
text = text.replace('Control Center v0.6.6', 'Control Center v0.8.0')
text = text.replace('<span>V0.6.6</span>', '<span>V0.8.0</span>')
text = text.replace('<strong>0.6.6</strong>', '<strong>0.8.0</strong>')
path.write_text(text, 'utf-8')
PY

python -m pip install -r requirements.txt
python -m compileall app
node --check app/web/app-v080.js
rm -rf .test-data
MARINS_DATA_ROOT="$ROOT/.test-data/projects" pytest -q
rm -rf .test-data
echo "Marins Facade v0.8.0 build passed with exact v0.7 interface and Perspective Grid"
