from __future__ import annotations

import json
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import uuid4

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

_generation_jobs: dict[str, dict] = {}
_generation_jobs_lock = threading.Lock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _job_snapshot(project_id: str) -> dict:
    with _generation_jobs_lock:
        return dict(_generation_jobs.get(project_id) or {})


def _set_job(project_id: str, **updates) -> dict:
    with _generation_jobs_lock:
        current = dict(_generation_jobs.get(project_id) or {})
        current.update(updates)
        _generation_jobs[project_id] = current
        return dict(current)


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
        approved_geometry_asset=(
            state.get("assets", {}).get("geometry_candidate", "")
            if stage == "environment"
            else ""
        ),
        approved_mask_asset=(
            state.get("assets", {}).get("geometry_outpaint_mask", "")
            if stage == "environment"
            else ""
        ),
    )
    return prompts.compile(context, projects.path(project_id))


def _relative_path(value: str | None, project_dir: Path) -> str | None:
    if not value:
        return value
    path = Path(value)
    try:
        return str(path.resolve().relative_to(project_dir.resolve()))
    except (ValueError, OSError):
        return str(path)


def _transport_for_state(transport: dict | None, project_dir: Path) -> dict:
    if not transport:
        return {}
    output = dict(transport)
    for key in (
        "master_geometry_path",
        "master_mask_path",
        "transport_geometry_path",
        "transport_mask_path",
        "approved_geometry_path",
        "approved_mask_path",
        "effective_mask_path",
    ):
        output[key] = _relative_path(output.get(key), project_dir)
    return output


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(
        (STATIC_ROOT / "index.html").read_text("utf-8"),
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "name": APP_NAME,
        "version": APP_VERSION,
        "runtime": "standalone-v080",
        "image_provider": "openrouter",
        "image_model": ai_images.model,
        "image_configured": bool(ai_images.api_key),
        "transport_policy": "provider-aware-temporary-copy",
        "generation_mode": "background-job-polling",
    }


@app.get("/api/provider/image-capabilities")
def image_capabilities() -> dict:
    if not ai_images.api_key:
        raise HTTPException(409, "OPENROUTER_API_KEY is not configured")
    return ai_images.discover_capabilities()


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
        "geometry": state.get("geometry"),
        "generation_input": state.get("generation_input"),
        "generation": state.get("generation"),
        "generation_job": _job_snapshot(project_id),
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
        state["pipeline"].update(
            {
                "source": "approved",
                "geometry": "ready",
                "environment": "locked",
                "final": "locked",
                "branding": "locked",
            }
        )
        state["master_canvas"] = {"width": master["width"], "height": master["height"]}
        state["active_stage"] = "geometry"
        state.pop("geometry", None)
        state.pop("generation_input", None)
        state.pop("generation", None)
        projects.write(project_id, state)
        projects.record(
            project_id,
            "SourceUploaded",
            {
                "filename": file.filename,
                "width": master["width"],
                "height": master["height"],
                "master": state["assets"]["source_master"],
            },
        )
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
        result = geometry.apply(
            projects.path(project_id) / master_rel,
            projects.path(project_id),
            points,
        )
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
    state["geometry"] = {
        "quad": points,
        "transparent_pixels": result["transparent_pixels"],
        "transparent_ratio": result["transparent_ratio"],
        "canvas_preserved": result["canvas_preserved"],
        "status": "review",
    }
    state["pipeline"]["geometry"] = "ready"
    state["active_stage"] = "geometry"
    state.pop("generation_input", None)
    state.pop("generation", None)
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
    projects.record(
        project_id,
        "GeometryApproved",
        {
            "asset": state["assets"]["geometry_candidate"],
            "outpaint_mask": state["assets"].get("geometry_outpaint_mask"),
        },
    )
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


