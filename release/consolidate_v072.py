from __future__ import annotations

import json
import re
import sys
from pathlib import Path

runtime = Path(sys.argv[1]).resolve()
main_path = runtime / "app/main.py"
js_path = runtime / "app/web/app.js"
index_path = runtime / "app/web/index.html"
test_path = runtime / "tests/test_v072_consolidated_frontend.py"

for required in (main_path, js_path, index_path):
    if not required.exists():
        raise SystemExit(f"Missing consolidated runtime file: {required}")

main = main_path.read_text("utf-8")
main = re.sub(r'^APP_VERSION = "[^"]+"$', 'APP_VERSION = "0.7.2"', main, count=1, flags=re.MULTILINE)
main_path.write_text(main, "utf-8")

js = js_path.read_text("utf-8")

# v0.7.0 observed every attribute mutation while render() itself changed attributes.
# That creates a self-triggering render loop, especially visible in mobile browsers.
js = js.replace(
    "observer.observe(document.body,{childList:true,subtree:true,attributes:true});",
    "observer.observe(document.body,{childList:true,subtree:true});",
)

# Replace the unbounded direct observer callback with one animation-frame render.
js = js.replace(
    "const observer=new MutationObserver(()=>render(window.current||window.currentProject));",
    "let mfRenderQueued=false;\n    const observer=new MutationObserver(()=>{\n      if(mfRenderQueued) return;\n      mfRenderQueued=true;\n      requestAnimationFrame(()=>{mfRenderQueued=false;render(window.current||window.currentProject)});\n    });",
)

# Polling is unnecessary after fetch interception and DOM observation; it caused extra mobile work.
js = js.replace(
    "setInterval(()=>render(window.current||window.currentProject),1200);",
    "// v0.7.2: event-driven updates only; no permanent polling loop.",
)

# The v0.6.9 global click handler opened raw image URLs before the richer v0.7.1 viewer.
# Disable only that legacy listener block while retaining its image metadata decoration.
legacy_start = "// v0.6.9 original-size image viewer\n(function(){\n  document.addEventListener('click', function(event){"
if legacy_start in js:
    js = js.replace(
        "  document.addEventListener('click', function(event){\n    const img=event.target.closest('img');\n    if(!img || img.dataset.noOriginal==='1') return;\n    event.preventDefault();\n    window.open(img.currentSrc||img.src, '_blank', 'noopener,noreferrer');\n  });",
        "  // v0.7.2: legacy raw-image click handler removed; the 1:1 quality viewer owns image clicks.",
        1,
    )

# Add a defensive boot watchdog. It does not hide errors; it exposes them in the page.
watchdog_marker = "// v0.7.2 frontend boot watchdog"
if watchdog_marker not in js:
    js += r'''

// v0.7.2 frontend boot watchdog
(function(){
  function showBootFailure(message){
    let panel=document.getElementById('mf-boot-failure');
    if(!panel){
      panel=document.createElement('div');
      panel.id='mf-boot-failure';
      panel.style.cssText='position:fixed;left:16px;right:16px;bottom:16px;z-index:99999;padding:14px 16px;background:#fff3f1;border:1px solid #9b2c21;color:#5d1711;font:14px/1.45 system-ui,sans-serif;white-space:pre-wrap;box-shadow:0 10px 30px rgba(0,0,0,.2)';
      document.body.appendChild(panel);
    }
    panel.textContent='Ошибка запуска интерфейса\n'+message+'\n\nОбновите страницу. Если ошибка повторится, сохраните этот текст.';
  }
  window.addEventListener('error',event=>showBootFailure(event.message||'Неизвестная JavaScript-ошибка'));
  window.addEventListener('unhandledrejection',event=>showBootFailure(String(event.reason||'Необработанная ошибка запроса')));
  window.setTimeout(async()=>{
    try{
      const response=await fetch('/api/health',{cache:'no-store'});
      if(!response.ok) throw new Error('Health API: HTTP '+response.status);
      const data=await response.json();
      document.documentElement.dataset.marinsHealth='ok';
      document.documentElement.dataset.marinsVersion=String(data.version||'0.7.2');
    }catch(error){
      showBootFailure(String(error));
    }
  },1500);
})();
'''

js_path.write_text(js, "utf-8")

# Cache busting ensures Safari does not keep the broken app.js from the previous runtime.
index = index_path.read_text("utf-8")
index = re.sub(r'(app\.js)(?:\?v=[^"\']+)?', r'\1?v=0.7.2', index)
index = re.sub(r'(styles\.css)(?:\?v=[^"\']+)?', r'\1?v=0.7.2', index)
index_path.write_text(index, "utf-8")

manifest = {
    "name": "Marins Facade Control Center",
    "version": "0.7.2",
    "runtime": "consolidated",
    "port": 8070,
    "quality_policy": "original_full_resolution",
    "outpaint_policy": "transparent_mask_with_post_generation_validation",
    "comment_policy": "ai_adapted_and_mandatory_in_final_prompt",
    "frontend_update_policy": "event_driven_no_recursive_attribute_observer",
}
(runtime / "RUNTIME_VERSION.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8")

test_path.write_text(r'''from pathlib import Path


def test_consolidated_frontend_has_no_recursive_attribute_observer():
    root = Path(__file__).parents[1]
    js = (root / 'app/web/app.js').read_text('utf-8')
    assert 'subtree:true,attributes:true' not in js
    assert 'event-driven updates only' in js
    assert 'frontend boot watchdog' in js


def test_consolidated_version_and_cache_busting():
    root = Path(__file__).parents[1]
    main = (root / 'app/main.py').read_text('utf-8')
    index = (root / 'app/web/index.html').read_text('utf-8')
    assert 'APP_VERSION = "0.7.2"' in main
    assert 'app.js?v=0.7.2' in index
''', "utf-8")

print("Consolidated Marins Facade runtime v0.7.2")
