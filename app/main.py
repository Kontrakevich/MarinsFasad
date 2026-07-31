from __future__ import annotations

import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageDraw

load_dotenv()
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "projects"
DATA.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Marins Fasad Control Center", version="1.0.0")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def project_dir(project_id: str) -> Path:
    p = DATA / project_id
    if not p.exists():
        raise HTTPException(404, "Project not found")
    return p


def state_path(p: Path) -> Path:
    return p / "project.json"


def load_state(p: Path) -> dict:
    return json.loads(state_path(p).read_text("utf-8"))


def save_state(p: Path, state: dict) -> None:
    state["updated_at"] = now()
    state_path(p).write_text(json.dumps(state, ensure_ascii=False, indent=2), "utf-8")


def log_event(p: Path, action: str, payload: dict | None = None) -> None:
    with (p / "logs" / "events.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"at": now(), "action": action, "payload": payload or {}}, ensure_ascii=False) + "\n")


def ensure_skill(p: Path, stage: str) -> Path:
    folder = p / "skills" / stage
    (folder / "history").mkdir(parents=True, exist_ok=True)
    current = folder / "current.md"
    if not current.exists():
        current.write_text(
            f"# {stage.title()} Skill\n\n## Цель\nРабочая инструкция этапа {stage}.\n\n## Ограничения\n- Не изменять подтвержденные элементы предыдущих этапов.\n- Все корректировки фиксировать в журнале.\n",
            "utf-8",
        )
    return current


def promote_skill(p: Path, stage: str, comment: str) -> str:
    current = ensure_skill(p, stage)
    folder = current.parent
    versions = sorted((folder / "history").glob("v*.md"))
    version = len(versions) + 1
    text = current.read_text("utf-8")
    text += f"\n\n## Подтвержденная итерация {version}\n- Дата: {now()}\n- Комментарий: {comment or 'Результат подтвержден без замечаний.'}\n"
    archived = folder / "history" / f"v{version:03d}.md"
    archived.write_text(text, "utf-8")
    current.write_text(text, "utf-8")
    return archived.name


def geometry_correct(src: Path, dst: Path, report_path: Path) -> dict:
    image = cv2.imread(str(src))
    if image is None:
        raise HTTPException(400, "Unsupported image")
    h, w = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 60, 180)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=max(60, w // 18), minLineLength=max(60, w // 14), maxLineGap=20)
    horizontal_angles, vertical_angles = [], []
    if lines is not None:
        for x1, y1, x2, y2 in np.asarray(lines).reshape(-1, 4):
            angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
            a = ((angle + 90) % 180) - 90
            if abs(a) < 20:
                horizontal_angles.append(a)
            if abs(abs(a) - 90) < 20:
                vertical_angles.append(a)
    rotation = float(np.median(horizontal_angles)) if horizontal_angles else 0.0
    rotation = max(-2.0, min(2.0, rotation))
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), rotation, 1.0)
    rotated = cv2.warpAffine(image, matrix, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)
    cv2.imwrite(str(dst), rotated)
    report = {
        "rotation_applied_deg": rotation,
        "horizontal_lines": len(horizontal_angles),
        "vertical_lines": len(vertical_angles),
        "perspective_status": "manual_review_required",
        "note": "Горизонт выровнен локально. Параллельность вертикалей должна быть подтверждена оператором до следующего этапа.",
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    return report


def copy_placeholder(src: Path, dst: Path, label: str) -> None:
    image = Image.open(src).convert("RGB")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((20, 20, 620, 92), radius=16, fill=(255, 255, 255), outline=(0, 48, 80), width=3)
    draw.text((42, 42), label, fill=(0, 48, 80))
    image.save(dst, quality=95)


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse((ROOT / "static" / "index.html").read_text("utf-8"))


@app.get("/api/projects")
def list_projects() -> list[dict]:
    result = []
    for path in sorted(DATA.iterdir(), reverse=True):
        if state_path(path).exists():
            result.append(load_state(path))
    return result


@app.post("/api/projects")
def create_project(name: str = Form(...)) -> dict:
    project_id = uuid.uuid4().hex[:10]
    p = DATA / project_id
    for folder in ["source", "geometry", "environment", "final", "branding", "logs", "skills/geometry/history", "skills/environment/history", "skills/branding/history"]:
        (p / folder).mkdir(parents=True, exist_ok=True)
    state = {"id": project_id, "name": name, "created_at": now(), "updated_at": now(), "stage": "source", "statuses": {"geometry": "waiting", "environment": "locked", "branding": "locked"}, "files": {}, "comments": []}
    save_state(p, state)
    for stage in ["geometry", "environment", "branding"]:
        ensure_skill(p, stage)
    log_event(p, "project_created", {"name": name})
    return state


@app.get("/api/projects/{project_id}")
def get_project(project_id: str) -> dict:
    return load_state(project_dir(project_id))


@app.post("/api/projects/{project_id}/source")
async def upload_source(project_id: str, file: UploadFile = File(...)) -> dict:
    p = project_dir(project_id)
    suffix = Path(file.filename or "source.jpg").suffix.lower() or ".jpg"
    dst = p / "source" / f"source{suffix}"
    with dst.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    state = load_state(p)
    state["files"]["source"] = str(dst.relative_to(p)).replace("\\", "/")
    state["statuses"]["geometry"] = "ready"
    save_state(p, state)
    log_event(p, "source_uploaded", {"filename": file.filename})
    return state


@app.post("/api/projects/{project_id}/geometry/run")
def run_geometry(project_id: str) -> dict:
    p = project_dir(project_id)
    state = load_state(p)
    source_rel = state["files"].get("source")
    if not source_rel:
        raise HTTPException(409, "Upload source first")
    src = p / source_rel
    dst = p / "geometry" / "geometry_corrected.jpg"
    report = geometry_correct(src, dst, p / "geometry" / "geometry.json")
    state["files"]["geometry"] = str(dst.relative_to(p)).replace("\\", "/")
    state["files"]["geometry_report"] = "geometry/geometry.json"
    state["statuses"]["geometry"] = "review"
    state["stage"] = "geometry_review"
    save_state(p, state)
    log_event(p, "geometry_generated", report)
    return state


def approve_stage(project_id: str, stage: str, comment: str) -> dict:
    p = project_dir(project_id)
    state = load_state(p)
    if state["statuses"].get(stage) != "review":
        raise HTTPException(409, f"{stage} is not awaiting review")
    version = promote_skill(p, stage, comment)
    state["statuses"][stage] = "approved"
    if stage == "geometry":
        state["statuses"]["environment"] = "ready"
        state["stage"] = "environment"
    elif stage == "environment":
        src = p / state["files"]["environment"]
        dst = p / "final" / "final.jpg"
        shutil.copy2(src, dst)
        state["files"]["final"] = "final/final.jpg"
        state["statuses"]["branding"] = "ready"
        state["stage"] = "branding"
    elif stage == "branding":
        state["stage"] = "complete"
    state["comments"].append({"stage": stage, "type": "approval", "text": comment, "at": now(), "skill_version": version})
    save_state(p, state)
    log_event(p, f"{stage}_approved", {"comment": comment, "skill_version": version})
    return state


def revise_stage(project_id: str, stage: str, comment: str) -> dict:
    p = project_dir(project_id)
    state = load_state(p)
    state["statuses"][stage] = "ready"
    state["comments"].append({"stage": stage, "type": "revision", "text": comment, "at": now()})
    current = ensure_skill(p, stage)
    current.write_text(current.read_text("utf-8") + f"\n\n## Новая корректировка\n- {now()}: {comment}\n", "utf-8")
    save_state(p, state)
    log_event(p, f"{stage}_revision_requested", {"comment": comment})
    return state


@app.post("/api/projects/{project_id}/geometry/approve")
def approve_geometry(project_id: str, comment: str = Form("")) -> dict:
    return approve_stage(project_id, "geometry", comment)


@app.post("/api/projects/{project_id}/geometry/revise")
def revise_geometry(project_id: str, comment: str = Form(...)) -> dict:
    return revise_stage(project_id, "geometry", comment)


@app.post("/api/projects/{project_id}/environment/run")
def run_environment(project_id: str) -> dict:
    p = project_dir(project_id)
    state = load_state(p)
    if state["statuses"].get("geometry") != "approved":
        raise HTTPException(409, "Approve geometry first")
    src = p / state["files"]["geometry"]
    dst = p / "environment" / "environment.jpg"
    copy_placeholder(src, dst, "ENVIRONMENT GENERATION PLACEHOLDER")
    state["files"]["environment"] = "environment/environment.jpg"
    state["statuses"]["environment"] = "review"
    state["stage"] = "environment_review"
    save_state(p, state)
    log_event(p, "environment_generated", {"provider": "adapter_placeholder"})
    return state


@app.post("/api/projects/{project_id}/environment/approve")
def approve_environment(project_id: str, comment: str = Form("")) -> dict:
    return approve_stage(project_id, "environment", comment)


@app.post("/api/projects/{project_id}/environment/revise")
def revise_environment(project_id: str, comment: str = Form(...)) -> dict:
    return revise_stage(project_id, "environment", comment)


@app.post("/api/projects/{project_id}/branding/run")
def run_branding(project_id: str, x: int = Form(...), y: int = Form(...), width: int = Form(...), height: int = Form(...), material: str = Form(...), logo: UploadFile | None = File(None)) -> dict:
    p = project_dir(project_id)
    state = load_state(p)
    final_rel = state["files"].get("final")
    if not final_rel:
        raise HTTPException(409, "Approve environment first")
    src = p / final_rel
    image = Image.open(src).convert("RGB")
    draw = ImageDraw.Draw(image)
    draw.rectangle((x, y, x + width, y + height), outline=(0, 138, 144), width=max(3, image.width // 300))
    draw.text((x + 8, y + 8), "SIGNAGE ZONE", fill=(0, 138, 144))
    dst = p / "branding" / "branding.jpg"
    image.save(dst, quality=95)
    placement = {"x": x, "y": y, "width": width, "height": height, "material": material}
    (p / "branding" / "placement.json").write_text(json.dumps(placement, ensure_ascii=False, indent=2), "utf-8")
    if logo and logo.filename:
        with (p / "branding" / Path(logo.filename).name).open("wb") as out:
            shutil.copyfileobj(logo.file, out)
    state["files"]["branding"] = "branding/branding.jpg"
    state["files"]["placement"] = "branding/placement.json"
    state["statuses"]["branding"] = "review"
    state["stage"] = "branding_review"
    save_state(p, state)
    log_event(p, "branding_generated", placement)
    return state


@app.post("/api/projects/{project_id}/branding/approve")
def approve_branding(project_id: str, comment: str = Form("")) -> dict:
    return approve_stage(project_id, "branding", comment)


@app.post("/api/projects/{project_id}/branding/revise")
def revise_branding(project_id: str, comment: str = Form(...)) -> dict:
    return revise_stage(project_id, "branding", comment)


@app.get("/api/projects/{project_id}/file/{file_key}")
def get_file(project_id: str, file_key: str):
    p = project_dir(project_id)
    state = load_state(p)
    rel = state["files"].get(file_key)
    if not rel:
        raise HTTPException(404, "File not found")
    target = (p / rel).resolve()
    if p.resolve() not in target.parents:
        raise HTTPException(400, "Invalid path")
    return FileResponse(target)
