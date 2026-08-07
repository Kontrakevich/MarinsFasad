const $ = id => document.getElementById(id);
let current = null;

async function api(url, options={}){
  const response = await fetch(url, options);
  if(!response.ok) throw new Error(await response.text());
  return response.json();
}
function formData(values){const data=new FormData();Object.entries(values).forEach(([k,v])=>{if(v!==undefined&&v!==null)data.append(k,v)});return data}
function fileUrl(key){return current?.active_files?.[key] ? `/api/projects/${current.id}/file/${key}?t=${Date.now()}` : ''}
function showAction(title, description, state='working'){
  const panel=$('action-feedback'); if(!panel)return;
  panel.className=`action-feedback is-${state}`;
  $('action-code').textContent=state==='success'?'ACTION / DONE':state==='error'?'ACTION / ERROR':'ACTION / RUNNING';
  $('action-title').textContent=title; $('action-description').textContent=description;
}
async function busy(button, title, work){const text=button.textContent;button.disabled=true;button.textContent='Выполняется…';showAction(title,'Операция выполняется.','working');try{const result=await work();showAction(title,'Операция завершена.','success');return result}catch(error){showAction('Ошибка',error.message,'error');alert(error.message);throw error}finally{button.disabled=false;button.textContent=text}}

async function health(){try{const data=await api('/api/health');$('health').innerHTML=`<i></i>ONLINE / ${data.openrouter_configured?'OPENROUTER READY':'NO API KEY'}`}catch{$('health').textContent='OFFLINE'}}
const stageLabels={source:'Исходник',geometry_editing:'Редактирование геометрии',geometry_review:'Проверка геометрии',environment_ready:'Окружение готово к запуску',environment_processing:'Генерация окружения',environment_review:'Проверка окружения',final:'Final',branding_ready:'Вывеска готова к настройке',branding_processing:'Генерация вывески',branding_review:'Проверка вывески',complete:'Завершено'};
function stageLabel(value){return stageLabels[value]||String(value||'').replaceAll('_',' ')}
async function refreshProjects(){const list=await api('/api/projects');if(!list.length){$('project-list').innerHTML='<div class="project-list-empty">Рабочих проектов пока нет. Нажмите «Новый проект».</div>';return}$('project-list').innerHTML=list.map(item=>`<button class="project-card ${current?.id===item.id?'is-active':''}" data-id="${item.id}"><span class="project-card__top"><strong>${escapeHtml(item.name)}</strong><span class="project-card__status">${escapeHtml(stageLabel(item.current_stage))}</span></span><small>Обновлён: ${escapeHtml(new Date(item.updated_at).toLocaleString('ru-RU'))}</small></button>`).join('');document.querySelectorAll('.project-card').forEach(card=>card.onclick=()=>openProject(card.dataset.id))}
async function openProject(id){current=await api(`/api/projects/${id}`);render();await refreshProjects()}
function escapeHtml(value){return String(value??'').replace(/[&<>'"]/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[ch]))}

$('new-project').onclick=async()=>{const name=prompt('Название проекта');if(!name)return;current=await api('/api/projects',{method:'POST',body:formData({name})});render();await refreshProjects()}
$('upload-source').onclick=async()=>{const file=$('source-file').files[0];if(!current||!file)return alert('Создайте проект и выберите изображение');await busy($('upload-source'),'Загрузка исходника',()=>api(`/api/projects/${current.id}/source`,{method:'POST',body:formData({file})}));geo.image=null;geo.projectId=null;geo.sourcePath=null;await reload()}
async function reload(){if(!current)return;current=await api(`/api/projects/${current.id}`);render();await refreshProjects()}

function renderStages(){const names={source:'Исходник',geometry:'Геометрия',environment:'Окружение',final:'Final',branding:'Вывеска'};$('stage-strip').innerHTML=Object.entries(current.statuses).map(([key,status])=>`<div class="stage-chip status-${status}"><span>${escapeHtml(names[key]||key)}</span><strong>${escapeHtml(status)}</strong></div>`).join('')}
function setImage(id,key){const el=$(id);const url=fileUrl(key);if(url){el.src=url;el.style.visibility='visible'}else{el.removeAttribute('src');el.style.visibility='hidden'}}
async function loadSkill(stage){try{const data=await api(`/api/projects/${current.id}/skill/${stage}`);$(`${stage}-skill`) && ($(`${stage}-skill`).value=data.skill)}catch{}}
async function loadPrompt(stage){const extra=$(`${stage}-extra`)?.value||'';try{const data=await api(`/api/projects/${current.id}/prompt/${stage}?operator_comment=${encodeURIComponent(extra)}`);$(`${stage}-prompt`).value=data.prompt}catch(error){$(`${stage}-prompt`).value=error.message}}
function render(){if(!current)return;$('onboarding')?.classList.add('hidden');$('workspace').classList.remove('hidden');$('project-title').textContent=current.name;renderStages();$('source-status').textContent=current.active_files.source?`Загружено: ${current.active_files.source}`:'Файл не загружен.';const hasSource=!!current.active_files.source;$('geometry-empty').classList.toggle('hidden',hasSource);$('geometry-editor').classList.toggle('hidden',!hasSource);setImage('geometry-before','source');setImage('geometry-after','geometry');$('geometry-comparison').classList.toggle('hidden',!current.active_files.geometry);setImage('environment-before','geometry');setImage('environment-after','environment');setImage('branding-before','final');setImage('branding-after','branding');$('environment-runtime').textContent=current.runtime?.environment?JSON.stringify(current.runtime.environment,null,2):'Нет запуска.';loadSkill('geometry');loadPrompt('environment');loadPrompt('branding');if(hasSource)loadGeometryImage();loadBrandingImage();setReviewButtons()}
function setReviewButtons(){document.querySelectorAll('.approve-stage,.revise-stage').forEach(button=>{const stage=button.dataset.stage;button.disabled=current.statuses[stage]!=='review'})}

// Geometry perspective grid
const geo={image:null,corners:[],drag:-1,history:[],future:[],projectId:null,sourcePath:null};
function defaultCorners(img){const x=img.naturalWidth*.12,y=img.naturalHeight*.12;return[{x,y},{x:img.naturalWidth-x,y},{x:img.naturalWidth-x,y:img.naturalHeight-y},{x,y:img.naturalHeight-y}]}
function loadGeometryImage(){if(geo.projectId===current.id&&geo.sourcePath===current.active_files.source&&geo.image){drawGeometry();return}const img=new Image();img.onload=()=>{geo.image=img;geo.projectId=current.id;geo.sourcePath=current.active_files.source;geo.corners=Array.isArray(current.geometry_grid)&&current.geometry_grid.length===4?current.geometry_grid.map(p=>({x:+p.x,y:+p.y})):defaultCorners(img);geo.history=[];geo.future=[];resizeGeometry()};img.src=fileUrl('source')}
function resizeGeometry(){const canvas=$('geometry-canvas');if(!geo.image)return;canvas.width=geo.image.naturalWidth;canvas.height=geo.image.naturalHeight;const max=canvas.parentElement.clientWidth-24;const scale=Math.min(1,max/canvas.width);canvas.style.width=`${Math.round(canvas.width*scale)}px`;canvas.style.height=`${Math.round(canvas.height*scale)}px`;drawGeometry()}
function bilinear(u,v){const [tl,tr,br,bl]=geo.corners;const top={x:tl.x+(tr.x-tl.x)*u,y:tl.y+(tr.y-tl.y)*u};const bottom={x:bl.x+(br.x-bl.x)*u,y:bl.y+(br.y-bl.y)*u};return{x:top.x+(bottom.x-top.x)*v,y:top.y+(bottom.y-top.y)*v}}
function drawGeometry(){const c=$('geometry-canvas'),img=geo.image;if(!img||geo.corners.length!==4)return;const ctx=c.getContext('2d');ctx.clearRect(0,0,c.width,c.height);ctx.drawImage(img,0,0,c.width,c.height);ctx.strokeStyle='#19d3c5';ctx.lineWidth=Math.max(2,c.width/1100);ctx.setLineDash([Math.max(10,c.width/180),Math.max(7,c.width/260)]);for(let i=0;i<=8;i++){const u=i/8;let p=bilinear(u,0);ctx.beginPath();ctx.moveTo(p.x,p.y);for(let s=1;s<=30;s++){p=bilinear(u,s/30);ctx.lineTo(p.x,p.y)}ctx.stroke()}for(let i=0;i<=6;i++){const v=i/6;let p=bilinear(0,v);ctx.beginPath();ctx.moveTo(p.x,p.y);for(let s=1;s<=30;s++){p=bilinear(s/30,v);ctx.lineTo(p.x,p.y)}ctx.stroke()}ctx.strokeStyle='#fff';ctx.lineWidth=Math.max(3,c.width/700);ctx.setLineDash([16,10]);ctx.beginPath();ctx.moveTo(geo.corners[0].x,geo.corners[0].y);geo.corners.slice(1).forEach(p=>ctx.lineTo(p.x,p.y));ctx.closePath();ctx.stroke();ctx.setLineDash([]);geo.corners.forEach((p,i)=>{ctx.beginPath();ctx.arc(p.x,p.y,Math.max(12,c.width/140),0,Math.PI*2);ctx.fillStyle='#008a90';ctx.fill();ctx.strokeStyle='#fff';ctx.stroke();ctx.fillStyle='#fff';ctx.font=`${Math.max(18,c.width/70)}px Arial`;ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(String(i+1),p.x,p.y)})}
function geoPos(event){const c=$('geometry-canvas'),r=c.getBoundingClientRect();return{x:(event.clientX-r.left)*c.width/r.width,y:(event.clientY-r.top)*c.height/r.height}}
function geoHit(p){const c=$('geometry-canvas'),r=c.getBoundingClientRect(),radius=30*c.width/r.width;let index=-1,best=Infinity;geo.corners.forEach((q,i)=>{const d=Math.hypot(p.x-q.x,p.y-q.y);if(d<radius&&d<best){index=i;best=d}});return index}
const gc=$('geometry-canvas');gc.onpointerdown=e=>{const i=geoHit(geoPos(e));if(i<0)return;geo.history.push(geo.corners.map(p=>({...p})));geo.future=[];geo.drag=i;gc.setPointerCapture(e.pointerId)};gc.onpointermove=e=>{if(geo.drag<0)return;const p=geoPos(e);geo.corners[geo.drag]={x:Math.max(0,Math.min(gc.width,p.x)),y:Math.max(0,Math.min(gc.height,p.y))};drawGeometry()};gc.onpointerup=e=>{geo.drag=-1;try{gc.releasePointerCapture(e.pointerId)}catch{}};gc.ondblclick=()=>resetGeometry();
function resetGeometry(){if(!geo.image)return;geo.history.push(geo.corners.map(p=>({...p})));geo.corners=defaultCorners(geo.image);geo.future=[];drawGeometry()}
$('geometry-reset').onclick=resetGeometry;$('geometry-undo').onclick=()=>{if(!geo.history.length)return;geo.future.push(geo.corners.map(p=>({...p})));geo.corners=geo.history.pop();drawGeometry()};$('geometry-redo').onclick=()=>{if(!geo.future.length)return;geo.history.push(geo.corners.map(p=>({...p})));geo.corners=geo.future.pop();drawGeometry()};
$('geometry-apply').onclick=async()=>{await busy($('geometry-apply'),'Коррекция геометрии',()=>api(`/api/projects/${current.id}/geometry/apply-grid`,{method:'POST',body:formData({quad_json:JSON.stringify(geo.corners)})}));await reload()}
window.addEventListener('resize',resizeGeometry);

$('environment-refresh-prompt').onclick=()=>loadPrompt('environment');$('environment-extra').addEventListener('input',debounce(()=>loadPrompt('environment'),350));$('environment-generate').onclick=async()=>{await busy($('environment-generate'),'Генерация окружения',()=>api(`/api/projects/${current.id}/environment/generate`,{method:'POST',body:formData({operator_comment:$('environment-extra').value})}));await reload()}

// Branding zone editor
const brand={image:null,rect:null,drawing:false,start:null,projectId:null};
function loadBrandingImage(){if(!current.active_files.final){const c=$('branding-canvas');c.width=900;c.height=400;const x=c.getContext('2d');x.fillStyle='#111';x.fillRect(0,0,c.width,c.height);x.fillStyle='#aaa';x.font='24px Arial';x.fillText('Final появится после утверждения окружения',40,70);return}if(brand.projectId===current.id&&brand.image){drawBranding();return}const img=new Image();img.onload=()=>{brand.image=img;brand.projectId=current.id;brand.rect=current.branding_zone||null;const c=$('branding-canvas');c.width=img.naturalWidth;c.height=img.naturalHeight;const max=c.parentElement.clientWidth-20,scale=Math.min(1,max/c.width);c.style.width=`${Math.round(c.width*scale)}px`;c.style.height=`${Math.round(c.height*scale)}px`;drawBranding()};img.src=fileUrl('final')}
function brandPos(e){const c=$('branding-canvas'),r=c.getBoundingClientRect();return{x:(e.clientX-r.left)*c.width/r.width,y:(e.clientY-r.top)*c.height/r.height}}
function drawBranding(){const c=$('branding-canvas'),ctx=c.getContext('2d');if(!brand.image)return;ctx.clearRect(0,0,c.width,c.height);ctx.drawImage(brand.image,0,0,c.width,c.height);if(brand.rect){ctx.fillStyle='rgba(0,138,144,.18)';ctx.strokeStyle='#00d4c7';ctx.lineWidth=Math.max(3,c.width/700);ctx.setLineDash([16,10]);ctx.fillRect(brand.rect.x,brand.rect.y,brand.rect.width,brand.rect.height);ctx.strokeRect(brand.rect.x,brand.rect.y,brand.rect.width,brand.rect.height);ctx.setLineDash([]);$('branding-zone-text').textContent=`x ${Math.round(brand.rect.x)} · y ${Math.round(brand.rect.y)} · w ${Math.round(brand.rect.width)} · h ${Math.round(brand.rect.height)}`}else $('branding-zone-text').textContent='Зона не задана. Проведите мышью по изображению.'}
const bc=$('branding-canvas');bc.onpointerdown=e=>{if(!brand.image)return;brand.drawing=true;brand.start=brandPos(e);brand.rect={x:brand.start.x,y:brand.start.y,width:0,height:0};bc.setPointerCapture(e.pointerId)};bc.onpointermove=e=>{if(!brand.drawing)return;const p=brandPos(e);brand.rect={x:Math.min(brand.start.x,p.x),y:Math.min(brand.start.y,p.y),width:Math.abs(p.x-brand.start.x),height:Math.abs(p.y-brand.start.y)};drawBranding()};bc.onpointerup=e=>{brand.drawing=false;try{bc.releasePointerCapture(e.pointerId)}catch{}};
$('branding-setup').onclick=async()=>{const logo=$('branding-logo').files[0];if(!brand.rect||brand.rect.width<20||brand.rect.height<20)return alert('Нарисуйте зону вывески');if(!logo&&!current.active_files.branding_logo)return alert('Загрузите логотип');await busy($('branding-setup'),'Фиксация зоны вывески',()=>api(`/api/projects/${current.id}/branding/setup`,{method:'POST',body:formData({zone_json:JSON.stringify(brand.rect),material:$('branding-material').value,logo})}));await reload()}
$('branding-extra').addEventListener('input',debounce(()=>loadPrompt('branding'),350));$('branding-generate').onclick=async()=>{await busy($('branding-generate'),'Генерация вывески',()=>api(`/api/projects/${current.id}/branding/generate`,{method:'POST',body:formData({operator_comment:$('branding-extra').value})}));await reload()}

// Review actions
document.querySelectorAll('.approve-stage').forEach(button=>button.onclick=async()=>{const stage=button.dataset.stage;const comment=$(`${stage}-comment`).value;await busy(button,`Подтверждение: ${stage}`,()=>api(`/api/projects/${current.id}/${stage}/approve`,{method:'POST',body:formData({comment})}));$(`${stage}-comment`).value='';await reload()});document.querySelectorAll('.revise-stage').forEach(button=>button.onclick=async()=>{const stage=button.dataset.stage;const comment=$(`${stage}-comment`).value.trim();if(!comment)return alert('Комментарий обязателен');await busy(button,`Доработка: ${stage}`,()=>api(`/api/projects/${current.id}/${stage}/revise`,{method:'POST',body:formData({comment})}));$(`${stage}-comment`).value='';await reload()});

async function refreshHistory(){if(!current)return;const data=await api(`/api/projects/${current.id}/diagnostics`);$('history-list').innerHTML=[...data.events].reverse().map(item=>`<div class="history-item"><strong>${escapeHtml(item.at)}</strong><div><b>${escapeHtml(item.event)}</b><pre>${escapeHtml(JSON.stringify(item.payload,null,2))}</pre></div></div>`).join('')||'<div class="empty-note">История пуста.</div>'}
$('refresh-history').onclick=refreshHistory;
function debounce(fn,delay){let timer;return(...args)=>{clearTimeout(timer);timer=setTimeout(()=>fn(...args),delay)}}
health();refreshProjects();


// v0.6.9 original-size image viewer
(function(){
  document.addEventListener('click', function(event){
    const img=event.target.closest('img');
    if(!img || img.dataset.noOriginal==='1') return;
    event.preventDefault();
    window.open(img.currentSrc||img.src, '_blank', 'noopener,noreferrer');
  });
  const observer=new MutationObserver(()=>document.querySelectorAll('img:not([data-original-ready])').forEach(img=>{img.dataset.originalReady='1';img.title='Открыть изображение в оригинальном размере';img.classList.add('mf-original-image');}));
  observer.observe(document.documentElement,{childList:true,subtree:true});
})();


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
