from __future__ import annotations

import re
import sys
from pathlib import Path

runtime = Path(sys.argv[1])
main_path = runtime / "app/main.py"
app_js = runtime / "app/web/app.js"
styles_path = runtime / "app/web/styles.css"
test_path = runtime / "tests/test_header_process_navigation.py"

main = main_path.read_text("utf-8")
main = re.sub(r'^APP_VERSION = "[^"]+"$', 'APP_VERSION = "0.7.0"', main, count=1, flags=re.MULTILINE)
main_path.write_text(main, "utf-8")

js = app_js.read_text("utf-8")
marker = "// v0.7.0 header process navigation"
if marker not in js:
    js += r'''

// v0.7.0 header process navigation
(function(){
  const STEPS=[
    {key:'source',label:'ИСХОДНИК'},
    {key:'geometry',label:'ГЕОМЕТРИЯ'},
    {key:'environment',label:'ОКРУЖЕНИЕ'},
    {key:'final',label:'FINAL'},
    {key:'branding',label:'ВЫВЕСКА'}
  ];

  function normalizeStatus(value){
    const raw=String(value||'').toLowerCase();
    if(['approved','locked','done','complete','completed'].some(v=>raw.includes(v))) return raw.includes('lock')?'locked':'approved';
    if(['processing','running','queued','generating'].some(v=>raw.includes(v))) return 'processing';
    if(['ready','active','review','revision','pending'].some(v=>raw.includes(v))) return 'ready';
    if(['failed','error'].some(v=>raw.includes(v))) return 'error';
    return raw||'locked';
  }

  function deriveStatuses(project){
    if(!project) return {source:'locked',geometry:'locked',environment:'locked',final:'locked',branding:'locked'};
    const statuses=project.statuses||{};
    const files=project.active_files||{};
    const source=files.source||files.original||project.source_file;
    const geometry=statuses.geometry||project.geometry_status;
    const environment=statuses.environment||project.environment_status;
    const branding=statuses.branding||project.branding_status;
    const finalLocked=project.final_locked||project.locked_final||files.final;
    return {
      source: source?'approved':'ready',
      geometry: normalizeStatus(geometry||(source?'ready':'locked')),
      environment: normalizeStatus(environment||(geometry&&String(geometry).includes('approved')?'ready':'locked')),
      final: finalLocked?'locked':(environment&&String(environment).includes('approved')?'ready':'locked'),
      branding: normalizeStatus(branding||(finalLocked?'ready':'locked'))
    };
  }

  function ensureHeader(){
    let nav=document.getElementById('mf-process-nav');
    if(nav) return nav;
    nav=document.createElement('nav');
    nav.id='mf-process-nav';
    nav.className='mf-process-nav';
    nav.setAttribute('aria-label','Процесс проекта');
    nav.innerHTML=STEPS.map((step,index)=>`<button type="button" class="mf-process-step" data-stage="${step.key}" aria-current="false"><span class="mf-process-label">${step.label}</span><strong class="mf-process-status">locked</strong></button>`).join('');
    const anchor=document.querySelector('header, .topbar, .app-header, body > main, body > .app')||document.body.firstElementChild;
    if(anchor&&anchor.tagName==='HEADER') anchor.insertAdjacentElement('afterend',nav);
    else if(anchor&&anchor.parentNode) anchor.parentNode.insertBefore(nav,anchor);
    else document.body.prepend(nav);
    nav.addEventListener('click',event=>{
      const button=event.target.closest('.mf-process-step');
      if(!button||button.classList.contains('is-locked')) return;
      const stage=button.dataset.stage;
      const target=document.querySelector(`[data-stage="${stage}"], #${stage}, .stage-${stage}, [id*="${stage}"]`);
      if(target) target.scrollIntoView({behavior:'smooth',block:'start'});
    });
    return nav;
  }

  function render(project){
    const nav=ensureHeader();
    const states=deriveStatuses(project||window.current||window.currentProject);
    let activeFound=false;
    STEPS.forEach(step=>{
      const el=nav.querySelector(`[data-stage="${step.key}"]`);
      if(!el) return;
      const status=states[step.key]||'locked';
      el.className='mf-process-step is-'+status;
      el.querySelector('.mf-process-status').textContent=status;
      const active=!activeFound&&['processing','ready','error'].includes(status);
      if(active) activeFound=true;
      el.classList.toggle('is-active',active);
      el.classList.toggle('is-locked',status==='locked'&&step.key!=='final');
      el.setAttribute('aria-current',active?'step':'false');
    });
  }

  function hook(){
    render(window.current||window.currentProject);
    const observer=new MutationObserver(()=>render(window.current||window.currentProject));
    observer.observe(document.body,{childList:true,subtree:true,attributes:true});
    const originalFetch=window.fetch;
    window.fetch=async function(...args){
      const response=await originalFetch.apply(this,args);
      try{
        const url=String(args[0]||'');
        if(url.includes('/api/projects/')&&response.headers.get('content-type')?.includes('application/json')){
          const clone=response.clone();
          clone.json().then(data=>{if(data&&typeof data==='object'){window.currentProject=data;render(data)}}).catch(()=>{});
        }
      }catch(_){ }
      return response;
    };
    setInterval(()=>render(window.current||window.currentProject),1200);
  }

  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',hook,{once:true}); else hook();
})();
'''
    app_js.write_text(js, "utf-8")

