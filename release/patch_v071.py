from __future__ import annotations

import re
import sys
from pathlib import Path

runtime = Path(sys.argv[1])
main_path = runtime / "app/main.py"
app_js = runtime / "app/web/app.js"
styles_path = runtime / "app/web/styles.css"
test_path = runtime / "tests/test_v071_resolution_outpaint_viewer.py"

main = main_path.read_text("utf-8")
main = re.sub(r'^APP_VERSION = "[^"]+"$', 'APP_VERSION = "0.7.1"', main, count=1, flags=re.MULTILINE)
marker = "# v0.7.1 strict master-canvas, outpaint mask and quality gate"
if marker not in main:
    main += r'''

# v0.7.1 strict master-canvas, outpaint mask and quality gate
import json as _mf071_json
import threading as _mf071_threading
import time as _mf071_time
from collections import deque as _mf071_deque
from pathlib import Path as _mf071_Path
from PIL import Image as _mf071_Image, ImageOps as _mf071_ImageOps


def _mf071_image_size(path: _mf071_Path):
    with _mf071_Image.open(path) as im:
        im = _mf071_ImageOps.exif_transpose(im)
        return im.size


def _mf071_source_path(project: _mf071_Path, state: dict):
    files = state.get('active_files') or {}
    candidates = [files.get('source'), files.get('original'), state.get('source_file')]
    for value in candidates:
        if not value:
            continue
        path = (project / str(value).replace('files/', '', 1).lstrip('/')).resolve()
        if path.exists() and project in path.parents:
            return path
    source_dir = project / 'source'
    for path in source_dir.glob('*') if source_dir.exists() else []:
        if path.suffix.lower() in {'.jpg','.jpeg','.png','.webp','.tif','.tiff'}:
            return path
    return None


def _mf071_border_black_mask(im, threshold=20):
    rgba = im.convert('RGBA')
    px = rgba.load(); w,h = rgba.size
    seen = bytearray(w*h); q = _mf071_deque()
    def black(x,y):
        r,g,b,a = px[x,y]
        return a > 0 and r <= threshold and g <= threshold and b <= threshold
    for x in range(w):
        if black(x,0): q.append((x,0))
        if h>1 and black(x,h-1): q.append((x,h-1))
    for y in range(h):
        if black(0,y): q.append((0,y))
        if w>1 and black(w-1,y): q.append((w-1,y))
    count=0
    while q:
        x,y=q.popleft(); i=y*w+x
        if seen[i] or not black(x,y): continue
        seen[i]=1; count+=1
        for nx,ny in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
            if 0<=nx<w and 0<=ny<h and not seen[ny*w+nx]: q.append((nx,ny))
    return rgba, seen, count


def _mf071_prepare_outpaint(path: _mf071_Path, master_size):
    with _mf071_Image.open(path) as src:
        src = _mf071_ImageOps.exif_transpose(src)
        if src.size != master_size:
            src = src.resize(master_size, _mf071_Image.Resampling.LANCZOS)
        rgba, mask, count = _mf071_border_black_mask(src)
        if count:
            px=rgba.load(); w,h=rgba.size
            for i,flag in enumerate(mask):
                if flag:
                    x=i%w; y=i//w
                    r,g,b,_=px[x,y]; px[x,y]=(r,g,b,0)
        out = path.with_suffix('.png')
        rgba.save(out, 'PNG', optimize=False, compress_level=1)
    return out, count


def _mf071_normalize_result(path: _mf071_Path, master_size):
    with _mf071_Image.open(path) as src:
        src = _mf071_ImageOps.exif_transpose(src).convert('RGB')
        original_size = src.size
        if src.size != master_size:
            src = src.resize(master_size, _mf071_Image.Resampling.LANCZOS)
        out = path.with_suffix('.png')
        src.save(out, 'PNG', optimize=False, compress_level=1)
    with _mf071_Image.open(out) as check:
        _, _, remaining = _mf071_border_black_mask(check, threshold=16)
    return out, original_size, remaining


def _mf071_rel(project, path):
    return str(path.relative_to(project)).replace('\\','/')


def _mf071_quality_pass():
    root = DATA_ROOT if 'DATA_ROOT' in globals() else ROOT / 'data' / 'projects'
    while True:
        try:
            for project in root.iterdir() if root.exists() else []:
                state_file=project/'project.json'
                if not state_file.exists(): continue
                try: state=_mf071_json.loads(state_file.read_text('utf-8'))
                except Exception: continue
                source=_mf071_source_path(project,state)
                if not source: continue
                try: master=_mf071_image_size(source)
                except Exception: continue
                files=state.get('active_files') or {}
                changed=False
                report=state.setdefault('quality_control',{})
                report['master_canvas']={'width':master[0],'height':master[1],'policy':'strict_original_canvas'}

                geometry=files.get('geometry') or files.get('corrected')
                if geometry:
                    gp=(project/str(geometry).replace('files/','',1).lstrip('/')).resolve()
                    if gp.exists() and project in gp.parents:
                        key=f'{gp.stat().st_mtime_ns}:{gp.stat().st_size}'
                        if report.get('geometry_checked_key')!=key:
                            out,count=_mf071_prepare_outpaint(gp,master)
                            files['geometry']=_mf071_rel(project,out)
                            files['corrected']=files['geometry']
                            report.update({'geometry_checked_key':f'{out.stat().st_mtime_ns}:{out.stat().st_size}','geometry_outpaint_pixels':count,'geometry_canvas':list(master),'geometry_mask_mode':'transparent_border_connected_black'})
                            changed=True

                for stage in ('environment','final','branding'):
                    value=files.get(stage)
                    if not value: continue
                    p=(project/str(value).replace('files/','',1).lstrip('/')).resolve()
                    if not p.exists() or project not in p.parents: continue
                    key=f'{p.stat().st_mtime_ns}:{p.stat().st_size}'
                    if report.get(stage+'_checked_key')==key: continue
                    out,provider_size,black=_mf071_normalize_result(p,master)
                    files[stage]=_mf071_rel(project,out)
                    report.update({stage+'_checked_key':f'{out.stat().st_mtime_ns}:{out.stat().st_size}',stage+'_provider_size':list(provider_size),stage+'_final_size':list(master),stage+'_border_black_pixels':black,stage+'_resolution_recovered':provider_size!=master})
                    if black>max(100,int(master[0]*master[1]*0.001)):
                        state.setdefault('statuses',{})[stage]='error'
                        state['task_state']={'stage':stage,'status':'error','progress':100,'message':'Контроль качества: outpaint не выполнен — в результате остались чёрные области. Результат не принят.','quality_error':'border_connected_black_remaining','updated_at':_mf_now() if '_mf_now' in globals() else ''}
                    changed=True
                if changed:
                    state['active_files']=files
                    state_file.write_text(_mf071_json.dumps(state,ensure_ascii=False,indent=2),'utf-8')
        except Exception:
            pass
        _mf071_time.sleep(2)


if not globals().get('_mf071_quality_thread_started'):
    _mf071_quality_thread_started=True
    _mf071_threading.Thread(target=_mf071_quality_pass,name='marins-quality-gate',daemon=True).start()

# Make the outpaint requirement impossible to miss in the image prompt.
_mf071_prev_prompt = globals().get('_mf_prompt')
def _mf_prompt(project: _mf071_Path, comment: str) -> str:
    base = _mf071_prev_prompt(project, comment) if _mf071_prev_prompt else str(comment or '')
    return base.rstrip() + '''\n\nMASTER CANVAS — NON-NEGOTIABLE\n- The output canvas must have exactly the same width, height, aspect ratio and framing as the original uploaded source.\n- Never crop, letterbox, pillarbox, shrink or change the canvas.\n- Transparent regions and every border-connected black region are OUTPAINT MASKS, not design content.\n- Replace 100% of those masked regions with continuous photorealistic surroundings matching the scene, perspective, lens, weather, light and depth.\n- No black wedges, black borders, transparency, empty pixels, mirrored filler, repeated texture or solid-color fill may remain.\n- Preserve all approved opaque architecture pixels and fine detail.\n'''
'''
main_path.write_text(main, "utf-8")

