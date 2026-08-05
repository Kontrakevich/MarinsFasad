from __future__ import annotations

import re
import sys
from pathlib import Path

runtime = Path(sys.argv[1])
main_path = runtime / "app/main.py"
app_js = runtime / "app/web/app.js"
test_path = runtime / "tests/test_header_navigation_no_render_loop.py"

main = main_path.read_text("utf-8")
main = re.sub(r'^APP_VERSION = "[^"]+"$', 'APP_VERSION = "0.7.2"', main, count=1, flags=re.MULTILINE)
main_path.write_text(main, "utf-8")

js = app_js.read_text("utf-8")
old = "observer.observe(document.body,{childList:true,subtree:true,attributes:true});"
new = "observer.observe(document.body,{childList:true,subtree:true});"
if old in js:
    js = js.replace(old, new, 1)
elif new not in js:
    raise SystemExit("v0.7.0 MutationObserver pattern not found")

# Prevent redundant DOM mutations when project state has not changed.
old_render = "  function render(project){\n    const nav=ensureHeader();\n    const states=deriveStatuses(project||window.current||window.currentProject);"
new_render = "  let lastRenderSignature='';\n  function render(project){\n    const nav=ensureHeader();\n    const states=deriveStatuses(project||window.current||window.currentProject);\n    const signature=JSON.stringify(states);\n    if(signature===lastRenderSignature) return;\n    lastRenderSignature=signature;"
if old_render in js:
    js = js.replace(old_render, new_render, 1)
elif "lastRenderSignature" not in js:
    raise SystemExit("v0.7.0 render function pattern not found")

app_js.write_text(js, "utf-8")

test_path.write_text(r'''from pathlib import Path


def test_header_navigation_does_not_observe_attributes():
    js = (Path(__file__).parents[1] / 'app/web/app.js').read_text('utf-8')
    assert "observer.observe(document.body,{childList:true,subtree:true});" in js
    assert "attributes:true" not in js.split('// v0.7.0 header process navigation', 1)[1]
    assert "lastRenderSignature" in js
''', "utf-8")

print("Applied Marins Facade v0.7.2 frontend render-loop hotfix")
