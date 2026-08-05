let current=null;
let assetMode='source';
let grid=[{x:80,y:80},{x:920,y:80},{x:920,y:920},{x:80,y:920}];
const $=id=>document.getElementById(id);

async function api(url,options={}){
  const r=await fetch(url,options);
  if(!r.ok)throw new Error(await r.text());
  const type=r.headers.get('content-type')||'';
  return type.includes('application/json')?r.json():r.text();
}

async function loadHealth(){
  try{const h=await api('/api/health');$('health').textContent=h.runtime==='standalone-v080'?'system online':'runtime mismatch'}
  catch(_){$('health').textContent='system offline'}
}

async function loadProjects(){
  const items=await api('/api/projects');
  $('project-count').textContent=String(items.length);
  $('projects').innerHTML='';
  items.forEach(p=>{
    const b=document.createElement('button');
    b.textContent=p.name;b.dataset.id=p.id;
    b.classList.toggle('active',current?.id===p.id);
    b.onclick=()=>selectProject(p.id);
    $('projects').appendChild(b);
  });
}

async function selectProject(id){
  current=await api('/api/projects/'+id);
  $('empty').hidden=true;$('workspace').hidden=false;
  $('project-name').textContent=current.name;
  assetMode=current.assets?.geometry_preview?'geometry':'source';
  restoreGrid();renderAll();await loadProjects();
}

function activeStage(){return current?.active_stage||$('stage').value||'geometry'}
function renderAll(){renderPipeline();renderImage();renderGrid();loadHistory();loadDiagnostics()}

function renderPipeline(){
  document.querySelectorAll('#pipeline button').forEach(b=>{
    const status=current?.pipeline?.[b.dataset.stage]||'locked';
    b.className=status;b.querySelector('b').textContent=status;
    b.onclick=()=>{if(status!=='locked'&&['geometry','environment','branding'].includes(b.dataset.stage))$('stage').value=b.dataset.stage};
  });
}

function currentAssetKey(){
  if(assetMode==='geometry'&&current?.assets?.geometry_preview)return 'geometry_preview';
  return current?.assets?.source_preview?'source_preview':current?.assets?.source_master?'source_master':null;
}

function renderImage(){
  const key=currentAssetKey();const img=$('preview');
  if(!key){img.removeAttribute('src');$('meta').textContent='Нет изображения';return}
  img.classList.remove('original');
  img.onload=()=>requestAnimationFrame(renderGrid);
  img.src=`/api/projects/${current.id}/assets/${key}?t=${Date.now()}`;
  $('viewer-title').textContent=assetMode==='geometry'?'Geometry Candidate':'Master Image';
  const c=current.master_canvas;
  const g=current.geometry;
  $('meta').textContent=c?`${c.width} × ${c.height} · master canvas · ${current.event_count||0} events${g?` · outpaint ${(g.transparent_ratio*100).toFixed(2)}%`:''}`:'';
  $('grid-overlay').hidden=assetMode!=='source'||!current?.assets?.source_master;
}

function restoreGrid(){
  const c=current?.master_canvas;
  const q=current?.geometry?.quad;
  if(c&&Array.isArray(q)&&q.length===4){
    grid=q.map(p=>({x:p.x/c.width*1000,y:p.y/c.height*1000}));
  }else{
    grid=[{x:80,y:80},{x:920,y:80},{x:920,y:920},{x:80,y:920}];
  }
}

function renderGrid(){
  const overlay=$('grid-overlay');if(!overlay||overlay.hidden)return;
  $('grid-polygon').setAttribute('points',grid.map(p=>`${p.x},${p.y}`).join(' '));
  const group=$('grid-points');group.innerHTML='';
  grid.forEach((p,index)=>{
    const c=document.createElementNS('http://www.w3.org/2000/svg','circle');
    c.setAttribute('cx',p.x);c.setAttribute('cy',p.y);c.setAttribute('r','18');
    c.dataset.index=String(index);c.classList.add('grid-handle');
    group.appendChild(c);
  });
}

function pointerToGrid(event){
  const rect=$('grid-overlay').getBoundingClientRect();
  return {x:Math.max(0,Math.min(1000,(event.clientX-rect.left)/rect.width*1000)),y:Math.max(0,Math.min(1000,(event.clientY-rect.top)/rect.height*1000))};
}

let dragging=-1;
$('grid-overlay').addEventListener('pointerdown',event=>{
  const handle=event.target.closest('.grid-handle');if(!handle)return;
  dragging=Number(handle.dataset.index);$('grid-overlay').setPointerCapture(event.pointerId);event.preventDefault();
});
$('grid-overlay').addEventListener('pointermove',event=>{if(dragging<0)return;grid[dragging]=pointerToGrid(event);renderGrid()});
$('grid-overlay').addEventListener('pointerup',event=>{dragging=-1;try{$('grid-overlay').releasePointerCapture(event.pointerId)}catch(_){}});

