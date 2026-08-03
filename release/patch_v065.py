from __future__ import annotations

import re
import sys
from pathlib import Path

runtime = Path(sys.argv[1])
main_path = runtime / "app/main.py"
index_path = runtime / "app/web/index.html"
styles_path = runtime / "app/web/styles.css"
test_path = runtime / "tests/test_task_status_async.py"

main = main_path.read_text("utf-8")
main = re.sub(
    r'^APP_VERSION = "[^"]+"$',
    'APP_VERSION = "0.6.5"',
    main,
    count=1,
    flags=re.MULTILINE,
)

marker = "# v0.6.5 asynchronous provider tasks and persistent task state"
if marker not in main:
    main += r'''

# v0.6.5 asynchronous provider tasks and persistent task state
import threading as _mf065_threading
import time as _mf065_time
import uuid as _mf065_uuid
from fastapi import Request as _mf065_Request
from fastapi.responses import JSONResponse as _mf065_JSONResponse

_mf065_project_locks: dict[str, _mf065_threading.RLock] = {}
_mf065_project_locks_guard = _mf065_threading.Lock()
_mf065_job_stops: dict[str, _mf065_threading.Event] = {}


def _mf065_lock(project_id: str) -> _mf065_threading.RLock:
    with _mf065_project_locks_guard:
        return _mf065_project_locks.setdefault(project_id, _mf065_threading.RLock())


def _mf065_read(project: _mf_Path) -> dict:
    return _mf_json.loads((project / "project.json").read_text("utf-8"))


def _mf065_write(project: _mf_Path, state: dict) -> None:
    state["updated_at"] = _mf_now()
    temporary = project / "project.json.tmp"
    temporary.write_text(_mf_json.dumps(state, ensure_ascii=False, indent=2), "utf-8")
    temporary.replace(project / "project.json")


def _mf065_task(
    state: dict,
    *,
    job_id: str,
    stage: str,
    status: str,
    message: str,
    progress: int,
    started_at: str | None = None,
    diagnostic: str | None = None,
    result_file: str | None = None,
    error: str | None = None,
) -> dict:
    now_value = _mf_now()
    task = state.setdefault("task_state", {})
    task.update({
        "job_id": job_id,
        "stage": stage,
        "status": status,
        "message": message,
        "progress": max(0, min(100, int(progress))),
        "started_at": started_at or task.get("started_at") or now_value,
        "updated_at": now_value,
        "finished_at": now_value if status in {"review", "approved", "failed", "timeout"} else None,
        "diagnostic": diagnostic,
        "result_file": result_file,
        "error": error,
    })
    return task


def _mf065_heartbeat(project_id: str, project: _mf_Path, job_id: str, stop: _mf065_threading.Event) -> None:
    started = _mf065_time.monotonic()
    while not stop.wait(4.0):
        with _mf065_lock(project_id):
            try:
                state = _mf065_read(project)
            except Exception:
                return
            task = state.get("task_state") or {}
            if task.get("job_id") != job_id or task.get("status") != "running":
                return
            elapsed = int(_mf065_time.monotonic() - started)
            current = int(task.get("progress") or 28)
            progress = min(90, current + (2 if elapsed < 90 else 1))
            if elapsed < 20:
                message = "OpenRouter принял запрос. Nano Banana подготавливает генерацию."
            elif elapsed < 90:
                message = "Nano Banana выполняет outpaint и очистку окружения."
            else:
                message = "Генерация идёт дольше обычного. Сервер продолжает ждать результат провайдера."
            _mf065_task(
                state,
                job_id=job_id,
                stage="environment",
                status="running",
                message=message,
                progress=progress,
            )
            state["task_state"]["elapsed_seconds"] = elapsed
            _mf065_write(project, state)


def _mf065_environment_worker(
    project_id: str,
    job_id: str,
    comment: str,
    started_at: str,
) -> None:
    project, _ = _mf_project(project_id)
    stop = _mf065_job_stops[job_id]
    heartbeat = _mf065_threading.Thread(
        target=_mf065_heartbeat,
        args=(project_id, project, job_id, stop),
        daemon=True,
        name=f"marins-heartbeat-{job_id}",
    )
    heartbeat.start()

    try:
        with _mf065_lock(project_id):
            state = _mf065_read(project)
            task = state.get("task_state") or {}
            if task.get("job_id") != job_id:
                return
            geometry_rel = _mf_state_file(state, "geometry")
            if not geometry_rel:
                raise RuntimeError("Сначала требуется утверждённая геометрия")
            source = (project / geometry_rel).resolve()
            if project not in source.parents or not source.exists():
                raise RuntimeError("Файл утверждённой геометрии не найден")
            prompt = _mf_prompt(project, comment)
            iterations = state.setdefault("iterations", {})
            iteration = int(iterations.get("environment") or 0) + 1
            prompt_rel = f"prompts/environment/prompt_v{iteration:03d}.txt"
            prompt_path = project / prompt_rel
            prompt_path.parent.mkdir(parents=True, exist_ok=True)
            prompt_path.write_text(prompt, "utf-8")
            _mf065_task(
                state,
                job_id=job_id,
                stage="environment",
                status="running",
                message="Запрос передан в Nano Banana через OpenRouter.",
                progress=25,
                started_at=started_at,
            )
            state["task_state"]["prompt_file"] = prompt_rel
            _mf065_write(project, state)

        image_bytes, media_type, provider_meta = _mf_openrouter_generate(source, prompt)
        extension = _mf_extension(media_type, image_bytes)
        output_rel = f"environment/env_v{iteration:03d}{extension}"
        output = project / output_rel
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(image_bytes)

        with _mf065_lock(project_id):
            state = _mf065_read(project)
            task = state.get("task_state") or {}
            if task.get("job_id") != job_id:
                return
            state.setdefault("iterations", {})["environment"] = iteration
            state.setdefault("active_files", {})["environment"] = output_rel
            state.setdefault("files", {})["environment"] = output_rel
            state.setdefault("statuses", {})["environment"] = "review"
            state["current_stage"] = "environment_review"
            state["stage"] = "environment_review"
            state.setdefault("comments", []).append({
                "stage": "environment",
                "type": "ai_generation",
                "text": comment,
                "model": provider_meta.get("model") or _mf_os.getenv("OPENROUTER_IMAGE_MODEL", "google/gemini-2.5-flash-image"),
                "input_file": geometry_rel,
                "output_file": output_rel,
                "prompt_file": prompt_rel,
                "job_id": job_id,
                "at": _mf_now(),
            })
            _mf065_task(
                state,
                job_id=job_id,
                stage="environment",
                status="review",
                message="Результат получен. Требуется визуальная проверка окружения.",
                progress=100,
                started_at=started_at,
                result_file=output_rel,
            )
            _mf065_write(project, state)

        calls = project / "diagnostics" / "provider_calls"
        calls.mkdir(parents=True, exist_ok=True)
        (calls / f"environment_v{iteration:03d}.json").write_text(
            _mf_json.dumps({
                "job_id": job_id,
                "started_at": started_at,
                "finished_at": _mf_now(),
                "provider": "openrouter",
                "model": provider_meta.get("model") or _mf_os.getenv("OPENROUTER_IMAGE_MODEL", "google/gemini-2.5-flash-image"),
                "input_file": geometry_rel,
                "output_file": output_rel,
                "usage": provider_meta.get("usage"),
                "status": "ok",
            }, ensure_ascii=False, indent=2),
            "utf-8",
        )

    except Exception as exc:
        detail = str(exc).strip() or exc.__class__.__name__
        diagnostic = _mf_write_diagnostic(project, {
            "job_id": job_id,
            "started_at": started_at,
            "failed_at": _mf_now(),
            "stage": "environment",
            "provider": "openrouter",
            "model": _mf_os.getenv("OPENROUTER_IMAGE_MODEL", "google/gemini-2.5-flash-image"),
            "error_type": exc.__class__.__name__,
            "error": detail,
        })
        timeout = any(token in detail.lower() for token in ("504", "timeout", "timed out", "gateway time-out"))
        status = "timeout" if timeout else "failed"
        message = (
            "Провайдер не ответил в установленное время. Запуск завершён тайм-аутом."
            if timeout
            else detail
        )
        with _mf065_lock(project_id):
            state = _mf065_read(project)
            _mf065_task(
                state,
                job_id=job_id,
                stage="environment",
                status=status,
                message=message,
                progress=100,
                started_at=started_at,
                diagnostic=diagnostic,
                error=detail,
            )
            _mf065_write(project, state)
    finally:
        stop.set()
        _mf065_job_stops.pop(job_id, None)


@app.middleware("http")
async def _mf065_async_generation(request: _mf065_Request, call_next):
    match = _mf_re.fullmatch(
        r"/api/projects/([^/]+)/(?:environment/(?:generate|run)|ai/environment)",
        request.url.path,
    )
    if request.method != "POST" or not match:
        return await call_next(request)

    project_id = match.group(1)
    try:
        project, state = _mf_project(project_id)
        form = await request.form()
        comment = str(form.get("operator_comment") or form.get("comment") or "")
        existing = state.get("task_state") or {}
        if existing.get("status") == "running":
            return _mf065_JSONResponse(state, status_code=202)

        job_id = _mf065_uuid.uuid4().hex[:12]
        started_at = _mf_now()
        _mf065_task(
            state,
            job_id=job_id,
            stage="environment",
            status="running",
            message="Задача поставлена в очередь и передаётся в Nano Banana.",
            progress=5,
            started_at=started_at,
        )
        state["current_stage"] = "environment_processing"
        state["stage"] = "environment_processing"
        state.setdefault("statuses", {})["environment"] = "processing"
        with _mf065_lock(project_id):
            _mf065_write(project, state)

        stop = _mf065_threading.Event()
        _mf065_job_stops[job_id] = stop
        worker = _mf065_threading.Thread(
            target=_mf065_environment_worker,
            args=(project_id, job_id, comment, started_at),
            daemon=True,
            name=f"marins-environment-{job_id}",
        )
        worker.start()
        return _mf065_JSONResponse(state, status_code=202)
    except Exception as exc:
        return _mf065_JSONResponse(
            {
                "detail": str(exc).strip() or exc.__class__.__name__,
                "stage": "environment",
                "status": "failed",
            },
            status_code=409,
        )
'''