js = app_js.read_text("utf-8")
if "// v0.7.1 original 1:1 quality viewer" not in js:
    js += r'''

// v0.7.1 original 1:1 quality viewer
(function(){
  function project(){return window.currentProject||window.current||null}
  function assetFor(img){
    const p=project(), src=decodeURIComponent(img.currentSrc||img.src||'');
    if(!p) return {url:src,file:''};
    const files=p.active_files||{};
    const hit=Object.entries(files).find(([k,v])=>v&&src.includes(String(v).split('/').pop()));
    const file=hit?hit[1]:'';
    return {file,url:file?`/api/projects/${p.id}/assets/original?file=${encodeURIComponent(file)}`:src,stage:hit?hit[0]:'image'};
  }
  function ensure(){
    let modal=document.getElementById('mf-quality-viewer'); if(modal)return modal;
    modal=document.createElement('div');modal.id='mf-quality-viewer';modal.className='mf-quality-viewer';
    modal.innerHTML='<div class="mf-qv-bar"><strong id="mf-qv-title">Изображение 1:1</strong><span id="mf-qv-meta"></span><button id="mf-qv-100">100%</button><button id="mf-qv-fit">Вписать</button><a id="mf-qv-open" target="_blank" rel="noopener">Открыть файл</a><button id="mf-qv-close">Закрыть</button></div><div class="mf-qv-canvas"><img id="mf-qv-image" alt="Original quality preview"></div>';
    document.body.appendChild(modal);
    modal.querySelector('#mf-qv-close').onclick=()=>modal.classList.remove('is-open');
    modal.addEventListener('click',e=>{if(e.target===modal)modal.classList.remove('is-open')});
    modal.querySelector('#mf-qv-100').onclick=()=>modal.querySelector('img').classList.remove('is-fit');
    modal.querySelector('#mf-qv-fit').onclick=()=>modal.querySelector('img').classList.add('is-fit');
    return modal;
  }
  async function openViewer(img){
    const modal=ensure(), a=assetFor(img), view=modal.querySelector('#mf-qv-image');
    view.classList.remove('is-fit'); view.src=a.url; modal.querySelector('#mf-qv-open').href=a.url;
    modal.querySelector('#mf-qv-title').textContent=(a.stage||'image').toUpperCase()+' · ORIGINAL 1:1';
    modal.querySelector('#mf-qv-meta').textContent='загрузка параметров…'; modal.classList.add('is-open');
    if(a.file&&project()) try{const r=await fetch(`/api/projects/${project().id}/assets/info?file=${encodeURIComponent(a.file)}`);const m=await r.json();modal.querySelector('#mf-qv-meta').textContent=`${m.width}×${m.height} · ${(m.bytes/1048576).toFixed(2)} MB · ${m.megapixels} MP`}catch(_){modal.querySelector('#mf-qv-meta').textContent='параметры недоступны'}
  }
  document.addEventListener('click',e=>{const img=e.target.closest('img');if(!img||e.target.closest('#mf-quality-viewer'))return;e.preventDefault();e.stopImmediatePropagation();openViewer(img)},true);
  const obs=new MutationObserver(()=>document.querySelectorAll('img:not([data-qv])').forEach(img=>{img.dataset.qv='1';img.title='Открыть оригинал 1:1 с параметрами качества';img.classList.add('mf-quality-click')}));
  obs.observe(document.documentElement,{childList:true,subtree:true});
})();
'''
    app_js.write_text(js,"utf-8")