function openTab(name){
  document.querySelectorAll('.tabs button').forEach(b=>b.classList.toggle('active',b.dataset.tab===name));
  document.querySelectorAll('.panel').forEach(p=>p.classList.toggle('active',p.dataset.panel===name));
}

async function loadHistory(){
  if(!current)return;const items=await api(`/api/projects/${current.id}/history?limit=60`);
  $('history').innerHTML=items.slice().reverse().map(e=>`<article class="event"><time>${new Date(e.at).toLocaleString()}</time><strong>${e.type}</strong><pre>${escapeHtml(JSON.stringify(e.payload,null,2))}</pre></article>`).join('')||'<p>Событий пока нет.</p>';
}

async function loadDiagnostics(){if(!current)return;const data=await api(`/api/projects/${current.id}/diagnostics`);$('diagnostics').textContent=JSON.stringify(data,null,2)}
function escapeHtml(v){return String(v).replace(/[&<>"']/g,s=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[s]))}
function showError(error){console.error(error);alert(error?.message||String(error))}

$('new-project').onclick=async()=>{try{const name=prompt('Название проекта');if(!name)return;const f=new FormData();f.append('name',name);current=await api('/api/projects',{method:'POST',body:f});await loadProjects();await selectProject(current.id)}catch(e){showError(e)}};
$('upload').onsubmit=async e=>{e.preventDefault();try{if(!current)return;const file=$('file').files[0];if(!file)return;const f=new FormData();f.append('file',file);current=await api(`/api/projects/${current.id}/source`,{method:'POST',body:f});assetMode='source';restoreGrid();renderAll()}catch(err){showError(err)}};
$('fit').onclick=()=>{$('preview').classList.remove('original')};
$('actual').onclick=()=>{$('preview').classList.add('original')};
$('show-source').onclick=()=>{assetMode='source';renderImage();renderGrid()};
$('show-geometry').onclick=()=>{if(current?.assets?.geometry_preview){assetMode='geometry';renderImage()}};
$('reset-grid').onclick=()=>{grid=[{x:80,y:80},{x:920,y:80},{x:920,y:920},{x:80,y:920}];renderGrid()};

$('apply-grid').onclick=async()=>{try{
  if(!current?.master_canvas)return;
  const c=current.master_canvas;
  const quad=grid.map(p=>({x:Math.round(p.x/1000*c.width),y:Math.round(p.y/1000*c.height)}));
  const f=new FormData();f.append('quad_json',JSON.stringify(quad));
  current=await api(`/api/projects/${current.id}/geometry/apply-grid`,{method:'POST',body:f});
  assetMode='geometry';renderAll();
}catch(e){showError(e)}};

$('approve-geometry').onclick=async()=>{try{if(!current)return;current=await api(`/api/projects/${current.id}/geometry/approve`,{method:'POST'});renderAll()}catch(e){showError(e)}};
$('revise-geometry').onclick=async()=>{try{if(!current)return;const value=prompt('Комментарий к геометрии');if(!value)return;const f=new FormData();f.append('comment',value);current=await api(`/api/projects/${current.id}/geometry/revise`,{method:'POST',body:f});assetMode='source';restoreGrid();renderAll();openTab('history')}catch(e){showError(e)}};

document.querySelectorAll('.tabs button').forEach(b=>b.onclick=()=>openTab(b.dataset.tab));
$('save-comment').onclick=async()=>{try{if(!current)return;const value=$('comment').value.trim();if(!value)return;const f=new FormData();f.append('comment',value);current=await api(`/api/projects/${current.id}/comments/${$('stage').value}`,{method:'POST',body:f});$('comment').value='';renderAll();openTab('history')}catch(e){showError(e)}};
$('show-prompt').onclick=async()=>{try{if(!current)return;const r=await api(`/api/projects/${current.id}/prompt/${$('stage').value}`);$('prompt').textContent=r.prompt;await loadHistory();openTab('prompt')}catch(e){showError(e)}};
$('refresh-diagnostics').onclick=loadDiagnostics;
$('quality-check').onclick=async()=>{try{if(!current?.assets?.source_master)return;const key=assetMode==='geometry'&&current.assets.geometry_candidate?'geometry_candidate':'source_master';const report=await api(`/api/projects/${current.id}/quality/${key}`);$('diagnostics').textContent=JSON.stringify(report,null,2);await selectProject(current.id);openTab('diagnostics')}catch(e){showError(e)}};

Promise.all([loadHealth(),loadProjects()]).catch(console.error);
