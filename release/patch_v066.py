from __future__ import annotations

import re
import sys
from pathlib import Path

runtime = Path(sys.argv[1])
main_path = runtime / "app/main.py"
index_path = runtime / "app/web/index.html"
styles_path = runtime / "app/web/styles.css"
test_path = runtime / "tests/test_ui_consistency.py"

main = main_path.read_text("utf-8")
main = re.sub(
    r'^APP_VERSION = "[^"]+"$',
    'APP_VERSION = "0.6.6"',
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
        "assert response.json()['version'] == '0.6.6'",
        smoke,
        count=1,
    )
    smoke_path.write_text(smoke, "utf-8")

index = index_path.read_text("utf-8")
for old in ("v0.6.5", "V0.6.5", ">0.6.5<"):
    index = index.replace(old, old.replace("0.6.5", "0.6.6"))

ui_marker = "v0.6.6 unified fields and labels"
if ui_marker not in index:
    ui_script = r'''
<script>
// v0.6.6 unified fields and labels
(() => {
  const reviewLabels = {
    'geometry-comment': 'КОММЕНТАРИЙ К РЕЗУЛЬТАТУ ГЕОМЕТРИИ',
    'environment-comment': 'КОММЕНТАРИЙ К РЕЗУЛЬТАТУ ОКРУЖЕНИЯ',
    'branding-comment': 'КОММЕНТАРИЙ К РЕЗУЛЬТАТУ ВЫВЕСКИ'
  };

  function applyUnifiedFormStyles() {
    Object.entries(reviewLabels).forEach(([id, labelText]) => {
      const textarea = document.getElementById(id);
      if (!textarea) return;
      textarea.classList.add('fixed-comment-field');
      textarea.setAttribute('rows', '4');
      textarea.setAttribute('aria-label', labelText);
      const reviewBox = textarea.closest('.review-box');
      if (reviewBox && !reviewBox.querySelector('.review-box__label')) {
        const label = document.createElement('span');
        label.className = 'review-box__label';
        label.textContent = labelText;
        reviewBox.insertBefore(label, textarea);
      }
    });

    ['environment-extra', 'branding-extra', 'branding-material'].forEach(id => {
      const textarea = document.getElementById(id);
      if (textarea) textarea.classList.add('fixed-operator-field');
    });

    ['environment-prompt', 'branding-prompt'].forEach(id => {
      const textarea = document.getElementById(id);
      if (textarea) textarea.classList.add('fixed-prompt-field');
    });

    ['geometry-skill'].forEach(id => {
      const textarea = document.getElementById(id);
      if (textarea) textarea.classList.add('fixed-skill-field');
    });

    document.querySelectorAll('.field-group').forEach(element => {
      element.classList.add('unified-field-group');
    });
    document.querySelectorAll('.panel-kicker, .field-label').forEach(element => {
      element.classList.add('unified-ui-label');
    });
  }

  applyUnifiedFormStyles();
  document.addEventListener('DOMContentLoaded', applyUnifiedFormStyles, { once: true });
  const observer = new MutationObserver(applyUnifiedFormStyles);
  observer.observe(document.documentElement, { childList: true, subtree: true });
})();
</script>
'''
    index = index.replace("</body>", ui_script + "\n</body>")
index_path.write_text(index, "utf-8")

