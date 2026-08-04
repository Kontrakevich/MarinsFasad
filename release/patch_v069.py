from __future__ import annotations

import re
import sys
from pathlib import Path

runtime = Path(sys.argv[1])
image_tools = runtime / "app/image_tools.py"
main_path = runtime / "app/main.py"
app_js = runtime / "app/web/app.js"
styles = runtime / "app/web/styles.css"
test_path = runtime / "tests/test_full_resolution_prompt_comments.py"

# Production images must never be downscaled. Preview helpers remain preview-only.
text = image_tools.read_text("utf-8")
old = "        work = im.copy()\n        work.thumbnail((int(max_w), int(max_h)), resample=Image.Resampling.LANCZOS)\n"
new = "        # v0.6.9: production pipeline always works at the EXIF-corrected original resolution.\n        # max_w/max_h remain only for backward-compatible config parsing and UI previews.\n        work = im.copy()\n"
if old in text:
    text = text.replace(old, new, 1)
elif new not in text:
    raise SystemExit("prepare_technical_photos resize pattern not found")
text = text.replace(
    "            'resolution': list(work.size),",
    "            'resolution': list(work.size),\n            'production_resolution_policy': 'original_full_resolution',\n            'lossless_intermediate': out.suffix.lower() == '.png',",
    1,
)
image_tools.write_text(text, "utf-8")

