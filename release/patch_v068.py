from __future__ import annotations

import re
import sys
from pathlib import Path

runtime = Path(sys.argv[1])
main_path = runtime / "app/main.py"
index_path = runtime / "app/web/index.html"
styles_path = runtime / "app/web/styles.css"
test_path = runtime / "tests/test_review_learning_fullscreen.py"

main = main_path.read_text("utf-8")
main = re.sub(
    r'^APP_VERSION = "[^"]+"$',
    'APP_VERSION = "0.6.8"',
    main,
    count=1,
    flags=re.MULTILINE,
)

marker = "# v0.6.8 revision-aware prompts, skill promotion and review workflow"
if marker not in main:
    main += r'''

# v0.6.8 revision-aware prompts, skill promotion and review workflow
import json as _mf068_json
import os as _mf068_os
import re as _mf068_re
import shutil as _mf068_shutil
from datetime import datetime as _mf068_datetime
from pathlib import Path as _mf068_Path
from fastapi import Request as _mf068_Request
from fastapi.responses import JSONResponse as _mf068_JSONResponse


def _mf068_safe_project(project_id: str) -> tuple[_mf068_Path, dict]:
    project, state = _mf_project(project_id)
    return project, state


def _mf068_current_skill(project: _mf068_Path) -> _mf068_Path:
    current = project / "skills" / "environment" / "current.md"
    current.parent.mkdir(parents=True, exist_ok=True)
    if not current.exists():
        template = ROOT / "skills" / "templates" / "environment.md"
        if template.exists():
            current.write_text(template.read_text("utf-8"), "utf-8")
        else:
            current.write_text(
                "# Environment Skill\n\n"
                "## Purpose\nGenerate and clean the surroundings while preserving approved geometry.\n",
                "utf-8",
            )
    return current


def _mf068_feedback_entries(state: dict, pending_only: bool = True) -> list[dict]:
    entries = (
        state.get("runtime_feedback", {})
        .get("environment", [])
    )
    if not isinstance(entries, list):
        return []
    if not pending_only:
        return [entry for entry in entries if isinstance(entry, dict)]
    return [
        entry for entry in entries
        if isinstance(entry, dict) and entry.get("status", "pending") == "pending"
    ]


def _mf068_normalize_rule(comment: str) -> str:
    value = " ".join(str(comment or "").split()).strip(" .;:-")
    if not value:
        return ""
    first = value[0].upper() + value[1:] if len(value) > 1 else value.upper()
    if first[-1] not in ".!?":
        first += "."
    return first


def _mf068_prompt(project: _mf068_Path, operator_comment: str = "") -> str:
    state = _mf068_json.loads((project / "project.json").read_text("utf-8"))
    skill_text = _mf068_current_skill(project).read_text("utf-8")
    pending = _mf068_feedback_entries(state, pending_only=True)
    feedback_lines = []
    for index, entry in enumerate(pending, start=1):
        text = _mf068_normalize_rule(entry.get("text", ""))
        if text:
            feedback_lines.append(f"{index}. {text}")
    feedback_block = "\n".join(feedback_lines) or "No pending revision feedback."
    operator = operator_comment.strip() or "No additional operator comment for this attempt."

    return f"""SYSTEM ROLE
You are the image execution model inside Marins Facade Control Center.

CURRENT STAGE
ENVIRONMENT

PRIMARY TASK
Create a photorealistic environment outpaint and cleanup from the approved geometry image.

IMMUTABLE SOURCE RULES
- Treat every non-transparent source pixel as immutable architectural evidence.
- Preserve approved building geometry, perspective, camera, crop, facade proportions, windows, doors, roofline, materials and signage positions.
- Transparent regions and empty wedges are intentional outpaint masks. Fill them completely and naturally.
- Do not leave transparent holes, black polygons, mirrored fragments, repeated edge patterns or placeholder colors.
- Do not modify opaque geometry pixels when filling missing surroundings.
- Remove temporary obstructions only when required by the Skill, pending revision feedback or operator comment.
- Return exactly one finished photorealistic image without captions, watermarks, UI or diagrams.

CURRENT APPROVED SKILL
----------------
{skill_text.strip()}
----------------

PENDING REVISION FEEDBACK — HARD CONSTRAINTS FOR THIS ATTEMPT
----------------
{feedback_block}
----------------

CURRENT OPERATOR COMMENT
----------------
{operator}
----------------

EXECUTION CHECK BEFORE RETURN
1. Every empty or transparent region is filled with plausible environment.
2. No black or transparent wedges remain.
3. The approved architecture is unchanged.
4. Every pending revision comment is visibly resolved.
"""


# Override the prompt function used by the asynchronous v0.6.5 worker.
def _mf_prompt(project: _mf068_Path, comment: str) -> str:
    return _mf068_prompt(project, comment)


def _mf068_write_candidate(project: _mf068_Path, entry: dict) -> str:
    current = _mf068_current_skill(project)
    revisions = current.parent / "revisions"
    revisions.mkdir(parents=True, exist_ok=True)
    existing = sorted(revisions.glob("candidate_*.md"))
    number = len(existing) + 1
    candidate = revisions / f"candidate_{number:03d}.md"
    rule = _mf068_normalize_rule(entry.get("text", ""))
    candidate.write_text(
        current.read_text("utf-8").rstrip()
        + "\n\n"
        + f"## Candidate revision {number:03d}\n"
        + f"- Feedback ID: {entry.get('id')}\n"
        + f"- Source result: {entry.get('source_result') or 'unknown'}\n"
        + f"- Required correction: {rule}\n"
        + "- Promotion rule: add to current Skill only after a later result is approved.\n",
        "utf-8",
    )
    return str(candidate.relative_to(project)).replace("\\", "/")


def _mf068_latest_prompt(state: dict, project: _mf068_Path) -> tuple[str | None, str]:
    task = state.get("task_state") or {}
    candidates = []
    if task.get("prompt_file"):
        candidates.append(str(task["prompt_file"]))
    for event in reversed(state.get("comments") or []):
        if isinstance(event, dict) and event.get("stage") == "environment" and event.get("prompt_file"):
            candidates.append(str(event["prompt_file"]))
    for relative in candidates:
        path = (project / relative).resolve()
        if project in path.parents and path.exists():
            return relative, path.read_text("utf-8")
    prompt_dir = project / "prompts" / "environment"
    if prompt_dir.exists():
        files = sorted(prompt_dir.glob("*.txt"))
        if files:
            path = files[-1]
            return str(path.relative_to(project)).replace("\\", "/"), path.read_text("utf-8")
    return None, ""


def _mf068_promote_approved_learning(project_id: str) -> dict:
    project, state = _mf068_safe_project(project_id)
    pending = _mf068_feedback_entries(state, pending_only=True)
    prompt_rel, prompt_text = _mf068_latest_prompt(state, project)
    result_rel = _mf_state_file(state, "environment")
    current = _mf068_current_skill(project)
    learning_key = (
        (state.get("task_state") or {}).get("job_id")
        or prompt_rel
        or result_rel
        or _mf_now()
    )
    learning_key = _mf068_re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(learning_key))[:80]

    learning_state = state.setdefault("skill_learning", {}).setdefault("environment", {})
    if learning_state.get("last_learning_key") == learning_key:
        return state

    history = current.parent / "history"
    history.mkdir(parents=True, exist_ok=True)
    history_number = len(list(history.glob("skill_before_*.md"))) + 1
    before = history / f"skill_before_{history_number:03d}.md"
    before.write_text(current.read_text("utf-8"), "utf-8")

    approved_prompt_rel = None
    if prompt_text:
        approved_prompt = history / f"approved_prompt_{history_number:03d}.txt"
        approved_prompt.write_text(prompt_text, "utf-8")
        approved_prompt_rel = str(approved_prompt.relative_to(project)).replace("\\", "/")

    rules = []
    for entry in pending:
        rule = _mf068_normalize_rule(entry.get("text", ""))
        if rule and rule not in rules:
            rules.append(rule)

    learning_lines = [
        "",
        "",
        f"## Validated environment learning {history_number:03d}",
        f"- Approved at: {_mf_now()}",
        f"- Approved result: {result_rel or 'unknown'}",
        f"- Approved prompt: {approved_prompt_rel or prompt_rel or 'not recorded'}",
        "",
        "### Reusable constraints validated by approval",
    ]
    if rules:
        learning_lines.extend(f"- {rule}" for rule in rules)
    else:
        learning_lines.append(
            "- Preserve approved geometry and complete every transparent outpaint area without black wedges."
        )
    learning_lines.extend([
        "",
        "### Prompt pattern that produced the approved result",
        "- Keep immutable geometry rules before editable environment instructions.",
        "- Add unresolved operator feedback as explicit hard constraints.",
        "- End with a visual completion checklist before image return.",
    ])

    current.write_text(current.read_text("utf-8").rstrip() + "\n".join(learning_lines) + "\n", "utf-8")

    promoted_at = _mf_now()
    for entry in _mf068_feedback_entries(state, pending_only=False):
        if entry.get("status", "pending") == "pending":
            entry["status"] = "promoted"
            entry["promoted_at"] = promoted_at
            entry["approved_result"] = result_rel
            entry["approved_prompt"] = approved_prompt_rel or prompt_rel

    learning_state.update({
        "last_learning_key": learning_key,
        "last_promoted_at": promoted_at,
        "last_approved_result": result_rel,
        "last_approved_prompt": approved_prompt_rel or prompt_rel,
        "rules_promoted": len(rules),
        "skill_file": str(current.relative_to(project)).replace("\\", "/"),
    })
    state.setdefault("comments", []).append({
        "stage": "environment",
        "type": "skill_learning_promoted",
        "text": "Approved prompt and successful corrections were analyzed and promoted to the Environment Skill.",
        "rules": rules,
        "prompt_file": approved_prompt_rel or prompt_rel,
        "result_file": result_rel,
        "at": promoted_at,
    })
    task = state.setdefault("task_state", {})
    task.update({
        "stage": "environment",
        "status": "approved",
        "message": "Окружение подтверждено. Удачный prompt и исправления записаны в Environment Skill.",
        "progress": 100,
        "updated_at": promoted_at,
        "finished_at": promoted_at,
    })
    _mf065_write(project, state)
    return state


async def _mf068_read_comment(request: _mf068_Request) -> str:
    content_type = (request.headers.get("content-type") or "").lower()
    if "application/json" in content_type:
        try:
            payload = await request.json()
            return str(payload.get("comment") or payload.get("operator_comment") or "").strip()
        except Exception:
            return ""
    try:
        form = await request.form()
        return str(form.get("comment") or form.get("operator_comment") or "").strip()
    except Exception:
        return ""


@app.middleware("http")
async def _mf068_revision_learning_routes(request: _mf068_Request, call_next):
    path = request.url.path

    prompt_match = _mf068_re.fullmatch(
        r"/api/projects/([^/]+)/(?:environment/prompt|prompt/environment|environment/system-prompt)",
        path,
    )
    if request.method == "GET" and prompt_match:
        project_id = prompt_match.group(1)
        try:
            project, state = _mf068_safe_project(project_id)
            prompt = _mf068_prompt(project, "")
            pending_count = len(_mf068_feedback_entries(state, pending_only=True))
            return _mf068_JSONResponse({
                "stage": "environment",
                "model": _mf068_os.getenv(
                    "OPENROUTER_IMAGE_MODEL",
                    "google/gemini-2.5-flash-image",
                ),
                "prompt": prompt,
                "pending_feedback_count": pending_count,
                "feedback_applied": [
                    entry.get("text") for entry in _mf068_feedback_entries(state, True)
                ],
            })
        except Exception as exc:
            return _mf068_JSONResponse({"detail": str(exc)}, status_code=404)

    revise_match = _mf068_re.fullmatch(
        r"/api/projects/([^/]+)/environment/(?:revise|revision)",
        path,
    )
    if request.method == "POST" and revise_match:
        project_id = revise_match.group(1)
        comment = await _mf068_read_comment(request)
        if not comment:
            return _mf068_JSONResponse(
                {"detail": "Комментарий к доработке обязателен."},
                status_code=422,
            )
        try:
            project, state = _mf068_safe_project(project_id)
            with _mf065_lock(project_id):
                state = _mf065_read(project)
                feedback = state.setdefault("runtime_feedback", {}).setdefault("environment", [])
                number = len(feedback) + 1
                entry = {
                    "id": f"environment_feedback_{number:03d}",
                    "text": comment,
                    "stage": "environment",
                    "status": "pending",
                    "created_at": _mf_now(),
                    "source_result": _mf_state_file(state, "environment"),
                    "source_prompt": _mf068_latest_prompt(state, project)[0],
                }
                feedback.append(entry)
                entry["candidate_skill"] = _mf068_write_candidate(project, entry)

                prompt = _mf068_prompt(project, "")
                prompts = project / "prompts" / "environment"
                prompts.mkdir(parents=True, exist_ok=True)
                revised_prompt = prompts / f"revised_after_feedback_{number:03d}.txt"
                revised_prompt.write_text(prompt, "utf-8")
                entry["revised_prompt"] = str(revised_prompt.relative_to(project)).replace("\\", "/")

                state.setdefault("statuses", {})["environment"] = "ready"
                state["current_stage"] = "environment_ready"
                state["stage"] = "environment_ready"
                state.setdefault("comments", []).append({
                    "stage": "environment",
                    "type": "revision",
                    "text": comment,
                    "feedback_id": entry["id"],
                    "candidate_skill": entry["candidate_skill"],
                    "revised_prompt": entry["revised_prompt"],
                    "at": entry["created_at"],
                })
                state["task_state"] = {
                    "stage": "environment",
                    "status": "idle",
                    "message": "Комментарий учтён. Prompt перестроен для следующей генерации.",
                    "progress": 0,
                    "updated_at": _mf_now(),
                    "finished_at": _mf_now(),
                    "feedback_id": entry["id"],
                    "prompt_file": entry["revised_prompt"],
                }
                _mf065_write(project, state)
            return _mf068_JSONResponse(state)
        except Exception as exc:
            return _mf068_JSONResponse({"detail": str(exc)}, status_code=409)

    approve_match = _mf068_re.fullmatch(
        r"/api/projects/([^/]+)/environment/approve",
        path,
    )
    if request.method == "POST" and approve_match:
        response = await call_next(request)
        if response.status_code >= 400:
            return response
        project_id = approve_match.group(1)
        try:
            with _mf065_lock(project_id):
                state = _mf068_promote_approved_learning(project_id)
            return _mf068_JSONResponse(state)
        except Exception as exc:
            return _mf068_JSONResponse({
                "detail": f"Результат подтверждён, но Skill learning завершился ошибкой: {exc}",
            }, status_code=500)

    return await call_next(request)
'''

