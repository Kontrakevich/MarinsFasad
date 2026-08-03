from __future__ import annotations

import re
import sys
from pathlib import Path

runtime = Path(sys.argv[1])
main_path = runtime / "app/main.py"
index_path = runtime / "app/web/index.html"
styles_path = runtime / "app/web/styles.css"
test_path = runtime / "tests/test_openrouter_hardened.py"

main = main_path.read_text("utf-8")
main = re.sub(
    r'^APP_VERSION = "[^"]+"$',
    'APP_VERSION = "0.6.4"',
    main,
    count=1,
    flags=re.MULTILINE,
)

marker = "# v0.6.4 hardened OpenRouter environment generation"
if marker not in main:
    main += r'''

# v0.6.4 hardened OpenRouter environment generation
import asyncio as _mf_asyncio
import base64 as _mf_base64
import json as _mf_json
import mimetypes as _mf_mimetypes
import os as _mf_os
import re as _mf_re
import urllib.error as _mf_urlerror
import urllib.request as _mf_urlrequest
from datetime import datetime as _mf_datetime, timezone as _mf_timezone
from pathlib import Path as _mf_Path
from fastapi import Request as _mf_Request
from fastapi.responses import JSONResponse as _mf_JSONResponse


def _mf_now() -> str:
    return _mf_datetime.now(_mf_timezone.utc).isoformat()


def _mf_data_root() -> _mf_Path:
    configured = _mf_os.getenv("MARINS_DATA_ROOT", "").strip()
    if configured:
        return _mf_Path(configured).resolve()
    return (ROOT / "data" / "projects").resolve()


def _mf_project(project_id: str) -> tuple[_mf_Path, dict]:
    root = _mf_data_root()
    project = (root / project_id).resolve()
    if root not in project.parents or not project.exists():
        raise RuntimeError("Проект не найден")
    state_path = project / "project.json"
    if not state_path.exists():
        raise RuntimeError("Файл состояния проекта не найден")
    return project, _mf_json.loads(state_path.read_text("utf-8"))


def _mf_state_file(state: dict, key: str) -> str | None:
    return (
        (state.get("active_files") or {}).get(key)
        or (state.get("files") or {}).get(key)
    )


def _mf_skill(project: _mf_Path, stage: str) -> str:
    candidates = [
        project / "skills" / stage / "current.md",
        ROOT / "skills" / "templates" / f"{stage}.md",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.read_text("utf-8")
    return f"# {stage.title()} Skill\n\nPreserve all approved previous-stage constraints."


def _mf_prompt(project: _mf_Path, comment: str) -> str:
    skill = _mf_skill(project, "environment")
    operator = comment.strip() or "No additional operator comment."
    return f"""SYSTEM ROLE
You are the image execution model of Marins Facade Control Center.

TASK
Perform environment cleanup and outpaint from the approved geometry image.

HARD CONSTRAINTS
- Treat every non-transparent source pixel as immutable architectural evidence.
- Preserve the approved building geometry, perspective, framing, proportions, windows, doors, facade rhythm, roofline and materials.
- Fill only transparent or otherwise missing canvas regions with a natural continuation of the photographed environment.
- Remove temporary obstructions only when explicitly requested by the operator or allowed by the Skill.
- Never crop, mirror, clone, reflect or symmetrically repeat image edges.
- Return exactly one photorealistic edited image without captions, watermarks, UI or diagrams.

CURRENT SKILL
----------------
{skill.strip()}
----------------

OPERATOR REQUEST
{operator}
"""


def _mf_data_url(path: _mf_Path) -> str:
    mime = _mf_mimetypes.guess_type(path.name)[0] or "image/png"
    encoded = _mf_base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _mf_extract_image_bytes(payload: object) -> tuple[bytes, str]:
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list) and data:
            item = data[0]
            if isinstance(item, dict):
                raw = item.get("b64_json") or item.get("base64")
                if isinstance(raw, str) and raw:
                    if raw.startswith("data:"):
                        header, raw = raw.split(",", 1)
                        media = header.split(";", 1)[0].split(":", 1)[1]
                    else:
                        media = str(item.get("media_type") or "image/png")
                    return _mf_base64.b64decode(raw), media
                url = item.get("url")
                if isinstance(url, str) and url.startswith(("http://", "https://")):
                    with _mf_urlrequest.urlopen(url, timeout=120) as response:
                        return response.read(), response.headers.get_content_type()

        choices = payload.get("choices")
        if isinstance(choices, list):
            for choice in choices:
                try:
                    message = choice.get("message") or {}
                    images = message.get("images") or []
                    for image in images:
                        image_url = image.get("image_url") or {}
                        url = image_url.get("url") if isinstance(image_url, dict) else image_url
                        if isinstance(url, str) and url.startswith("data:"):
                            header, raw = url.split(",", 1)
                            media = header.split(";", 1)[0].split(":", 1)[1]
                            return _mf_base64.b64decode(raw), media
                except Exception:
                    continue

    raise RuntimeError("OpenRouter ответил без изображения. Проверьте модель, баланс и доступность image endpoint.")


def _mf_openrouter_generate(source: _mf_Path, prompt: str) -> tuple[bytes, str, dict]:
    api_key = _mf_os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY не задан в Codespaces secrets")

    model = _mf_os.getenv(
        "OPENROUTER_IMAGE_MODEL",
        "google/gemini-2.5-flash-image",
    ).strip()

    request_payload = {
        "model": model,
        "prompt": prompt,
        "n": 1,
        "output_format": "png",
        "input_references": [
            {
                "type": "image_url",
                "image_url": {"url": _mf_data_url(source)},
            }
        ],
    }

    request = _mf_urlrequest.Request(
        "https://openrouter.ai/api/v1/images",
        data=_mf_json.dumps(request_payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/Kontrakevich/MarinsFasad",
            "X-Title": "Marins Facade Control Center",
        },
        method="POST",
    )

    try:
        with _mf_urlrequest.urlopen(request, timeout=300) as response:
            body = response.read().decode("utf-8", errors="replace")
            result = _mf_json.loads(body)
    except _mf_urlerror.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = _mf_json.loads(body)
            detail = (
                (parsed.get("error") or {}).get("message")
                if isinstance(parsed.get("error"), dict)
                else parsed.get("error")
            ) or parsed.get("message") or parsed.get("detail") or body
        except Exception:
            detail = body or str(exc)
        raise RuntimeError(f"OpenRouter HTTP {exc.code}: {str(detail)[:1800]}") from exc
    except _mf_urlerror.URLError as exc:
        raise RuntimeError(f"Не удалось подключиться к OpenRouter: {exc.reason}") from exc
    except TimeoutError as exc:
        raise RuntimeError("OpenRouter не ответил за 300 секунд") from exc
    except _mf_json.JSONDecodeError as exc:
        raise RuntimeError("OpenRouter вернул некорректный JSON") from exc

    image_bytes, media_type = _mf_extract_image_bytes(result)
    meta = {
        "model": result.get("model") or model,
        "usage": result.get("usage"),
        "created": result.get("created"),
    }
    return image_bytes, media_type, meta


def _mf_extension(media_type: str, image_bytes: bytes) -> str:
    if image_bytes.startswith(b"\x89PNG"):
        return ".png"
    if image_bytes.startswith(b"\xff\xd8"):
        return ".jpg"
    if media_type == "image/webp":
        return ".webp"
    return ".png"


def _mf_write_diagnostic(project: _mf_Path, payload: dict) -> str:
    folder = project / "diagnostics" / "errors"
    folder.mkdir(parents=True, exist_ok=True)
    filename = f"openrouter_{_mf_datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    path = folder / filename
    path.write_text(_mf_json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")
    return str(path.relative_to(project)).replace("\\", "/")


@app.middleware("http")
async def _mf_harden_environment_generation(request: _mf_Request, call_next):
    match = _mf_re.fullmatch(
        r"/api/projects/([^/]+)/(?:environment/(?:generate|run)|ai/environment)",
        request.url.path,
    )
    if request.method != "POST" or not match:
        return await call_next(request)

    project_id = match.group(1)
    started_at = _mf_now()
    project = None
    model = _mf_os.getenv("OPENROUTER_IMAGE_MODEL", "google/gemini-2.5-flash-image")

    try:
        project, state = _mf_project(project_id)
        form = await request.form()
        comment = str(form.get("operator_comment") or form.get("comment") or "")

        geometry_rel = _mf_state_file(state, "geometry")
        if not geometry_rel:
            raise RuntimeError("Сначала требуется утверждённая геометрия")
        source = (project / geometry_rel).resolve()
        if project not in source.parents or not source.exists():
            raise RuntimeError("Файл утверждённой геометрии не найден")

        prompt = _mf_prompt(project, comment)
        prompt_dir = project / "prompts" / "environment"
        prompt_dir.mkdir(parents=True, exist_ok=True)

        iterations = state.setdefault("iterations", {})
        iteration = int(iterations.get("environment") or 0) + 1
        prompt_rel = f"prompts/environment/prompt_v{iteration:03d}.txt"
        (project / prompt_rel).write_text(prompt, "utf-8")

        image_bytes, media_type, provider_meta = await _mf_asyncio.to_thread(
            _mf_openrouter_generate,
            source,
            prompt,
        )

        extension = _mf_extension(media_type, image_bytes)
        output_rel = f"environment/env_v{iteration:03d}{extension}"
        output = project / output_rel
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(image_bytes)

        iterations["environment"] = iteration
        state.setdefault("active_files", {})["environment"] = output_rel
        state.setdefault("files", {})["environment"] = output_rel
        state.setdefault("statuses", {})["environment"] = "review"
        state["current_stage"] = "environment_review"
        state["stage"] = "environment_review"
        state["updated_at"] = _mf_now()
        state.setdefault("comments", []).append({
            "stage": "environment",
            "type": "ai_generation",
            "text": comment,
            "model": provider_meta.get("model") or model,
            "input_file": geometry_rel,
            "output_file": output_rel,
            "prompt_file": prompt_rel,
            "at": state["updated_at"],
        })
        (project / "project.json").write_text(
            _mf_json.dumps(state, ensure_ascii=False, indent=2),
            "utf-8",
        )

        calls = project / "diagnostics" / "provider_calls"
        calls.mkdir(parents=True, exist_ok=True)
        (calls / f"environment_v{iteration:03d}.json").write_text(
            _mf_json.dumps({
                "started_at": started_at,
                "finished_at": _mf_now(),
                "provider": "openrouter",
                "model": provider_meta.get("model") or model,
                "input_file": geometry_rel,
                "output_file": output_rel,
                "usage": provider_meta.get("usage"),
                "status": "ok",
            }, ensure_ascii=False, indent=2),
            "utf-8",
        )
        return _mf_JSONResponse(state)

    except Exception as exc:
        detail = str(exc).strip() or exc.__class__.__name__
        diagnostic = None
        if project is not None:
            diagnostic = _mf_write_diagnostic(project, {
                "started_at": started_at,
                "failed_at": _mf_now(),
                "stage": "environment",
                "provider": "openrouter",
                "model": model,
                "error_type": exc.__class__.__name__,
                "error": detail,
            })
        return _mf_JSONResponse(
            {
                "detail": detail,
                "stage": "environment",
                "provider": "openrouter",
                "model": model,
                "diagnostic": diagnostic,
            },
            status_code=502,
        )
'''