styles = styles_path.read_text("utf-8")
css_marker = "/* v0.6.6 unified spacing, labels and fixed comment fields */"
if css_marker not in styles:
    styles += r'''

/* v0.6.6 unified spacing, labels and fixed comment fields */
:root{
  --ui-space-1:8px;
  --ui-space-2:12px;
  --ui-space-3:16px;
  --ui-space-4:20px;
  --ui-space-5:28px;
  --ui-control-bg:#f8f7f3;
}
.section-content > * + *{margin-top:var(--ui-space-4)}
.side-by-side{gap:var(--ui-space-4)}
.field-stack{gap:var(--ui-space-3)}
.top-gap{margin-top:var(--ui-space-4)!important}
.editor-actions{gap:var(--ui-space-2);margin-top:var(--ui-space-3)}

.panel-kicker,
.field-label,
.review-box__label,
.task-status-header__kicker,
.task-status-stage__kicker,
.task-status-stage__eyebrow,
.unified-ui-label{
  display:block;
  margin:0 0 var(--ui-space-2);
  color:var(--ink-2);
  font-size:10px;
  font-weight:600;
  line-height:1.25;
  letter-spacing:.18em;
  text-transform:uppercase;
}

.field-group,
.unified-field-group{
  display:grid;
  gap:var(--ui-space-2);
  min-width:0;
  margin:0;
}
.field-group .field-label,
.unified-field-group .field-label{margin:0}

.review-box{
  display:grid;
  gap:var(--ui-space-2);
  margin-top:var(--ui-space-4);
  padding:var(--ui-space-3);
  border:1px solid var(--ink);
  background:transparent;
}
.review-box .editor-actions{margin-top:0}
.review-box__label{margin-bottom:0}

.fixed-comment-field,
#geometry-comment,
#environment-comment,
#branding-comment{
  display:block;
  width:100%;
  height:112px!important;
  min-height:112px!important;
  max-height:112px!important;
  margin:0!important;
  padding:14px 16px!important;
  resize:none!important;
  overflow:auto!important;
  border:1px solid var(--line-dark)!important;
  background:var(--ui-control-bg)!important;
  color:var(--ink)!important;
  line-height:1.5;
  box-shadow:none;
}

.fixed-operator-field,
#environment-extra,
#branding-extra,
#branding-material{
  display:block;
  width:100%;
  height:132px!important;
  min-height:132px!important;
  max-height:132px!important;
  padding:14px 16px!important;
  resize:none!important;
  overflow:auto!important;
  border:1px solid var(--line-dark)!important;
  background:var(--ui-control-bg)!important;
  color:var(--ink)!important;
  line-height:1.5;
}

.fixed-prompt-field,
#environment-prompt,
#branding-prompt{
  height:300px!important;
  min-height:300px!important;
  max-height:300px!important;
  resize:none!important;
  overflow:auto!important;
}
.fixed-skill-field,
#geometry-skill{
  height:300px!important;
  min-height:300px!important;
  max-height:300px!important;
  padding:14px 16px!important;
  resize:none!important;
  overflow:auto!important;
  border:1px solid var(--line-dark)!important;
  background:var(--ui-control-bg)!important;
}

.fixed-comment-field::placeholder,
.fixed-operator-field::placeholder,
#geometry-comment::placeholder,
#environment-comment::placeholder,
#branding-comment::placeholder,
#environment-extra::placeholder,
#branding-extra::placeholder,
#branding-material::placeholder{
  color:#71808d;
  opacity:1;
}

.fixed-comment-field:focus,
.fixed-operator-field:focus,
.fixed-skill-field:focus,
#geometry-comment:focus,
#environment-comment:focus,
#branding-comment:focus,
#environment-extra:focus,
#branding-extra:focus,
#branding-material:focus,
#geometry-skill:focus{
  outline:none!important;
  border-color:var(--ink)!important;
  box-shadow:0 0 0 2px rgba(19,47,73,.12)!important;
}

.prompt-panel-v060,
.skill-panel,
.runtime-card,
.task-status-stage{
  padding:var(--ui-space-3);
}
.prompt-panel-v060 .panel-kicker,
.skill-panel .panel-kicker{margin-bottom:var(--ui-space-2)}

@media(max-width:760px){
  .review-box{padding:var(--ui-space-2)}
  .fixed-comment-field,
  #geometry-comment,
  #environment-comment,
  #branding-comment{height:128px!important;min-height:128px!important;max-height:128px!important}
}
'''
styles_path.write_text(styles, "utf-8")

test_path.write_text(
    '''from pathlib import Path\n\n\ndef test_unified_comment_fields_and_labels():\n    root = Path(__file__).resolve().parents[1]\n    index = (root / "app/web/index.html").read_text("utf-8")\n    styles = (root / "app/web/styles.css").read_text("utf-8")\n    assert "v0.6.6 unified fields and labels" in index\n    assert "geometry-comment" in index\n    assert "environment-comment" in index\n    assert "branding-comment" in index\n    assert "review-box__label" in index\n    assert "v0.6.6 unified spacing, labels and fixed comment fields" in styles\n    assert "resize:none!important" in styles\n    assert "height:112px!important" in styles\n    assert "--ui-space-4:20px" in styles\n''',
    "utf-8",
)

print("Applied v0.6.6 unified form spacing and fixed comment fields")
