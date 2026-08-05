from __future__ import annotations

import json
import shutil
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .ai_engine import AIEngineError, OpenRouterImageEngine
from .config import APP_NAME, APP_VERSION, DATA_ROOT, STATIC_ROOT
from .geometry_engine import GeometryEngine
from .image_engine import ImageEngine
from .project_engine import ProjectEngine
from .prompt_engine import PromptContext, PromptEngine
from .quality_engine import QualityEngine

app = FastAPI(title=APP_NAME, version=APP_VERSION)
projects = ProjectEngine(DATA_ROOT)
images = ImageEngine()
geometry = GeometryEngine()
prompts = PromptEngine()
quality = QualityEngine()
ai_images = OpenRouterImageEngine()
app.mount("/static", StaticFiles(directory=STATIC_ROOT), name="static")


def _compile_prompt(project_id: str, stage: str) -> dict:
    state = projects.read(project_id)
    comments = [x["text"] for x in state.get("comments", []) if x.get("stage") == stage]
    geometry_block = ""
    if stage == "environment" and state.get("geometry"):
        geometry_block = (
            " Use the approved geometry candidate and its transparent outpaint mask. "
            "Fill every masked pixel with continuous photorealistic surroundings while preserving the exact master canvas. "
            "Do not crop, reframe, resize, letterbox or alter approved opaque architecture pixels."
        )
    context = PromptContext(
        stage=stage,
        master_prompt="You are the architectural image execution model inside Marins Facade Control Center.",
        skill=f"Execute the {stage} stage while preserving all previously approved architecture.{geometry_block}",
        comments=comments,
    )
    return prompts.compile(context, projects.path(project_id))


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse((STATIC_ROOT / "index.html").read_text("utf-8"))


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "name": APP_NAME, "version": APP_VERSION, "runtime": "standalone-v080", "image_provider": "openrouter", "image_model": ai_images.model, "image_configured": bool(ai_images.api_key)}


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
    return {"project_id": project_id, "version": state.get("version"), "pipeline": state.get("pipeline", {}), "master_canvas": state.get("master_canvas"), "geometry": state.get("geometry"), "generation": state.get("generation"), "quality": state.get("quality", {}), "events": projects.history(project_id, 30)}


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
        state["pipeline"].update({"source": "approved", "geometry": "ready", "environment": "locked", "final": "locked", "branding": "locked"})
        state["master_canvas"] = {"width": master["width"], "height": master["height"]}
        state["active_stage"] = "geometry"
        state.pop("geometry", None)
        state.pop("generation", None)
        projects.write(project_id, state)
        projects.record(project_id, "SourceUploaded", {"filename": file.filename, "width": master["width"], "height": master["height"], "master": state["assets"]["source_master"]})
        return projects.read(project_id)
    finally:
        temp_path.unlink(missing_ok=True)


@app.post("/api/projects/{project_id}/geometry/apply-grid")
def apply_geometry_grid(project_id: str, quad_json: str = Form(...)) -> dict:
    state = projects.read(project_id)
    master_rel = state.get("assets", {}).get("source_master")
    if not master_rel:
        raise HTTPException(409, "Upload source before geometry correction")
    try:
        points = json.loads(quad_json)
        result = geometry.apply(projects.path(project_id) / master_rel, projects.path(project_id), points)
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(422, str(exc))
    project_dir = projects.path(project_id)
    candidate = Path(result["candidate"])
    mask = Path(result["outpaint_mask"])
    preview = images.make_preview(candidate, project_dir, name="geometry-candidate")
    state = projects.read(project_id)
    state["assets"]["geometry_candidate"] = str(candidate.relative_to(project_dir))
    state["assets"]["geometry_preview"] = str(Path(preview["path"]).relative_to(project_dir))
    state["assets"]["geometry_outpaint_mask"] = str(mask.relative_to(project_dir))
    state["geometry"] = {"quad": points, "transparent_pixels": result["transparent_pixels"], "transparent_ratio": result["transparent_ratio"], "canvas_preserved": result["canvas_preserved"], "status": "review"}
    state["pipeline"]["geometry"] = "ready"
    state["active_stage"] = "geometry"
    projects.write(project_id, state)
    projects.record(project_id, "GeometryGridApplied", state["geometry"])
    return projects.read(project_id)


@app.post("/api/projects/{project_id}/geometry/approve")
def approve_geometry(project_id: str) -> dict:
    state = projects.read(project_id)
    if not state.get("assets", {}).get("geometry_candidate"):
        raise HTTPException(409, "Apply perspective grid before approval")
    state["geometry"]["status"] = "approved"
    state["pipeline"].update({"geometry": "approved", "environment": "ready"})
    state["active_stage"] = "environment"
    projects.write(project_id, state)
    projects.record(project_id, "GeometryApproved", {"asset": state["assets"]["geometry_candidate"], "outpaint_mask": state["assets"].get("geometry_outpaint_mask")})
    return projects.read(project_id)