main_path.write_text(main, "utf-8")

smoke_path = runtime / "tests/test_smoke.py"
if smoke_path.exists():
    smoke = smoke_path.read_text("utf-8")
    smoke = re.sub(
        r"assert response\.json\(\)\['version'\] == '[^']+'",
        "assert response.json()['version'] == '0.6.5'",
        smoke,
        count=1,
    )
    smoke_path.write_text(smoke, "utf-8")

index = index_path.read_text("utf-8")
index = index.replace("v0.6.4", "v0.6.5")
index = index.replace("V0.6.4", "V0.6.5")
index = index.replace(">0.6.4<", ">0.6.5<")

ui_marker = "v0.6.5 task status monitor"
if ui_marker not in index:
    task_ui = r'''
<script>
// v0.6.5 task status monitor
(() => {
  const statusLabels = {
    idle: 'Ожидание',
    running: 'Выполняется',
    review: 'Нужна проверка',
    approved: 'Подтверждено',
    failed: 'Ошибка',
    timeout: 'Тайм-аут'
  };
  const stageLabels = {
    geometry: 'Геометрия',
    environment: 'Окружение',
    branding: 'Вывеска'
  };
  let trackedProjectId = null;
  let pollTimer = null;
  let lastTask = null;
  const wrappedFetch = window.fetch.bind(window);

  function ensureUi() {
    if (!document.getElementById('task-status-header')) {
      const title = document.getElementById('project-title');
      const host = title?.parentElement || document.querySelector('#workspace header') || document.querySelector('#workspace');
      if (host) {
        const header = document.createElement('div');
        header.id = 'task-status-header';
        header.className = 'task-status-header is-idle';
        header.innerHTML = `
          <span class="task-status-header__kicker">ТЕКУЩАЯ ЗАДАЧА</span>
          <div class="task-status-header__row">
            <strong id="task-status-header-title">Нет активной задачи</strong>
            <span id="task-status-header-pill" class="task-status-pill is-idle">ОЖИДАНИЕ</span>
          </div>
          <div id="task-status-header-message" class="task-status-header__message">Система готова к запуску.</div>
          <div class="task-status-progress"><span id="task-status-header-progress"></span></div>
          <div id="task-status-header-meta" class="task-status-header__meta"></div>`;
        host.appendChild(header);
      }
    }

    if (!document.getElementById('task-status-stage')) {
      const runButton = document.getElementById('run-environment') ||
        [...document.querySelectorAll('button')].find(button => /nano banana/i.test(button.textContent || ''));
      const host = runButton?.parentElement;
      if (host) {
        const panel = document.createElement('section');
        panel.id = 'task-status-stage';
        panel.className = 'task-status-stage is-idle';
        panel.innerHTML = `
          <div class="task-status-stage__top">
            <span class="task-status-stage__kicker">СОСТОЯНИЕ ЗАДАЧИ</span>
            <span id="task-status-stage-pill" class="task-status-pill is-idle">ОЖИДАНИЕ</span>
          </div>
          <strong id="task-status-stage-title">Запуск не выполняется</strong>
          <div id="task-status-stage-message">Нажмите «Запустить Nano Banana» после проверки prompt.</div>
          <div class="task-status-progress"><span id="task-status-stage-progress"></span></div>
          <div id="task-status-stage-meta" class="task-status-stage__meta"></div>`;
        host.insertAdjacentElement('afterend', panel);
      }
    }
  }

  function elapsed(task) {
    if (!task?.started_at) return '';
    const end = task.finished_at ? new Date(task.finished_at).getTime() : Date.now();
    const seconds = Math.max(0, Math.floor((end - new Date(task.started_at).getTime()) / 1000));
    const minutes = Math.floor(seconds / 60);
    const rest = seconds % 60;
    return `${minutes}:${String(rest).padStart(2, '0')}`;
  }

  function renderTask(task) {
    ensureUi();
    lastTask = task || null;
    const status = task?.status || 'idle';
    const stage = task?.stage || null;
    const progress = Number.isFinite(Number(task?.progress)) ? Number(task.progress) : 0;
    const title = stage ? `${stageLabels[stage] || stage} · ${statusLabels[status] || status}` : 'Нет активной задачи';
    const message = task?.message || 'Система готова к запуску.';
    const metaParts = [];
    if (task?.job_id) metaParts.push(`ID: ${task.job_id}`);
    if (task?.started_at) metaParts.push(`Время: ${elapsed(task)}`);
    if (task?.diagnostic) metaParts.push(`Диагностика: ${task.diagnostic}`);
    const meta = metaParts.join(' · ');

    for (const id of ['task-status-header', 'task-status-stage']) {
      const element = document.getElementById(id);
      if (element) element.className = `${id} is-${status}`;
    }
    for (const id of ['task-status-header-pill', 'task-status-stage-pill']) {
      const element = document.getElementById(id);
      if (element) {
        element.className = `task-status-pill is-${status}`;
        element.textContent = statusLabels[status] || status;
      }
    }
    for (const id of ['task-status-header-title', 'task-status-stage-title']) {
      const element = document.getElementById(id);
      if (element) element.textContent = title;
    }
    for (const id of ['task-status-header-message', 'task-status-stage-message']) {
      const element = document.getElementById(id);
      if (element) element.textContent = message;
    }
    for (const id of ['task-status-header-meta', 'task-status-stage-meta']) {
      const element = document.getElementById(id);
      if (element) element.textContent = meta;
    }
    for (const id of ['task-status-header-progress', 'task-status-stage-progress']) {
      const element = document.getElementById(id);
      if (element) element.style.width = `${Math.max(0, Math.min(100, progress))}%`;
    }
  }

  async function poll() {
    if (!trackedProjectId) return;
    try {
      const response = await wrappedFetch(`/api/projects/${trackedProjectId}?task_poll=${Date.now()}`, { cache: 'no-store' });
      if (!response.ok) return;
      const project = await response.json();
      renderTask(project.task_state);
      const status = project.task_state?.status;
      if (['review', 'approved', 'failed', 'timeout'].includes(status)) {
        stopPolling();
        if (typeof openProject === 'function') {
          await openProject(trackedProjectId);
        } else if (typeof reload === 'function') {
          await reload();
        }
        if (['failed', 'timeout'].includes(status)) {
          alert(`${project.task_state?.message || 'Генерация завершилась ошибкой.'}${project.task_state?.diagnostic ? `\nДиагностика: ${project.task_state.diagnostic}` : ''}`);
        }
      }
    } catch (error) {
      console.warn('Task polling failed', error);
    }
  }

  function startPolling(projectId) {
    trackedProjectId = projectId;
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(poll, 3000);
    poll();
  }

  function stopPolling() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = null;
  }

  window.fetch = async (...args) => {
    const response = await wrappedFetch(...args);
    const url = String(args[0]?.url || args[0] || '');
    const generationMatch = url.match(/\/api\/projects\/([^/]+)\/(?:environment\/(?:generate|run)|ai\/environment)/);
    const projectMatch = url.match(/\/api\/projects\/([^/?]+)(?:\?|$)/);

    if (generationMatch && response.ok) {
      const data = await response.clone().json().catch(() => null);
      renderTask(data?.task_state || {
        stage: 'environment',
        status: 'running',
        message: 'Задача поставлена в очередь.',
        progress: 5,
        started_at: new Date().toISOString()
      });
      startPolling(generationMatch[1]);
    } else if (projectMatch && response.ok) {
      const data = await response.clone().json().catch(() => null);
      if (data?.task_state) {
        trackedProjectId = projectMatch[1];
        renderTask(data.task_state);
        if (data.task_state.status === 'running') startPolling(projectMatch[1]);
      }
    }
    return response;
  };

  setInterval(() => {
    if (lastTask) renderTask(lastTask);
  }, 1000);
  ensureUi();
  window.addEventListener('load', ensureUi);
})();
</script>
'''
    index = index.replace("</body>", task_ui + "\n</body>")