css=styles_path.read_text("utf-8")
if ".mf-quality-viewer" not in css:
    css += r'''

/* v0.7.1 original 1:1 quality viewer */
.mf-quality-click{cursor:zoom-in}
.mf-quality-viewer{position:fixed;inset:0;z-index:1000;display:none;background:rgba(3,15,25,.94)}
.mf-quality-viewer.is-open{display:flex;flex-direction:column}
.mf-qv-bar{flex:0 0 auto;display:flex;align-items:center;gap:12px;min-height:52px;padding:8px 16px;background:#f4f3ef;color:#003050;border-bottom:1px solid #31526b}
.mf-qv-bar span{margin-right:auto;font-size:12px}.mf-qv-bar button,.mf-qv-bar a{border:1px solid #31526b;background:#fff;color:#003050;padding:7px 10px;text-decoration:none;cursor:pointer}
.mf-qv-canvas{flex:1;overflow:auto;text-align:left;background:#111;padding:0}
.mf-qv-canvas img{display:block;max-width:none;max-height:none;width:auto;height:auto;margin:0}
.mf-qv-canvas img.is-fit{max-width:100%;max-height:calc(100vh - 54px);margin:auto}
'''
    styles_path.write_text(css,"utf-8")

test_path.write_text(r'''from pathlib import Path

def test_v071_assets_present():
    root=Path(__file__).parents[1]
    main=(root/'app/main.py').read_text('utf-8')
    js=(root/'app/web/app.js').read_text('utf-8')
    assert 'strict master-canvas' in main
    assert 'border-connected black region' in main
    assert 'MASTER CANVAS — NON-NEGOTIABLE' in main
    assert 'mf-quality-viewer' in js
    assert 'assets/info' in js
''',"utf-8")

print('Applied Marins Facade v0.7.1 strict canvas, outpaint and quality viewer patch')