def _run_environment_generation(project_id: str, job_id: str) -> None:
    project_dir = projects.path(project_id)
    try:
        state = projects.read(project_id)
        geometry_rel = state.get("assets", {}).get("geometry_candidate")
        mask_rel = state.get("assets", {}).get("geometry_outpaint_mask")
        canvas = state.get("master_canvas") or {}
        if (
            state.get("pipeline", {}).get("geometry") != "approved"
            or not geometry_rel
            or not mask_rel
            or not canvas
        ):
            raise AIEngineError(
                "Approved geometry, outpaint mask or master canvas is missing",
                details={"reason": "generation_input_missing"},
            )

        started_at = _utc_now()
        state["pipeline"]["environment"] = "processing"
        state["active_stage"] = "environment"
        state["generation"] = {
            "stage": "environment",
            "provider": "openrouter",
            "model": ai_images.model,
            "status": "processing",
            "job_id": job_id,
            "started_at": started_at,
        }
        projects.write(project_id, state)
        _set_job(project_id, status="processing", started_at=started_at)
        projects.record(
            project_id,
            "EnvironmentGenerationStarted",
            {"job_id": job_id, "model": ai_images.model},
        )

        compiled = _compile_prompt(project_id, "environment")
        geometry_path = project_dir / geometry_rel
        mask_path = project_dir / mask_rel
        transport_dir = project_dir / "images" / "transport" / "environment"

        prepared = ai_images.prepare_environment_inputs(
            prompt=compiled["prompt"],
            geometry_image=geometry_path,
            outpaint_mask=mask_path,
            output_dir=transport_dir,
            width=int(canvas["width"]),
            height=int(canvas["height"]),
        )
        prepared_state = _transport_for_state(prepared, project_dir)

        state = projects.read(project_id)
        state["generation_input"] = prepared_state
        state["generation"].update(
            {
                "prompt": compiled.get("path"),
                "request_body_bytes": prepared_state.get("request_body_bytes"),
            }
        )
        projects.write(project_id, state)
        projects.record(
            project_id,
            "GenerationPayloadPrepared",
            {
                "job_id": job_id,
                "master": f"{prepared_state.get('master_width')}x{prepared_state.get('master_height')}",
                "transport": f"{prepared_state.get('transport_width')}x{prepared_state.get('transport_height')}",
                "request_body_bytes": prepared_state.get("request_body_bytes"),
                "safe_request_bytes": prepared_state.get("safe_request_bytes"),
                "resized_for_provider": prepared_state.get("resized_for_provider"),
                "request_limit_source": prepared_state.get("request_limit_source"),
                "full_canvas_generation": prepared_state.get("full_canvas_generation"),
            },
        )

        result = ai_images.generate_environment(
            prompt=compiled["prompt"],
            geometry_image=geometry_path,
            outpaint_mask=mask_path,
            output_dir=project_dir / "images" / "stages" / "environment",
            width=int(canvas["width"]),
            height=int(canvas["height"]),
            prepared_input=prepared,
        )
        candidate = Path(result["candidate"])
        preview = images.make_preview(
            candidate,
            project_dir,
            name="environment-candidate",
        )

        state = projects.read(project_id)
        report = quality.inspect(
            project_dir / state["assets"]["source_master"],
            candidate,
        )
        if not report.get("passed"):
            raise AIEngineError(
                f"Environment candidate failed quality control: {report}",
                details={"transport": result.get("transport")},
            )

        final_transport = _transport_for_state(result.get("transport"), project_dir)
        if final_transport and final_transport != prepared_state:
            projects.record(
                project_id,
                "GenerationPayloadAdjusted",
                {
                    "job_id": job_id,
                    "request_body_bytes": final_transport.get("request_body_bytes"),
                    "max_request_bytes": final_transport.get("max_request_bytes"),
                    "transport_width": final_transport.get("transport_width"),
                    "transport_height": final_transport.get("transport_height"),
                    "request_limit_source": final_transport.get("request_limit_source"),
                },
            )

        completed_at = _utc_now()
        state = projects.read(project_id)
        state["generation_input"] = final_transport or prepared_state
        state["assets"]["environment_candidate"] = str(candidate.relative_to(project_dir))
        state["assets"]["environment_preview"] = str(
            Path(preview["path"]).relative_to(project_dir)
        )
        state["generation"] = {
            "stage": "environment",
            "provider": result["provider"],
            "model": result["model"],
            "duration_seconds": result["duration_seconds"],
            "usage": result.get("usage") or {},
            "request_body_bytes": result.get("request_body_bytes"),
            "transport": state["generation_input"],
            "status": "review",
            "job_id": job_id,
            "started_at": started_at,
            "completed_at": completed_at,
        }
        state.setdefault("quality", {})["environment_candidate"] = report
        state["pipeline"]["environment"] = "ready"
        projects.write(project_id, state)
        _set_job(
            project_id,
            status="completed",
            completed_at=completed_at,
            error=None,
        )
        projects.record(
            project_id,
            "EnvironmentGenerationCompleted",
            state["generation"],
        )
    except Exception as exc:
        details = exc.details if isinstance(exc, AIEngineError) else {}
        state = projects.read(project_id)
        transport = details.get("transport") if isinstance(details, dict) else None
        if transport:
            state["generation_input"] = _transport_for_state(transport, project_dir)
        failed_at = _utc_now()
        state["pipeline"]["environment"] = "error"
        state["generation"] = {
            "stage": "environment",
            "provider": "openrouter",
            "model": ai_images.model,
            "status": "error",
            "job_id": job_id,
            "error": str(exc),
            "failed_at": failed_at,
            "request_body_bytes": (
                details.get("request_body_bytes")
                if isinstance(details, dict)
                else None
            ),
            "transport": state.get("generation_input"),
        }
        projects.write(project_id, state)
        _set_job(
            project_id,
            status="error",
            failed_at=failed_at,
            error=str(exc),
        )
        projects.record(
            project_id,
            "EnvironmentGenerationFailed",
            {
                **state["generation"],
                "exception": type(exc).__name__,
                "details": details,
            },
        )


