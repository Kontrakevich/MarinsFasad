(() => {
  'use strict';
  let current = null;
  const $ = id => document.getElementById(id);
  const api = async (url, options = {}) => {
    const response = await fetch(url, options);
    if (!response.ok) throw new Error(await response.text());
    const type = response.headers.get('content-type') || '';
    return type.includes('application/json') ? response.json() : response.text();
  };
  const show = (el, value = true) => el && el.classList.toggle('hidden', !value);
  const notify = (title, description = '') => {
    if ($('action-title')) $('action-title').textContent = title;
    if ($('action-description')) $('action-description').textContent = description;
  };
  const assetUrl = key => current?.assets?.[key] ? `/api/projects/${current.id}/assets/${key}?v=${Date.now()}` : '';
  const formData = values => { const data = new FormData(); Object.entries(values).forEach(([key,value]) => { if (value !== undefined && value !== null) data.append(key,value); }); return data; };

  async function health() {
    try {
      const data = await api('/api/health');
      const node = $('health');
      if (node) {
        node.classList.toggle('ok', data.runtime === 'standalone-v080');
        node.classList.toggle('bad', data.runtime !== 'standalone-v080');
        if (node.lastChild) node.lastChild.textContent = data.runtime === 'standalone-v080' ? 'Система работает' : 'Runtime mismatch';
      }
    } catch (_) { $('health')?.classList.add('bad'); }
  }

  function renderStageStrip() {
    const strip = $('stage-strip');
    if (!strip || !current) return;
    const labels = {source:'ИСХОДНИК', geometry:'ГЕОМЕТРИЯ', environment:'ОКРУЖЕНИЕ', final:'FINAL', branding:'ВЫВЕСКА'};
    strip.innerHTML = Object.entries(labels).map(([key,label]) => {
      const status = current.pipeline?.[key] || 'locked';
      return `<div class="stage-cell ${status}"><small>${label}</small><strong>${status}</strong></div>`;
    }).join('');
  }

  function setImage(id, key) {
    const img = $(id); if (!img) return;
    const url = assetUrl(key);
    if (url) { img.src = url; img.hidden = false; img.style.visibility = 'visible'; }
    else { img.removeAttribute('src'); img.hidden = true; }
  }

  function renderProject() {
    if (!current) return;
    $('project-title').textContent = current.name;
    show($('onboarding'), false); show($('workspace'), true); renderStageStrip();
    const master = current.master_canvas;
    $('source-status').textContent = master ? `Оригинал: ${master.width} × ${master.height}. Production policy: original resolution.` : 'Файл не загружен.';
    const sourceKey = current.assets?.source_master ? 'source_master' : 'source_preview';
    setImage('geometry-before', sourceKey);
    setImage('geometry-after', current.assets?.geometry_candidate ? 'geometry_candidate' : sourceKey);
    setImage('environment-before', current.assets?.geometry_candidate ? 'geometry_candidate' : sourceKey);
    setImage('environment-after', current.assets?.environment_candidate ? 'environment_candidate' : sourceKey);
    setImage('branding-before', current.assets?.environment_candidate ? 'environment_candidate' : sourceKey);
    setImage('branding-after', current.assets?.branding_candidate ? 'branding_candidate' : 'environment_candidate');
    const hasSource = !!current.assets?.source_master;
    show($('geometry-empty'), !hasSource); show($('geometry-editor'), hasSource);
    show($('geometry-comparison'), !!current.assets?.geometry_candidate);
    if (hasSource) loadGeometryImage();
  }

  async function selectProject(id) { current = await api(`/api/projects/${id}`); renderProject(); await loadProjects(); }
  async function loadProjects() {
    const projects = await api('/api/projects'); const list = $('project-list'); if (!list) return;
    list.innerHTML = '';
    projects.forEach(project => {
      const button = document.createElement('button');
      button.className = `project-chip${current?.id === project.id ? ' active' : ''}`;
      button.textContent = project.name; button.onclick = () => selectProject(project.id).catch(error => alert(error.message)); list.appendChild(button);
    });
  }
  async function createProject() {
    const name = prompt('Название проекта'); if (!name) return;
    current = await api('/api/projects', {method:'POST', body:formData({name})}); await loadProjects(); renderProject();
  }
  async function uploadSource() {
    if (!current) return alert('Сначала создайте проект.');
    const file = $('source-file')?.files?.[0]; if (!file) return alert('Выберите изображение.');
    notify('Загрузка оригинала', `${file.name} · ${(file.size/1048576).toFixed(1)} MB`);
    current = await api(`/api/projects/${current.id}/source`, {method:'POST', body:formData({file})});
    geo.image = null; geo.projectId = null; geo.sourcePath = null;
    renderProject(); notify('Исходник загружен', 'Оригинальное разрешение сохранено.');
  }
  async function addRevision(stage) {
    if (!current) return;
    const field = $(`${stage}-comment`); const comment = field?.value?.trim(); if (!comment) return alert('Введите комментарий.');
    current = await api(`/api/projects/${current.id}/comments/${stage}`, {method:'POST', body:formData({comment})});
    if (field) field.value = ''; renderProject(); notify('Комментарий принят', 'Он включён в compiled prompt этапа.');
  }
  async function compile(stage) {
    if (!current) return;
    const result = await api(`/api/projects/${current.id}/prompt/${stage}`); const target = $(`${stage}-prompt`); if (target) target.value = result.prompt || ''; return result;
  }
  async function setStage(stage, status) {
    if (!current) return;
    current = await api(`/api/projects/${current.id}/stages/${stage}/status`, {method:'POST', body:formData({status})}); renderProject();
  }
  async function loadHistory() {
    if (!current) return;
    const events = await api(`/api/projects/${current.id}/history`); const target = $('history-list'); if (!target) return;
    target.innerHTML = events.map(event => `<article class="history-entry"><time>${event.timestamp || ''}</time><strong>${event.type || event.event_type || 'Event'}</strong><pre>${JSON.stringify(event.payload || {}, null, 2)}</pre></article>`).join('') || '<div class="empty-note">История пуста.</div>';
  }

  // Exact v0.7 Perspective Grid behavior, connected to v0.8 master-image API.
  const geo = {image:null,corners:[],drag:-1,history:[],future:[],projectId:null,sourcePath:null};
  function defaultCorners(img){const x=img.naturalWidth*.12,y=img.naturalHeight*.12;return[{x,y},{x:img.naturalWidth-x,y},{x:img.naturalWidth-x,y:img.naturalHeight-y},{x,y:img.naturalHeight-y}]}
  function loadGeometryImage(){
    const sourcePath=current?.assets?.source_master;
    if(!sourcePath)return;
    if(geo.projectId===current.id&&geo.sourcePath===sourcePath&&geo.image){drawGeometry();return}
    const img=new Image();
    img.onload=()=>{
      geo.image=img;geo.projectId=current.id;geo.sourcePath=sourcePath;
      const saved=current?.geometry?.quad;
      geo.corners=Array.isArray(saved)&&saved.length===4?saved.map(p=>({x:+p.x,y:+p.y})):defaultCorners(img);
      geo.history=[];geo.future=[];resizeGeometry();
    };
    img.src=assetUrl('source_master');
  }
  function resizeGeometry(){
    const canvas=$('geometry-canvas');if(!canvas||!geo.image)return;
    canvas.width=geo.image.naturalWidth;canvas.height=geo.image.naturalHeight;
    const max=Math.max(320,(canvas.parentElement?.clientWidth||canvas.width)-24);const scale=Math.min(1,max/canvas.width);
    canvas.style.width=`${Math.round(canvas.width*scale)}px`;canvas.style.height=`${Math.round(canvas.height*scale)}px`;drawGeometry();
  }
  function bilinear(u,v){const[tl,tr,br,bl]=geo.corners;const top={x:tl.x+(tr.x-tl.x)*u,y:tl.y+(tr.y-tl.y)*u};const bottom={x:bl.x+(br.x-bl.x)*u,y:bl.y+(br.y-bl.y)*u};return{x:top.x+(bottom.x-top.x)*v,y:top.y+(bottom.y-top.y)*v}}
  function drawGeometry(){
    const c=$('geometry-canvas'),img=geo.image;if(!c||!img||geo.corners.length!==4)return;
    const ctx=c.getContext('2d');ctx.clearRect(0,0,c.width,c.height);ctx.drawImage(img,0,0,c.width,c.height);
    ctx.strokeStyle='#19d3c5';ctx.lineWidth=Math.max(2,c.width/1100);ctx.setLineDash([Math.max(10,c.width/180),Math.max(7,c.width/260)]);
    for(let i=0;i<=8;i++){const u=i/8;let p=bilinear(u,0);ctx.beginPath();ctx.moveTo(p.x,p.y);for(let s=1;s<=30;s++){p=bilinear(u,s/30);ctx.lineTo(p.x,p.y)}ctx.stroke()}
    for(let i=0;i<=6;i++){const v=i/6;let p=bilinear(0,v);ctx.beginPath();ctx.moveTo(p.x,p.y);for(let s=1;s<=30;s++){p=bilinear(s/30,v);ctx.lineTo(p.x,p.y)}ctx.stroke()}
    ctx.strokeStyle='#fff';ctx.lineWidth=Math.max(3,c.width/700);ctx.setLineDash([16,10]);ctx.beginPath();ctx.moveTo(geo.corners[0].x,geo.corners[0].y);geo.corners.slice(1).forEach(p=>ctx.lineTo(p.x,p.y));ctx.closePath();ctx.stroke();ctx.setLineDash([]);
    geo.corners.forEach((p,i)=>{ctx.beginPath();ctx.arc(p.x,p.y,Math.max(12,c.width/140),0,Math.PI*2);ctx.fillStyle='#008a90';ctx.fill();ctx.strokeStyle='#fff';ctx.stroke();ctx.fillStyle='#fff';ctx.font=`${Math.max(18,c.width/70)}px Arial`;ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(String(i+1),p.x,p.y)});
  }
  function geoPos(event){const c=$('geometry-canvas'),r=c.getBoundingClientRect();return{x:(event.clientX-r.left)*c.width/r.width,y:(event.clientY-r.top)*c.height/r.height}}
  function geoHit(p){const c=$('geometry-canvas'),r=c.getBoundingClientRect(),radius=30*c.width/r.width;let index=-1,best=Infinity;geo.corners.forEach((q,i)=>{const d=Math.hypot(p.x-q.x,p.y-q.y);if(d<radius&&d<best){index=i;best=d}});return index}
  function resetGeometry(){if(!geo.image)return;geo.history.push(geo.corners.map(p=>({...p})));geo.corners=defaultCorners(geo.image);geo.future=[];drawGeometry()}
  const gc=$('geometry-canvas');
  if(gc){
    gc.onpointerdown=e=>{const i=geoHit(geoPos(e));if(i<0)return;geo.history.push(geo.corners.map(p=>({...p})));geo.future=[];geo.drag=i;gc.setPointerCapture(e.pointerId)};
    gc.onpointermove=e=>{if(geo.drag<0)return;const p=geoPos(e);geo.corners[geo.drag]={x:Math.max(0,Math.min(gc.width,p.x)),y:Math.max(0,Math.min(gc.height,p.y))};drawGeometry()};
    gc.onpointerup=e=>{geo.drag=-1;try{gc.releasePointerCapture(e.pointerId)}catch{}};
    gc.onpointercancel=()=>{geo.drag=-1};gc.ondblclick=resetGeometry;
  }
  if($('geometry-reset')) $('geometry-reset').onclick=resetGeometry;
  if($('geometry-undo')) $('geometry-undo').onclick=()=>{if(!geo.history.length)return;geo.future.push(geo.corners.map(p=>({...p})));geo.corners=geo.history.pop();drawGeometry()};
  if($('geometry-redo')) $('geometry-redo').onclick=()=>{if(!geo.future.length)return;geo.history.push(geo.corners.map(p=>({...p})));geo.corners=geo.future.pop();drawGeometry()};
  if($('geometry-apply')) $('geometry-apply').onclick=async()=>{
    if(!current||!geo.image||geo.corners.length!==4)return alert('Загрузите исходник и настройте четыре точки.');
    notify('Коррекция геометрии','Полноразмерная перспективная трансформация выполняется без crop и downscale.');
    current=await api(`/api/projects/${current.id}/geometry/apply-grid`,{method:'POST',body:formData({quad_json:JSON.stringify(geo.corners)})});
    renderProject();notify('Geometry candidate создан','Canvas исходника сохранён; пустые области переданы в outpaint mask.');
  };
  window.addEventListener('resize',resizeGeometry);

  $('new-project') && ($('new-project').onclick = () => createProject().catch(error => alert(error.message)));
  $('upload-source') && ($('upload-source').onclick = () => uploadSource().catch(error => alert(error.message)));
  $('environment-refresh-prompt') && ($('environment-refresh-prompt').onclick = () => compile('environment').catch(error => alert(error.message)));
  $('branding-setup') && ($('branding-setup').onclick = () => compile('branding').catch(error => alert(error.message)));
  $('refresh-history') && ($('refresh-history').onclick = () => loadHistory().catch(error => alert(error.message)));
  document.querySelectorAll('.revise-stage').forEach(button => button.onclick = () => addRevision(button.dataset.stage).catch(error => alert(error.message)));
  document.querySelectorAll('.approve-stage').forEach(button => button.onclick = async()=>{
    const stage=button.dataset.stage;
    if(stage==='geometry') current=await api(`/api/projects/${current.id}/geometry/approve`,{method:'POST'});
    else if(stage==='environment') current=await api(`/api/projects/${current.id}/environment/approve`,{method:'POST'});
    else await setStage(stage,'approved');
    renderProject();
  });
  $('environment-generate') && ($('environment-generate').onclick = async () => { current=await api(`/api/projects/${current.id}/environment/generate`,{method:'POST'});renderProject(); });
  $('branding-generate') && ($('branding-generate').onclick = async () => { await compile('branding'); notify('Branding', 'Prompt собран.'); });

  Promise.all([health(), loadProjects()]).catch(error => console.error(error));
})();