main_path.write_text(main, "utf-8")

smoke_path = runtime / "tests/test_smoke.py"
if smoke_path.exists():
    smoke = smoke_path.read_text("utf-8")
    smoke = re.sub(
        r"assert response\.json\(\)\['version'\] == '[^']+'",
        "assert response.json()['version'] == '0.6.8'",
        smoke,
        count=1,
    )
    smoke_path.write_text(smoke, "utf-8")

index = index_path.read_text("utf-8")
index = index.replace("v0.6.7", "v0.6.8")
index = index.replace("V0.6.7", "V0.6.8")
index = index.replace(">0.6.7<", ">0.6.8<")

ui_marker = "v0.6.8 fullscreen review and automatic prompt refresh"
if ui_marker not in index:
    ui_script = r'''
<script>
// v0.6.8 fullscreen review and automatic prompt refresh
(() => {
  const nativeFetch = window.fetch.bind(window);
  let lastProjectId = null;

  function projectIdFromUrl(value) {
    const url = typeof value === 'string' ? value : (value?.url || '');
    const match = url.match(/\/api\/projects\/([^/]+)/);
    return match ? match[1] : null;
  }

  function ensurePromptFeedbackBadge() {
    const prompt = document.getElementById('environment-prompt');
    if (!prompt || document.getElementById('environment-feedback-badge')) return;
    const badge = document.createElement('div');
    badge.id = 'environment-feedback-badge';
    badge.className = 'environment-feedback-badge';
    badge.textContent = 'КОРРЕКТИРОВКИ В PROMPT: 0';
    prompt.parentElement?.insertBefore(badge, prompt);
  }

  async function refreshEnvironmentPrompt(projectId) {
    if (!projectId) return;
    const endpoints = [
      `/api/projects/${projectId}/environment/prompt`,
      `/api/projects/${projectId}/prompt/environment`
    ];
    for (const endpoint of endpoints) {
      try {
        const response = await nativeFetch(endpoint, { cache: 'no-store' });
        if (!response.ok) continue;
        const data = await response.json();
        const field = document.getElementById('environment-prompt');
        if (field && data.prompt) field.value = data.prompt;
        ensurePromptFeedbackBadge();
        const badge = document.getElementById('environment-feedback-badge');
        if (badge) {
          const count = Number(data.pending_feedback_count || 0);
          badge.textContent = `КОРРЕКТИРОВКИ В PROMPT: ${count}`;
          badge.classList.toggle('has-feedback', count > 0);
        }
        return;
      } catch (_) {}
    }
  }

  window.fetch = async (...args) => {
    const projectId = projectIdFromUrl(args[0]);
    if (projectId) lastProjectId = projectId;
    const response = await nativeFetch(...args);
    const url = typeof args[0] === 'string' ? args[0] : (args[0]?.url || '');
    if (response.ok && /\/environment\/(revise|revision)$/.test(url)) {
      setTimeout(() => refreshEnvironmentPrompt(projectId || lastProjectId), 120);
    }
    return response;
  };

  const modal = document.createElement('div');
  modal.id = 'image-review-modal';
  modal.className = 'image-review-modal hidden';
  modal.innerHTML = `
    <div class="image-review-modal__toolbar">
      <div>
        <span class="image-review-modal__kicker">FULLSCREEN REVIEW</span>
        <strong id="image-review-modal-title">AI RESULT</strong>
      </div>
      <div class="image-review-modal__actions">
        <button type="button" id="image-review-fit">ВПИСАТЬ</button>
        <button type="button" id="image-review-actual">100%</button>
        <button type="button" id="image-review-close">ЗАКРЫТЬ ×</button>
      </div>
    </div>
    <div id="image-review-stage" class="image-review-modal__stage is-fit">
      <img id="image-review-full" alt="Fullscreen AI result review">
    </div>`;
  document.body.appendChild(modal);

  const stage = document.getElementById('image-review-stage');
  const fullImage = document.getElementById('image-review-full');

  function openReview(image, title) {
    if (!image?.src) return;
    fullImage.src = image.src;
    document.getElementById('image-review-modal-title').textContent = title || 'AI RESULT';
    stage.classList.add('is-fit');
    stage.classList.remove('is-actual');
    modal.classList.remove('hidden');
    document.body.classList.add('image-review-open');
  }

  function closeReview() {
    modal.classList.add('hidden');
    document.body.classList.remove('image-review-open');
    fullImage.removeAttribute('src');
  }

  document.getElementById('image-review-close').onclick = closeReview;
  document.getElementById('image-review-fit').onclick = () => {
    stage.classList.add('is-fit');
    stage.classList.remove('is-actual');
  };
  document.getElementById('image-review-actual').onclick = () => {
    stage.classList.remove('is-fit');
    stage.classList.add('is-actual');
  };
  modal.addEventListener('click', event => {
    if (event.target === modal) closeReview();
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !modal.classList.contains('hidden')) closeReview();
  });

  function isAiResultImage(image) {
    const src = image.getAttribute('src') || '';
    const containerText = (image.closest('figure, .image-card, .compare-cell, div')?.textContent || '').toUpperCase();
    return /environment|branding|ai[_-]?result/i.test(src) || containerText.includes('AI RESULT');
  }

  function bindReviewImages() {
    document.querySelectorAll('#workspace img, main img').forEach(image => {
      if (image.dataset.fullscreenReviewBound === '1' || !isAiResultImage(image)) return;
      image.dataset.fullscreenReviewBound = '1';
      image.classList.add('fullscreen-review-target');
      image.title = 'Открыть результат на весь экран';
      image.addEventListener('click', () => openReview(image, 'AI RESULT'));

      const parent = image.parentElement;
      if (parent && !parent.querySelector(':scope > .fullscreen-review-button')) {
        parent.classList.add('fullscreen-review-host');
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'fullscreen-review-button';
        button.textContent = 'НА ВЕСЬ ЭКРАН';
        button.onclick = event => {
          event.preventDefault();
          event.stopPropagation();
          openReview(image, 'AI RESULT');
        };
        parent.appendChild(button);
      }
    });
    ensurePromptFeedbackBadge();
  }

  bindReviewImages();
  document.addEventListener('DOMContentLoaded', bindReviewImages, { once: true });
  new MutationObserver(bindReviewImages).observe(document.documentElement, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ['src']
  });
})();
</script>
'''
    index = index.replace("</body>", ui_script + "\n</body>")
