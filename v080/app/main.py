from __future__ import annotations

import shutil
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import APP_NAME, APP_VERSION, DATA_ROOT, STATIC_ROOT
from .image_engine import ImageEngine
from .project_engine import ProjectEngine
from .prompt_engine import PromptContext, PromptEngine
from .quality_engine import QualityEngine

app = FastAPI(title=APP_NAME, version=APP_VERSION)
projects = ProjectEngine(DATA_ROOT)
images = ImageEngine()
prompts = PromptEngine()
quality = QualityEngine()
app.mount("/static", StaticFiles(directory=STATIC_ROOT), name="static")


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse((STATIC_ROOT / "index.html").read_text("utf-8"))


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "name": APP_NAME, "version": APP_VERSION, "runtime": "standalone-v080"}


@app.get("/api/projects")
def list_projects() -> list[dict]:
    return projects.list()


@app.post("/api/projects")
def create_project(name: str = Form(...)) -> dict:
    return projects.create(name)


@app.get("/api/projects/{project_id}")
def get_project(project_id: str) -> dict:
    try:
        return projects.read(project_id)
    except FileNotFoundError:
        raise HTTPException(404, "Project not found")


@app.get("/api/projects/{project_id}/history")
def get_history(project_id: str, limit: int = 100) -> list[dict]:
    return projects.history(project_id, limit)


@app.get("/api/projects/{project_id}/diagnostics")
def get_diagnostics(project_id: str) -> dict:
    state = projects.read(project_id)
    return {
        "project_id": project_id,
        "version": state.get("version"),
        "pipeline": state.get("pipeline", {}),
        "master_canvas": state.get("master_canvas"),
        "quality": state.get("quality", {}),
        "events": projects.history(project_id, 30),
    }


@app.post("/api/projects/{project_id}/source")
async def upload_source(project_id: str, file: UploadFile = File(...)) -> dict:
    project_dir = projects.path(project_id)
    suffix = Path(file.filename or "source.png").suffix or ".png"
    with NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        temp_path = Path(tmp.name)
    try:
        master = images.ingest_master(temp_path, project_dir)
        master_path = Path(master["path"])
        preview = images.make_preview(master_path, project_dir)
        state = projects.read(project_id)
        state["assets"]["source_master"] = str(master_path.relative_to(project_dir))
        state["assets"]["source_preview"] = str(Path(preview["path"]).relative_to(project_dir))
        state["pipeline"].update({"source": "approved", "geometry": "ready"})
        state["master_canvas"] = {"width": master["width"], "height": master["height"]}
        state["active_stage"] = "geometry"
        projects.write(project_id, state)
        projects.record(project_id, "SourceUploaded", {"filename": file.filename, "width": master["width"], "height": master["height"], "master": state["assets"]["source_master"]})
        return projects.read(project_id)
    finally:
        temp_path.unlink(missing_ok=True)


@app.post("/api/projects/{project_id}/comments/{stage}")
def add_comment(project_id: str, stage: str, comment: str = Form(...)) -> dict:
    if stage not in {"geometry", "environment", "branding"}:
        raise HTTPException(422, "Unsupported stage")
    clean = comment.strip()
    if not clean:
        raise HTTPException(422, "Comment is required")
    state = projects.read(project_id)
    entry = {"stage": stage, "text": clean, "status": "pending"}
    state["comments"].append(entry)
    state["pipeline"][stage] = "editing"
    state["active_stage"] = stage
    projects.write(project_id, state)
    event = projects.record(project_id, "RevisionAdded", entry)
    state = projects.read(project_id)
    state["last_event"] = event
    return state


@app.post("/api/projects/{project_id}/stages/{stage}/status")
def set_stage_status(project_id: str, stage: str, status: str = Form(...)) -> dict:
    if stage not in {"source", "geometry", "environment", "branding", "final"}:
        raise HTTPException(422, "Unsupported stage")
    if status not in {"ready", "editing", "processing", "approved", "locked", "error"}:
        raise HTTPException(422, "Unsupported status")
    state = projects.read(project_id)
    state["pipeline"][stage] = status
    state["active_stage"] = stage
    projects.write(project_id, state)
    projects.record(project_id, "StageStatusChanged", {"stage": stage, "status": status})
    return projects.read(project_id)


@app.get("/api/projects/{project_id}/prompt/{stage}")
def compile_prompt(project_id: str, stage: str) -> dict:
    state = projects.read(project_id)
    comments = [x["text"] for x in state.get("comments", []) if x.get("stage") == stage]
    context = PromptContext(
        stage=stage,
        master_prompt="You are the architectural image execution model inside Marins Facade Control Center.",
        skill=f"Execute the {stage} stage while preserving all previously approved architecture.",
        comments=comments,
    )
    result = prompts.compile(context, projects.path(project_id))
    projects.record(project_id, "PromptCompiled", {"stage": stage, "comment_count": len(comments), "path": result.get("path")})
    return result


@app.get("/api/projects/{project_id}/assets/{asset_key}")
def get_asset(project_id: str, asset_key: str) -> FileResponse:
    state = projects.read(project_id)
    relative = state.get("assets", {}).get(asset_key)
    if not relative:
        raise HTTPException(404, "Asset not found")
    path = (projects.path(project_id) / relative).resolve()
    return FileResponse(path, headers={"Cache-Control": "no-transform", "X-Marins-Resolution-Policy": "original-full-resolution"})


@app.get("/api/projects/{project_id}/quality/{asset_key}")
def inspect_asset(project_id: str, asset_key: str) -> JSONResponse:
    state = projects.read(project_id)
    master_rel = state.get("assets", {}).get("source_master")
    candidate_rel = state.get("assets", {}).get(asset_key)
    if not master_rel or not candidate_rel:
        raise HTTPException(404, "Assets not found")
    report = quality.inspect(projects.path(project_id) / master_rel, projects.path(project_id) / candidate_rel)
    state.setdefault("quality", {})[asset_key] = report
    projects.write(project_id, state)
    projects.record(project_id, "QualityInspected", {"asset": asset_key, "passed": report.get("passed"), "report": report})
    return JSONResponse(report)