index_path.write_text(index, "utf-8")

styles = styles_path.read_text("utf-8")
css_marker = "/* v0.6.5 task status */"
if css_marker not in styles:
    styles += r'''

/* v0.6.5 task status */
.task-status-header{margin-top:18px;min-width:340px;max-width:560px;border-left:4px solid var(--line-dark);padding:12px 0 12px 16px;display:grid;gap:7px}
.task-status-header__kicker,.task-status-stage__kicker{font-size:9px;letter-spacing:.16em;font-weight:700}
.task-status-header__row,.task-status-stage__top{display:flex;align-items:center;justify-content:space-between;gap:14px}
.task-status-header__message,.task-status-stage #task-status-stage-message{font-size:12px;line-height:1.45}
.task-status-header__meta,.task-status-stage__meta{font:10px/1.4 ui-monospace,SFMono-Regular,Consolas,monospace;opacity:.72;overflow-wrap:anywhere}
.task-status-stage{margin:14px 0;padding:16px;border:1px solid var(--ink);display:grid;gap:10px;background:rgba(255,255,255,.42)}
.task-status-stage strong{font-size:14px}
.task-status-pill{display:inline-flex;align-items:center;justify-content:center;padding:5px 8px;border:1px solid currentColor;font-size:9px;line-height:1;letter-spacing:.1em;text-transform:uppercase;white-space:nowrap}
.task-status-progress{height:4px;background:rgba(0,48,80,.14);overflow:hidden}
.task-status-progress span{display:block;width:0;height:100%;background:var(--ink);transition:width .4s ease}
.task-status-header.is-running,.task-status-stage.is-running{border-color:#008a90}
.task-status-pill.is-running{background:#003050;color:#fff}
.task-status-pill.is-review{background:#dceff0;color:#003050}
.task-status-pill.is-approved{background:#e4efe4;color:#22512c}
.task-status-pill.is-failed,.task-status-pill.is-timeout{background:#f5dfdc;color:#7b1e18}
.task-status-header.is-running .task-status-progress span,.task-status-stage.is-running .task-status-progress span{background:#008a90;animation:task-status-pulse 1.6s ease-in-out infinite}
.task-status-header.is-failed,.task-status-header.is-timeout,.task-status-stage.is-failed,.task-status-stage.is-timeout{border-color:#7b1e18}
@keyframes task-status-pulse{0%,100%{opacity:.55}50%{opacity:1}}
@media(max-width:900px){.task-status-header{min-width:0;max-width:none;width:100%}.task-status-header__row,.task-status-stage__top{align-items:flex-start;flex-direction:column}}
'''
styles_path.write_text(styles, "utf-8")

test_path.write_text(
    '''from pathlib import Path\n\n\ndef test_async_task_state_and_status_ui_are_installed():\n    root = Path(__file__).resolve().parents[1]\n    main = (root / "app/main.py").read_text("utf-8")\n    index = (root / "app/web/index.html").read_text("utf-8")\n    styles = (root / "app/web/styles.css").read_text("utf-8")\n    assert "v0.6.5 asynchronous provider tasks" in main\n    assert "_mf065_environment_worker" in main\n    assert "status_code=202" in main\n    assert '"task_state"' in main\n    assert "v0.6.5 task status monitor" in index\n    assert "task-status-header" in index\n    assert "startPolling" in index\n    assert "v0.6.5 task status" in styles\n''',
    "utf-8",
)

print("Applied v0.6.5 asynchronous task execution and live status UI")