index_path.write_text(index, "utf-8")

styles = styles_path.read_text("utf-8")
css_marker = "/* v0.6.8 fullscreen image review and feedback visibility */"
if css_marker not in styles:
    styles += r'''

/* v0.6.8 fullscreen image review and feedback visibility */
.fullscreen-review-host{position:relative!important;overflow:hidden}
.fullscreen-review-target{cursor:zoom-in}
.fullscreen-review-button{
  position:absolute;
  right:12px;
  bottom:12px;
  z-index:3;
  padding:9px 12px;
  border:1px solid rgba(255,255,255,.75);
  background:rgba(8,31,52,.88);
  color:#fff;
  font-size:9px;
  line-height:1;
  letter-spacing:.14em;
  text-transform:uppercase;
  opacity:0;
  transform:translateY(4px);
  transition:opacity .16s ease,transform .16s ease;
}
.fullscreen-review-host:hover>.fullscreen-review-button,
.fullscreen-review-button:focus{opacity:1;transform:none}
.image-review-open{overflow:hidden}
.image-review-modal{
  position:fixed;
  inset:0;
  z-index:12000;
  display:grid;
  grid-template-rows:auto minmax(0,1fr);
  background:#071522;
  color:#fff;
}
.image-review-modal.hidden{display:none}
.image-review-modal__toolbar{
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:20px;
  min-height:68px;
  padding:12px 20px;
  border-bottom:1px solid rgba(255,255,255,.28);
  background:#0b2238;
}
.image-review-modal__kicker{
  display:block;
  margin-bottom:5px;
  color:#a8becf;
  font-size:9px;
  letter-spacing:.18em;
}
.image-review-modal__toolbar strong{font-size:14px;letter-spacing:.1em}
.image-review-modal__actions{display:flex;gap:8px;flex-wrap:wrap}
.image-review-modal__actions button{
  border:1px solid rgba(255,255,255,.45);
  background:transparent;
  color:#fff;
  padding:10px 13px;
  font-size:9px;
  letter-spacing:.12em;
}
.image-review-modal__stage{
  min-width:0;
  min-height:0;
  overflow:auto;
  display:flex;
  align-items:center;
  justify-content:center;
  padding:20px;
  background:
    linear-gradient(45deg,#13283a 25%,transparent 25%),
    linear-gradient(-45deg,#13283a 25%,transparent 25%),
    linear-gradient(45deg,transparent 75%,#13283a 75%),
    linear-gradient(-45deg,transparent 75%,#13283a 75%),
    #0a1b2a;
  background-size:28px 28px;
  background-position:0 0,0 14px,14px -14px,-14px 0;
}
.image-review-modal__stage.is-fit img{
  display:block;
  width:auto;
  height:auto;
  max-width:100%;
  max-height:100%;
  object-fit:contain;
}
.image-review-modal__stage.is-actual{
  align-items:flex-start;
  justify-content:flex-start;
}
.image-review-modal__stage.is-actual img{
  display:block;
  width:auto;
  height:auto;
  max-width:none;
  max-height:none;
}
.environment-feedback-badge{
  display:flex;
  align-items:center;
  justify-content:space-between;
  min-height:30px;
  margin:0 0 8px;
  padding:7px 10px;
  border:1px solid var(--line-dark);
  color:var(--ink-2);
  font-size:9px;
  font-weight:600;
  letter-spacing:.14em;
  text-transform:uppercase;
}
.environment-feedback-badge.has-feedback{
  border-color:var(--ink);
  background:#dcecf2;
  color:var(--ink);
}
@media(max-width:760px){
  .fullscreen-review-button{opacity:1;transform:none}
  .image-review-modal__toolbar{align-items:flex-start;flex-direction:column}
  .image-review-modal__actions{width:100%}
}
'''
styles_path.write_text(styles, "utf-8")

test_path.write_text(
    '''from pathlib import Path\n\n\ndef test_fullscreen_revision_prompt_and_skill_learning_are_installed():\n    root = Path(__file__).resolve().parents[1]\n    main = (root / "app/main.py").read_text("utf-8")\n    index = (root / "app/web/index.html").read_text("utf-8")\n    styles = (root / "app/web/styles.css").read_text("utf-8")\n    assert "v0.6.8 revision-aware prompts" in main\n    assert "PENDING REVISION FEEDBACK" in main\n    assert "candidate_skill" in main\n    assert "skill_learning_promoted" in main\n    assert "approved_prompt_" in main\n    assert "v0.6.8 fullscreen review" in index\n    assert "image-review-modal" in index\n    assert "refreshEnvironmentPrompt" in index\n    assert "v0.6.8 fullscreen image review" in styles\n    assert "fullscreen-review-button" in styles\n''',
    "utf-8",
)

print("Applied v0.6.8 fullscreen review, revision-aware prompts and Skill learning")
