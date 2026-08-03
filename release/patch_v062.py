from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

runtime = Path(sys.argv[1])
main_path = runtime / "app/main.py"
index_path = runtime / "app/web/index.html"
app_js_path = runtime / "app/web/app.js"
styles_path = runtime / "app/web/styles.css"
tests_path = runtime / "tests/test_ui_onboarding.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise SystemExit(f"v0.6.2 patch failed: {label}")
    return text.replace(old, new, 1)


main = main_path.read_text("utf-8")
main = re.sub(
    r'^DATA_ROOT = ROOT / "data" / "projects"$',
    'DATA_ROOT = Path(os.getenv("MARINS_DATA_ROOT", str(ROOT / "data" / "projects"))).resolve()',
    main,
    count=1,
    flags=re.MULTILINE,
)
main = re.sub(r'^APP_VERSION = "[^"]+"$', 'APP_VERSION = "0.6.2"', main, count=1, flags=re.MULTILINE)
main_path.write_text(main, "utf-8")

smoke_path = runtime / "tests/test_smoke.py"
if smoke_path.exists():
    smoke = smoke_path.read_text("utf-8")
    smoke = smoke.replace("assert response.json()['version'] == '0.6.0'", "assert response.json()['version'] == '0.6.2'")
    smoke_path.write_text(smoke, "utf-8")

index = index_path.read_text("utf-8")
index = index.replace("v0.6.0", "v0.6.2").replace("V0.6.0", "V0.6.2").replace(">0.6.0<", ">0.6.2<")
anchor = '''  </section>\n\n  <div id="workspace" class="hidden">'''
onboarding = '''  </section>\n\n  <section id="onboarding" class="onboarding-panel">\n    <div class="onboarding-panel__index">START</div>\n    <div>\n      <p class="eyebrow">ПЕРВЫЙ ЗАПУСК</p>\n      <h2>Создайте рабочий проект</h2>\n      <p class="onboarding-panel__lead">До выбора проекта система ничего не запускает. Начните с новой карточки проекта, затем загрузите исходную фотографию фасада.</p>\n      <ol class="onboarding-steps">\n        <li><strong>Создайте проект</strong><span>Нажмите «Новый проект» и задайте понятное название объекта.</span></li>\n        <li><strong>Загрузите исходник</strong><span>Фото появится в редакторе перспективы и останется неизменным.</span></li>\n        <li><strong>Идите по этапам</strong><span>Geometry → Approval → Environment → Final → Branding.</span></li>\n      </ol>\n    </div>\n  </section>\n\n  <div id="workspace" class="hidden">'''
index = replace_once(index, anchor, onboarding, "onboarding insertion")
index_path.write_text(index, "utf-8")

js = app_js_path.read_text("utf-8")
old_refresh = "async function refreshProjects(){const list=await api('/api/projects');$('project-list').innerHTML=list.map(item=>`<button class=\"project-card ${current?.id===item.id?'is-active':''}\" data-id=\"${item.id}\"><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.current_stage)}</small></button>`).join('');document.querySelectorAll('.project-card').forEach(card=>card.onclick=()=>openProject(card.dataset.id))}"
new_refresh = """const stageLabels={source:'Исходник',geometry_editing:'Редактирование геометрии',geometry_review:'Проверка геометрии',environment_ready:'Окружение готово к запуску',environment_processing:'Генерация окружения',environment_review:'Проверка окружения',final:'Final',branding_ready:'Вывеска готова к настройке',branding_processing:'Генерация вывески',branding_review:'Проверка вывески',complete:'Завершено'};
function stageLabel(value){return stageLabels[value]||String(value||'').replaceAll('_',' ')}
async function refreshProjects(){const list=await api('/api/projects');if(!list.length){$('project-list').innerHTML='<div class=\"project-list-empty\">Рабочих проектов пока нет. Нажмите «Новый проект».</div>';return}$('project-list').innerHTML=list.map(item=>`<button class=\"project-card ${current?.id===item.id?'is-active':''}\" data-id=\"${item.id}\"><span class=\"project-card__top\"><strong>${escapeHtml(item.name)}</strong><span class=\"project-card__status\">${escapeHtml(stageLabel(item.current_stage))}</span></span><small>Обновлён: ${escapeHtml(new Date(item.updated_at).toLocaleString('ru-RU'))}</small></button>`).join('');document.querySelectorAll('.project-card').forEach(card=>card.onclick=()=>openProject(card.dataset.id))}"""
js = replace_once(js, old_refresh, new_refresh, "project cards")
old_render = "function render(){if(!current)return;$('workspace').classList.remove('hidden');$('project-title').textContent=current.name;"
new_render = "function render(){if(!current)return;$('onboarding')?.classList.add('hidden');$('workspace').classList.remove('hidden');$('project-title').textContent=current.name;"
js = replace_once(js, old_render, new_render, "onboarding hide")
app_js_path.write_text(js, "utf-8")