main_path.write_text(main, "utf-8")

smoke_path = runtime / "tests/test_smoke.py"
if smoke_path.exists():
    smoke = smoke_path.read_text("utf-8")
    smoke = re.sub(
        r"assert response\.json\(\)\['version'\] == '[^']+'",
        "assert response.json()['version'] == '0.6.4'",
        smoke,
        count=1,
    )
    smoke_path.write_text(smoke, "utf-8")

index = index_path.read_text("utf-8")
for old in ("v0.6.3", "V0.6.3", ">0.6.3<"):
    index = index.replace(old, old.replace("0.6.3", "0.6.4"))

ui_marker = "v0.6.4 API error diagnostics"
if ui_marker not in index:
    diagnostics_ui = r'''
<script>
// v0.6.4 API error diagnostics
(() => {
  const originalFetch = window.fetch.bind(window);
  window.__marinsLastApiError = '';

  function readableError(text, status) {
    if (!text) return `Сервер вернул пустой ответ${status ? ` (HTTP ${status})` : ''}.`;
    try {
      const data = JSON.parse(text);
      const detail = data.detail || data.message || data.error?.message || data.error;
      const diagnostic = data.diagnostic ? `\nДиагностика: ${data.diagnostic}` : '';
      return `${detail || text}${diagnostic}`;
    } catch (_) {
      return text;
    }
  }

  window.fetch = async (...args) => {
    const response = await originalFetch(...args);
    if (!response.ok) {
      const text = await response.clone().text();
      window.__marinsLastApiError = readableError(text, response.status);
    }
    return response;
  };

  const modal = document.createElement('div');
  modal.id = 'marins-error-modal';
  modal.className = 'marins-error-modal hidden';
  modal.innerHTML = `
    <div class="marins-error-modal__card" role="alertdialog" aria-modal="true">
      <p class="eyebrow">ОШИБКА ГЕНЕРАЦИИ</p>
      <h3>Nano Banana не вернул результат</h3>
      <pre id="marins-error-modal-text"></pre>
      <button type="button" id="marins-error-modal-close">Закрыть</button>
    </div>`;
  document.body.appendChild(modal);

  const nativeAlert = window.alert.bind(window);
  window.alert = message => {
    const text = String(message || '').trim() || window.__marinsLastApiError || 'Неизвестная ошибка. Подробности записаны в диагностике проекта.';
    if (!modal?.classList) return nativeAlert(text);
    document.getElementById('marins-error-modal-text').textContent = text;
    modal.classList.remove('hidden');
  };

  document.getElementById('marins-error-modal-close').onclick = () => modal.classList.add('hidden');
  modal.addEventListener('click', event => {
    if (event.target === modal) modal.classList.add('hidden');
  });
})();
</script>
'''
    index = index.replace("</body>", diagnostics_ui + "\n</body>")