@app.post("/api/projects/{project_id}/geometry/revise")
def revise_geometry(project_id: str, comment: str = Form(...)) -> dict:
    clean = comment.strip()
    if not clean:
        raise HTTPException(422, "Comment is required")
    state = projects.read(project_id)
    entry = {"stage": "geometry", "text": clean, "status": "pending"}
    state.setdefault("comments", []).append(entry)
    state["pipeline"]["geometry"] = "editing"
    state["active_stage"] = "geometry"
    if state.get("geometry"):
        state["geometry"]["status"] = "revision"
    projects.write(project_id, state)
    projects.record(project_id, "GeometryRevisionAdded", entry)
    return projects.read(project_id)


@app.post("/api/projects/{project_id}/environment/generate")
def generate_environment(project_id: str) -> dict:
    state = projects.read(project_id)
    if state.get("pipeline", {}).get("geometry") != "approved":
        raise HTTPException(409, "Approve geometry before environment generation")
    project_dir = projects.path(project_id)
    geometry_rel = state.get("assets", {}).get("geometry_candidate")
    mask_rel = state.get("assets", {}).get("geometry_outpaint_mask")
    canvas = state.get("master_canvas") or {}
    if not geometry_rel or not mask_rel or not canvas:
        raise HTTPException(409, "Geometry candidate, outpaint mask or master canvas is missing")
    compiled = _compile_prompt(project_id, "environment")
    state["pipeline"]["environment"] = "processing"
    state["active_stage"] = "environment"
    projects.write(project_id, state)
    projects.record(project_id, "EnvironmentGenerationStarted", {"model": ai_images.model, "prompt": compiled.get("path")})
    try:
        result = ai_images.generate_environment(prompt=compiled["prompt"], geometry_image=project_dir / geometry_rel, outpaint_mask=project_dir / mask_rel, output_dir=project_dir / "images" / "stages" / "environment", width=int(canvas["width"]), height=int(canvas["height"]))
        candidate = Path(result["candidate"])
        preview = images.make_preview(candidate, project_dir, name="environment-candidate")
        report = quality.inspect(project_dir / state["assets"]["source_master"], candidate)
        if not report.get("passed"):
            raise AIEngineError(f"Environment candidate failed quality control: {report}")
        state = projects.read(project_id)
        state["assets"]["environment_candidate"] = str(candidate.relative_to(project_dir))
        state["assets"]["environment_preview"] = str(Path(preview["path"]).relative_to(project_dir))
        state["generation"] = {"stage": "environment", "provider": result["provider"], "model": result["model"], "duration_seconds": result["duration_seconds"], "usage": result.get("usage") or {}, "status": "review"}
        state.setdefault("quality", {})["environment_candidate"] = report
        state["pipeline"]["environment"] = "ready"
        projects.write(project_id, state)
        projects.record(project_id, "EnvironmentGenerationCompleted", state["generation"])
        return projects.read(project_id)
    except AIEngineError as exc:
        state = projects.read(project_id)
        state["pipeline"]["environment"] = "error"
        state["generation"] = {"stage": "environment", "provider": "openrouter", "model": ai_images.model, "status": "error", "error": str(exc)}
        projects.write(project_id, state)
        projects.record(project_id, "EnvironmentGenerationFailed", state["generation"])
        raise HTTPException(502, str(exc))


@app.post("/api/projects/{project_id}/environment/approve")
def approve_environment(project_id: str) -> dict:
    state = projects.read(project_id)
    if not state.get("assets", {}).get("environment_candidate"):
        raise HTTPException(409, "Generate environment candidate before approval")
    state["pipeline"].update({"environment": "approved", "final": "ready", "branding": "ready"})
    state["active_stage"] = "branding"
    if state.get("generation"):
        state["generation"]["status"] = "approved"
    projects.write(project_id, state)
    projects.record(project_id, "EnvironmentApproved", {"asset": state["assets"]["environment_candidate"]})
    return projects.read(project_id)


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
    result = _compile_prompt(project_id, stage)
    state = projects.read(project_id)
    comments = [x for x in state.get("comments", []) if x.get("stage") == stage]
    projects.record(project_id, "PromptCompiled", {"stage": stage, "comment_count": len(comments), "path": result.get("path")})
    return result


@app.get("/api/projects/{project_id}/assets/{asset_key}")
def get_asset(project_id: str, asset_key: str) -> FileResponse:
    state = projects.read(project_id)
    relative = state.get("assets", {}).get(asset_key)
    if not relative:
        raise HTTPException(404, "Asset not found")
    project_dir = projects.path(project_id)
    path = (project_dir / relative).resolve()
    if project_dir.resolve() not in path.parents:
        raise HTTPException(400, "Unsafe asset path")
    return FileResponse(path, headers={"Cache-Control": "no-transform, no-store", "X-Marins-Resolution-Policy": "original-full-resolution"})


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