@app.post("/api/projects/{project_id}/environment/generate")
def generate_environment(project_id: str) -> JSONResponse:
    state = projects.read(project_id)
    if state.get("pipeline", {}).get("geometry") != "approved":
        raise HTTPException(409, "Approve geometry before environment generation")

    assets = state.get("assets", {})
    canvas = state.get("master_canvas") or {}
    if (
        not assets.get("geometry_candidate")
        or not assets.get("geometry_outpaint_mask")
        or not canvas
    ):
        raise HTTPException(
            409,
            "Geometry candidate, outpaint mask or master canvas is missing",
        )

    running = _job_snapshot(project_id)
    if running.get("status") in {"queued", "processing"}:
        return JSONResponse(
            status_code=202,
            content={
                "job_id": running.get("job_id"),
                "status": running.get("status"),
                "status_url": f"/api/projects/{project_id}/environment/generation-status",
            },
        )

    job_id = uuid4().hex
    queued_at = _utc_now()
    state["assets"].pop("environment_candidate", None)
    state["assets"].pop("environment_preview", None)
    state["pipeline"]["environment"] = "processing"
    state["active_stage"] = "environment"
    state["generation"] = {
        "stage": "environment",
        "provider": "openrouter",
        "model": ai_images.model,
        "status": "queued",
        "job_id": job_id,
        "queued_at": queued_at,
    }
    projects.write(project_id, state)
    _set_job(
        project_id,
        job_id=job_id,
        status="queued",
        queued_at=queued_at,
        error=None,
    )
    projects.record(
        project_id,
        "EnvironmentGenerationQueued",
        {"job_id": job_id, "model": ai_images.model},
    )

    worker = threading.Thread(
        target=_run_environment_generation,
        args=(project_id, job_id),
        name=f"environment-{project_id[:8]}-{job_id[:8]}",
        daemon=True,
    )
    worker.start()

    return JSONResponse(
        status_code=202,
        content={
            "job_id": job_id,
            "status": "queued",
            "status_url": f"/api/projects/{project_id}/environment/generation-status",
        },
    )


@app.get("/api/projects/{project_id}/environment/generation-status")
def generation_status(project_id: str) -> dict:
    state = projects.read(project_id)
    generation = state.get("generation") or {}
    job = _job_snapshot(project_id)
    status = generation.get("status") or job.get("status") or "idle"
    if status == "review":
        status = "completed"
    return {
        "job_id": generation.get("job_id") or job.get("job_id"),
        "status": status,
        "pipeline_status": state.get("pipeline", {}).get("environment"),
        "error": generation.get("error") or job.get("error"),
        "project": state,
    }


@app.post("/api/projects/{project_id}/environment/approve")
def approve_environment(project_id: str) -> dict:
    state = projects.read(project_id)
    if not state.get("assets", {}).get("environment_candidate"):
        raise HTTPException(409, "Generate environment candidate before approval")
    state["pipeline"].update(
        {"environment": "approved", "final": "ready", "branding": "ready"}
    )
    state["active_stage"] = "branding"
    if state.get("generation"):
        state["generation"]["status"] = "approved"
    projects.write(project_id, state)
    projects.record(
        project_id,
        "EnvironmentApproved",
        {"asset": state["assets"]["environment_candidate"]},
    )
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
    if status not in {
        "ready",
        "editing",
        "processing",
        "approved",
        "locked",
        "error",
    }:
        raise HTTPException(422, "Unsupported status")
    state = projects.read(project_id)
    state["pipeline"][stage] = status
    state["active_stage"] = stage
    projects.write(project_id, state)
    projects.record(
        project_id,
        "StageStatusChanged",
        {"stage": stage, "status": status},
    )
    return projects.read(project_id)


@app.get("/api/projects/{project_id}/prompt/{stage}")
def compile_prompt(project_id: str, stage: str) -> dict:
    result = _compile_prompt(project_id, stage)
    state = projects.read(project_id)
    comments = [x for x in state.get("comments", []) if x.get("stage") == stage]
    projects.record(
        project_id,
        "PromptCompiled",
        {
            "stage": stage,
            "comment_count": len(comments),
            "path": result.get("path"),
        },
    )
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
    return FileResponse(
        path,
        headers={
            "Cache-Control": "no-transform, no-store",
            "X-Marins-Resolution-Policy": "original-full-resolution",
        },
    )


@app.get("/api/projects/{project_id}/quality/{asset_key}")
def inspect_asset(project_id: str, asset_key: str) -> JSONResponse:
    state = projects.read(project_id)
    master_rel = state.get("assets", {}).get("source_master")
    candidate_rel = state.get("assets", {}).get(asset_key)
    if not master_rel or not candidate_rel:
        raise HTTPException(404, "Assets not found")
    report = quality.inspect(
        projects.path(project_id) / master_rel,
        projects.path(project_id) / candidate_rel,
    )
    state.setdefault("quality", {})[asset_key] = report
    projects.write(project_id, state)
    projects.record(
        project_id,
        "QualityInspected",
        {
            "asset": asset_key,
            "passed": report.get("passed"),
            "report": report,
        },
    )
    return JSONResponse(report)