styles = styles_path.read_text("utf-8")
addition = '''\n/* v0.6.2 onboarding and project manager cleanup */\n.onboarding-panel{display:grid;grid-template-columns:110px minmax(0,760px);gap:28px;border-top:1px solid var(--ink);border-bottom:1px solid var(--ink);padding:28px 0 34px;margin:0 0 30px}.onboarding-panel__index{font-size:11px;letter-spacing:.16em;font-weight:700}.onboarding-panel h2{font-size:34px;margin:6px 0 12px}.onboarding-panel__lead{max-width:700px;line-height:1.55}.onboarding-steps{list-style:none;padding:0;margin:24px 0 0;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;counter-reset:onboarding}.onboarding-steps li{border:1px solid var(--ink);padding:16px;display:grid;gap:8px;min-height:126px}.onboarding-steps li::before{counter-increment:onboarding;content:"0" counter(onboarding);font-size:10px;letter-spacing:.16em}.onboarding-steps strong{font-size:15px}.onboarding-steps span{font-size:12px;line-height:1.45;color:var(--ink-2)}.project-card{display:grid;gap:10px;min-height:92px}.project-card__top{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;align-items:start}.project-card__top strong{font-size:15px;line-height:1.25;overflow-wrap:anywhere}.project-card__status{border:1px solid currentColor;padding:4px 6px;font-size:9px;line-height:1.2;letter-spacing:.08em;text-transform:uppercase;max-width:190px;text-align:right}.project-card small{font-size:10px;letter-spacing:.04em;opacity:.72}.project-list-empty{grid-column:1/-1;border:1px dashed var(--line-dark);padding:22px;color:var(--ink-2)}\n@media(max-width:900px){.onboarding-panel{grid-template-columns:1fr}.onboarding-steps{grid-template-columns:1fr}.project-card__top{grid-template-columns:1fr}.project-card__status{text-align:left;width:max-content;max-width:100%}}\n'''
if "v0.6.2 onboarding" not in styles:
    styles += addition
styles_path.write_text(styles, "utf-8")

tests_path.write_text('''from pathlib import Path\n\n\ndef test_first_run_ui_has_clear_onboarding_and_readable_cards():\n    root = Path(__file__).resolve().parents[1]\n    index = (root / "app/web/index.html").read_text("utf-8")\n    app_js = (root / "app/web/app.js").read_text("utf-8")\n    assert 'id="onboarding"' in index\n    assert 'Создайте рабочий проект' in index\n    assert 'project-card__status' in app_js\n    assert 'Рабочих проектов пока нет' in app_js\n''', "utf-8")

legacy_test_names = {"Test facade", "Revision test", "No mirror fill"}
projects_root = runtime / "data/projects"
removed = []
if projects_root.exists():
    for folder in projects_root.iterdir():
        state_file = folder / "project.json"
        if not state_file.exists():
            continue
        try:
            state = json.loads(state_file.read_text("utf-8"))
        except Exception:
            continue
        if state.get("name") in legacy_test_names:
            shutil.rmtree(folder, ignore_errors=True)
            removed.append(state.get("name"))

print("Applied v0.6.2 project manager cleanup")
if removed:
    print("Removed legacy test projects:", ", ".join(sorted(removed)))
