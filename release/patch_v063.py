from __future__ import annotations

import re
import sys
from pathlib import Path

runtime = Path(sys.argv[1])
main_path = runtime / "app/main.py"
index_path = runtime / "app/web/index.html"
styles_path = runtime / "app/web/styles.css"
test_path = runtime / "tests/test_prompt_visibility.py"

main = main_path.read_text("utf-8")
main = re.sub(
    r'^APP_VERSION = "[^"]+"$',
    'APP_VERSION = "0.6.3"',
    main,
    count=1,
    flags=re.MULTILINE,
)
main_path.write_text(main, "utf-8")

smoke_path = runtime / "tests/test_smoke.py"
if smoke_path.exists():
    smoke = smoke_path.read_text("utf-8")
    smoke = re.sub(
        r"assert response\.json\(\)\['version'\] == '[^']+'",
        "assert response.json()['version'] == '0.6.3'",
        smoke,
        count=1,
    )
    smoke_path.write_text(smoke, "utf-8")

index = index_path.read_text("utf-8")
index = index.replace("v0.6.2", "v0.6.3")
index = index.replace("V0.6.2", "V0.6.3")
index = index.replace(">0.6.2<", ">0.6.3<")
index_path.write_text(index, "utf-8")

styles = styles_path.read_text("utf-8")
marker = "/* v0.6.3 readable compiled prompts */"
addition = r'''

/* v0.6.3 readable compiled prompts */
.prompt-panel-v060{
  background:var(--ink) !important;
  color:var(--paper) !important;
}
.prompt-panel-v060 .panel-kicker{
  color:#c9d5de !important;
}
.prompt-panel-v060 textarea,
#environment-prompt,
#branding-prompt{
  display:block;
  width:100%;
  min-height:300px;
  padding:14px !important;
  border:1px solid rgba(255,255,255,.34) !important;
  background:var(--ink) !important;
  background-color:var(--ink) !important;
  color:#f7f4ec !important;
  -webkit-text-fill-color:#f7f4ec !important;
  caret-color:#f7f4ec !important;
  opacity:1 !important;
  font-family:ui-monospace,SFMono-Regular,Consolas,monospace;
  font-size:12px;
  line-height:1.55;
  white-space:pre-wrap;
  overflow-wrap:anywhere;
  word-break:break-word;
  forced-color-adjust:none;
}
.prompt-panel-v060 textarea::selection,
#environment-prompt::selection,
#branding-prompt::selection{
  background:#4a7da5;
  color:#ffffff;
  -webkit-text-fill-color:#ffffff;
}
.prompt-panel-v060 textarea:focus,
#environment-prompt:focus,
#branding-prompt:focus{
  outline:2px solid rgba(255,255,255,.55) !important;
  outline-offset:2px;
  box-shadow:none !important;
}
'''
if marker not in styles:
    styles += addition
styles_path.write_text(styles, "utf-8")

test_path.write_text(
    '''from pathlib import Path\n\n\ndef test_compiled_prompt_is_readable_without_selection():\n    root = Path(__file__).resolve().parents[1]\n    styles = (root / "app/web/styles.css").read_text("utf-8")\n    assert "v0.6.3 readable compiled prompts" in styles\n    assert "#environment-prompt" in styles\n    assert "#branding-prompt" in styles\n    assert "-webkit-text-fill-color:#f7f4ec !important" in styles\n    assert "background-color:var(--ink) !important" in styles\n''',
    "utf-8",
)

print("Applied v0.6.3 compiled prompt visibility fix")