main = main_path.read_text("utf-8")
main = re.sub(r'^APP_VERSION = "[^"]+"$', 'APP_VERSION = "0.6.9"', main, count=1, flags=re.MULTILINE)
marker = "# v0.6.9 full-resolution assets and AI-adapted comments"
if marker not in main:
    main += r'''

# v0.6.9 full-resolution assets and AI-adapted comments
import hashlib as _mf069_hashlib
import json as _mf069_json
import mimetypes as _mf069_mimetypes
import os as _mf069_os
import re as _mf069_re
import urllib.request as _mf069_urllib
from pathlib import Path as _mf069_Path
from PIL import Image as _mf069_Image, ImageOps as _mf069_ImageOps
from fastapi import Request as _mf069_Request
from fastapi.responses import JSONResponse as _mf069_JSONResponse, FileResponse as _mf069_FileResponse


def _mf069_safe_asset(project: _mf069_Path, relative: str) -> _mf069_Path:
    value = str(relative or '').replace('\\', '/').lstrip('/')
    if value.startswith('files/'):
        value = value[6:]
    path = (project / value).resolve()
    if path != project and project not in path.parents:
        raise ValueError('Unsafe asset path')
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(value)
    return path


def _mf069_asset_meta(project: _mf069_Path, relative: str) -> dict:
    path = _mf069_safe_asset(project, relative)
    payload = {
        'file': str(path.relative_to(project)).replace('\\', '/'),
        'bytes': path.stat().st_size,
        'sha256': _mf069_hashlib.sha256(path.read_bytes()).hexdigest(),
        'mime': _mf069_mimetypes.guess_type(path.name)[0] or 'application/octet-stream',
        'original_url': f'/api/projects/{project.name}/assets/original?file=' + str(path.relative_to(project)).replace('\\', '/'),
    }
    try:
        with _mf069_Image.open(path) as im:
            oriented = _mf069_ImageOps.exif_transpose(im)
            payload.update({'width': oriented.width, 'height': oriented.height, 'megapixels': round(oriented.width * oriented.height / 1_000_000, 3)})
    except Exception:
        pass
    return payload


def _mf069_local_instruction(comment: str, stage: str) -> str:
    clean = ' '.join(str(comment or '').split()).strip()
    return (
        f'For the {stage.upper()} stage, apply this operator requirement as a hard visual constraint: {clean}. '
        'Preserve all previously approved pixels, geometry, camera, crop, proportions, texture detail and full source resolution. '
        'Do not summarize or omit any part of the requirement.'
    )


def _mf069_ai_adapt_comment(comment: str, stage: str) -> dict:
    clean = ' '.join(str(comment or '').split()).strip()
    if not clean:
        return {'instruction': '', 'provider': 'none', 'model': None}
    api_key = _mf069_os.getenv('OPENROUTER_API_KEY', '').strip()
    model = _mf069_os.getenv('OPENROUTER_TEXT_MODEL', 'moonshotai/kimi-k2.5')
    if not api_key:
        return {'instruction': _mf069_local_instruction(clean, stage), 'provider': 'deterministic-fallback', 'model': None}
    system = (
        'You are a senior architectural image prompt compiler. Convert the operator comment into one precise imperative '
        'instruction for an image-generation prompt. Preserve every concrete requirement. Never reduce resolution, crop, '
        'reframe or alter approved geometry. Return only the instruction, no headings or explanation.'
    )
    body = _mf069_json.dumps({'model': model, 'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': f'Stage: {stage}\nComment: {clean}'}], 'temperature': 0.1}).encode('utf-8')
    req = _mf069_urllib.Request('https://openrouter.ai/api/v1/chat/completions', data=body, method='POST', headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json', 'HTTP-Referer': 'https://github.com/Kontrakevich/MarinsFasad', 'X-Title': 'Marins Facade Control Center'})
    try:
        with _mf069_urllib.urlopen(req, timeout=45) as response:
            data = _mf069_json.loads(response.read().decode('utf-8'))
        instruction = str(data['choices'][0]['message']['content']).strip()
        return {'instruction': instruction or _mf069_local_instruction(clean, stage), 'provider': 'openrouter', 'model': model}
    except Exception as exc:
        return {'instruction': _mf069_local_instruction(clean, stage), 'provider': 'deterministic-fallback', 'model': model, 'error': str(exc)}


def _mf069_collect_prompt_comments(state: dict, stage: str) -> list[str]:
    output = []
    for item in state.get('comments') or []:
        if not isinstance(item, dict):
            continue
        item_stage = str(item.get('stage') or '').lower()
        if item_stage not in ('', stage):
            continue
        value = str(item.get('adapted_prompt_instruction') or item.get('text') or item.get('comment') or '').strip()
        if value and value not in output:
            output.append(value)
    for item in ((state.get('runtime_feedback') or {}).get(stage) or []):
        if isinstance(item, dict):
            value = str(item.get('adapted_prompt_instruction') or item.get('text') or '').strip()
            if value and value not in output:
                output.append(value)
    return output


_mf069_previous_prompt = globals().get('_mf_prompt')
def _mf_prompt(project: _mf069_Path, comment: str) -> str:
    base = _mf069_previous_prompt(project, comment) if _mf069_previous_prompt else str(comment or '')
    try:
        state = _mf069_json.loads((project / 'project.json').read_text('utf-8'))
        instructions = _mf069_collect_prompt_comments(state, 'environment')
    except Exception:
        instructions = []
    block = '\n'.join(f'{i}. {value}' for i, value in enumerate(instructions, 1)) or 'No stored operator comments.'
    return base.rstrip() + '\n\nALL OPERATOR COMMENTS — MANDATORY HARD CONSTRAINTS\n' + block + '\n\nFULL-RESOLUTION DELIVERY RULE\nReturn the result at the maximum available/original source dimensions. Never create a preview-sized production output. Preserve fine material texture and edge detail; use lossless intermediates whenever supported.\n'


@app.middleware('http')
async def _mf069_quality_and_comment_routes(request: _mf069_Request, call_next):
    path = request.url.path
    original_match = _mf069_re.fullmatch(r'/api/projects/([^/]+)/assets/original', path)
    if request.method == 'GET' and original_match:
        try:
            project, state = _mf_project(original_match.group(1))
            asset = _mf069_safe_asset(project, request.query_params.get('file') or '')
            return _mf069_FileResponse(asset, media_type=_mf069_mimetypes.guess_type(asset.name)[0] or 'application/octet-stream', filename=asset.name, headers={'Cache-Control': 'no-transform, public, max-age=31536000, immutable', 'X-Marins-Resolution-Policy': 'original-full-resolution'})
        except Exception as exc:
            return _mf069_JSONResponse({'detail': str(exc)}, status_code=404)

    info_match = _mf069_re.fullmatch(r'/api/projects/([^/]+)/assets/info', path)
    if request.method == 'GET' and info_match:
        try:
            project, state = _mf_project(info_match.group(1))
            return _mf069_JSONResponse(_mf069_asset_meta(project, request.query_params.get('file') or ''))
        except Exception as exc:
            return _mf069_JSONResponse({'detail': str(exc)}, status_code=404)

    revise_match = _mf069_re.fullmatch(r'/api/projects/([^/]+)/(geometry|environment|branding)/(?:revise|revision)', path)
    if request.method == 'POST' and revise_match:
        project_id, stage = revise_match.group(1), revise_match.group(2)
        try:
            content_type = (request.headers.get('content-type') or '').lower()
            if 'application/json' in content_type:
                payload = await request.json()
                comment = str(payload.get('comment') or payload.get('operator_comment') or payload.get('notes') or '').strip()
            else:
                form = await request.form()
                comment = str(form.get('comment') or form.get('operator_comment') or form.get('notes') or '').strip()
        except Exception:
            comment = ''
        if not comment:
            return _mf069_JSONResponse({'detail': 'Комментарий к доработке обязателен.'}, status_code=422)
        try:
            project, state = _mf_project(project_id)
            adapted = _mf069_ai_adapt_comment(comment, stage)
            state = _mf065_read(project) if '_mf065_read' in globals() else state
            feedback = state.setdefault('runtime_feedback', {}).setdefault(stage, [])
            entry = {'id': f'{stage}_feedback_{len(feedback)+1:03d}', 'stage': stage, 'text': comment, 'adapted_prompt_instruction': adapted['instruction'], 'prompt_adapter_provider': adapted.get('provider'), 'prompt_adapter_model': adapted.get('model'), 'status': 'pending', 'created_at': _mf_now() if '_mf_now' in globals() else ''}
            if adapted.get('error'):
                entry['prompt_adapter_error'] = adapted['error']
            feedback.append(entry)
            state.setdefault('comments', []).append({'stage': stage, 'type': 'revision', 'text': comment, 'adapted_prompt_instruction': adapted['instruction'], 'feedback_id': entry['id'], 'at': entry['created_at']})
            prompts = project / 'prompts' / stage
            prompts.mkdir(parents=True, exist_ok=True)
            prompt_file = prompts / f'comment_{len(feedback):03d}_adapted.txt'
            prompt_file.write_text(adapted['instruction'] + '\n', 'utf-8')
            entry['adapted_prompt_file'] = str(prompt_file.relative_to(project)).replace('\\', '/')
            state.setdefault('statuses', {})[stage] = 'ready'
            state['current_stage'] = f'{stage}_ready'
            state['stage'] = f'{stage}_ready'
            state['task_state'] = {'stage': stage, 'status': 'idle', 'message': 'Комментарий обработан нейросетью и добавлен в финальный prompt.', 'progress': 0, 'updated_at': entry['created_at'], 'finished_at': entry['created_at'], 'feedback_id': entry['id'], 'prompt_file': entry['adapted_prompt_file']}
            if '_mf065_write' in globals():
                _mf065_write(project, state)
            else:
                (project / 'project.json').write_text(_mf069_json.dumps(state, ensure_ascii=False, indent=2), 'utf-8')
            return _mf069_JSONResponse(state)
        except Exception as exc:
            return _mf069_JSONResponse({'detail': str(exc)}, status_code=500)

    response = await call_next(request)
    response.headers['X-Marins-Resolution-Policy'] = 'original-full-resolution'
    response.headers['X-Marins-Production-Image-Transform'] = 'no-downscale'
    return response
'''
main_path.write_text(main, "utf-8")

js = app_js.read_text("utf-8")
if "// v0.6.9 original-size image viewer" not in js:
    js += r'''

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
'''
    app_js.write_text(js, "utf-8")

css = styles.read_text("utf-8")
if ".mf-original-image" not in css:
    styles.write_text(css + "\n/* v0.6.9 */\n.mf-original-image{cursor:zoom-in}\n", "utf-8")

test_path.write_text(r'''from pathlib import Path


def test_production_prepare_has_no_thumbnail():
    text = (Path(__file__).parents[1] / 'app/image_tools.py').read_text('utf-8')
    section = text.split('def prepare_technical_photos', 1)[1].split('def make_preview', 1)[0]
    assert '.thumbnail(' not in section
    assert "production_resolution_policy': 'original_full_resolution'" in section


def test_full_resolution_routes_and_comment_adapter_exist():
    text = (Path(__file__).parents[1] / 'app/main.py').read_text('utf-8')
    assert '/assets/original' in text
    assert 'adapted_prompt_instruction' in text
    assert 'ALL OPERATOR COMMENTS' in text
    assert 'original-full-resolution' in text
''', "utf-8")

print("Applied Marins Facade v0.6.9 full-resolution and AI-comment patch")