css = styles_path.read_text("utf-8")
if ".mf-process-nav" not in css:
    css += r'''

/* v0.7.0 — header process navigation */
.mf-process-nav{position:sticky;top:0;z-index:60;display:grid;grid-template-columns:repeat(5,minmax(0,1fr));margin:0 20px 18px;border:1px solid #183653;background:#f5f4f0;box-shadow:0 8px 24px rgba(0,32,52,.08)}
.mf-process-step{min-height:58px;padding:10px 12px;border:0;border-right:1px solid #183653;background:#f5f4f0;color:#003050;text-align:left;cursor:pointer;transition:background .18s ease,color .18s ease,opacity .18s ease}
.mf-process-step:last-child{border-right:0}
.mf-process-label{display:block;margin-bottom:5px;font-size:10px;line-height:1;letter-spacing:.08em;text-transform:uppercase}
.mf-process-status{display:block;font-size:12px;line-height:1.2;font-weight:700}
.mf-process-step.is-approved,.mf-process-step.is-locked.is-active{background:#173654;color:#fff}
.mf-process-step.is-processing{background:#c9e0dc;color:#003050}
.mf-process-step.is-ready{background:#e7efed;color:#003050}
.mf-process-step.is-error{background:#f3d8d4;color:#6c1d16}
.mf-process-step.is-locked{cursor:default;opacity:.72}
.mf-process-step.is-active{box-shadow:inset 0 -4px 0 #008a90}
.mf-process-step:focus-visible{outline:3px solid #008a90;outline-offset:-3px}
@media(max-width:900px){.mf-process-nav{grid-template-columns:repeat(5,minmax(150px,1fr));overflow-x:auto;margin-inline:12px}.mf-process-step{min-width:150px}}
'''
    styles_path.write_text(css, "utf-8")

test_path.write_text(r'''from pathlib import Path


def test_header_process_navigation_assets_exist():
    root = Path(__file__).parents[1]
    js = (root / 'app/web/app.js').read_text('utf-8')
    css = (root / 'app/web/styles.css').read_text('utf-8')
    assert 'mf-process-nav' in js
    assert "{key:'source',label:'ИСХОДНИК'}" in js
    assert "{key:'branding',label:'ВЫВЕСКА'}" in js
    assert '.mf-process-nav' in css
    assert '.mf-process-step.is-processing' in css
''', "utf-8")

print("Applied Marins Facade v0.7.0 header process navigation patch")