index_path.write_text(index, "utf-8")

styles = styles_path.read_text("utf-8")
css_marker = "/* v0.6.4 generation error modal */"
if css_marker not in styles:
    styles += r'''

/* v0.6.4 generation error modal */
.marins-error-modal{position:fixed;inset:0;z-index:9999;display:grid;place-items:center;padding:24px;background:rgba(4,16,28,.66)}
.marins-error-modal.hidden{display:none}
.marins-error-modal__card{width:min(680px,100%);max-height:80vh;overflow:auto;background:var(--paper);border:1px solid var(--ink);padding:26px;color:var(--ink);box-shadow:0 24px 80px rgba(0,0,0,.28)}
.marins-error-modal__card h3{margin:8px 0 16px;font-size:26px}
.marins-error-modal__card pre{white-space:pre-wrap;overflow-wrap:anywhere;margin:0 0 18px;padding:14px;border:1px solid var(--line-dark);background:#fff;font:12px/1.55 ui-monospace,SFMono-Regular,Consolas,monospace;color:#7b1e18}
'''
styles_path.write_text(styles, "utf-8")

test_path.write_text(
    '''from pathlib import Path\n\n\ndef test_hardened_openrouter_and_visible_error_diagnostics():\n    root = Path(__file__).resolve().parents[1]\n    main = (root / "app/main.py").read_text("utf-8")\n    index = (root / "app/web/index.html").read_text("utf-8")\n    styles = (root / "app/web/styles.css").read_text("utf-8")\n    assert "v0.6.4 hardened OpenRouter environment generation" in main\n    assert "https://openrouter.ai/api/v1/images" in main\n    assert "input_references" in main\n    assert "OpenRouter HTTP" in main\n    assert "v0.6.4 API error diagnostics" in index\n    assert "marins-error-modal" in styles\n''',
    "utf-8",
)

print("Applied v0.6.4 hardened OpenRouter generation and diagnostics")
