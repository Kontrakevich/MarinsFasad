from __future__ import annotations

import json
import urllib.request
import urllib.error
import mimetypes
import base64
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



def _line_angle_deg(line: list[dict]) -> float:
    p1, p2 = line
    return float(np.degrees(np.arctan2(
        float(p2["y"]) - float(p1["y"]),
        float(p2["x"]) - float(p1["x"]),
    )))


def _rotate_point(point: tuple[float, float], matrix: np.ndarray) -> tuple[float, float]:
    x, y = point
    return (
        float(matrix[0, 0] * x + matrix[0, 1] * y + matrix[0, 2]),
        float(matrix[1, 0] * x + matrix[1, 1] * y + matrix[1, 2]),
    )


def manual_perspective_correct(
    src: Path,
    dst: Path,
    report_path: Path,
    guides: dict,
) -> dict:
    """
    Выравнивает выбранную пользователем плоскость, но применяет
    гомографию ко всему изображению. Исходный кадр не обрезается
    по границам управляющей сетки.
    """
    image = cv2.imread(str(src))
    if image is None:
        raise HTTPException(400, "Unsupported image")

    height, width = image.shape[:2]
    quad = guides.get("quad")

    if not isinstance(quad, list) or len(quad) != 4:
        raise HTTPException(
            400,
            "Требуются четыре угловые точки сетки",
        )

    try:
        points = np.float32([
            [float(point["x"]), float(point["y"])]
            for point in quad
        ])
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            400,
            "Некорректные координаты сетки",
        ) from exc

    # Порядок точек:
    # 0 — верхняя левая
    # 1 — верхняя правая
    # 2 — нижняя правая
    # 3 — нижняя левая
    contour = points.reshape((-1, 1, 2))

    if not cv2.isContourConvex(contour):
        raise HTTPException(
            400,
            "Линии сетки не должны пересекаться",
        )

    area = abs(float(cv2.contourArea(contour)))
    if area < width * height * 0.02:
        raise HTTPException(
            400,
            "Область сетки слишком мала",
        )

    tl, tr, br, bl = points

    top_width = float(np.linalg.norm(tr - tl))
    bottom_width = float(np.linalg.norm(br - bl))
    left_height = float(np.linalg.norm(bl - tl))
    right_height = float(np.linalg.norm(br - tr))

    target_width = max(
        320,
        int(round(max(top_width, bottom_width))),
    )
    target_height = max(
        240,
        int(round(max(left_height, right_height))),
    )

    target_quad = np.float32([
        [0, 0],
        [target_width - 1, 0],
        [target_width - 1, target_height - 1],
        [0, target_height - 1],
    ])

    # Преобразование выбранной плоскости в прямоугольник.
    plane_matrix = cv2.getPerspectiveTransform(
        points,
        target_quad,
    )

    # Применяем ту же матрицу ко всем углам полного исходника.
    full_image_corners = np.float32([[
        [0, 0],
        [width - 1, 0],
        [width - 1, height - 1],
        [0, height - 1],
    ]])

    transformed_corners = cv2.perspectiveTransform(
        full_image_corners,
        plane_matrix,
    )[0]

    min_x = float(np.floor(transformed_corners[:, 0].min()))
    min_y = float(np.floor(transformed_corners[:, 1].min()))
    max_x = float(np.ceil(transformed_corners[:, 0].max()))
    max_y = float(np.ceil(transformed_corners[:, 1].max()))

    output_width = max(1, int(max_x - min_x))
    output_height = max(1, int(max_y - min_y))

    translation = np.array([
        [1.0, 0.0, -min_x],
        [0.0, 1.0, -min_y],
        [0.0, 0.0, 1.0],
    ], dtype=np.float64)

    full_matrix = translation @ plane_matrix

    # Защита от слишком большого результата.
    max_dimension = 8192
    max_pixels = 50_000_000

    dimension_scale = min(
        1.0,
        max_dimension / max(output_width, output_height),
    )

    pixel_scale = min(
        1.0,
        (
            max_pixels /
            max(1, output_width * output_height)
        ) ** 0.5,
    )

    output_scale = min(dimension_scale, pixel_scale)

    if output_scale < 1.0:
        scale_matrix = np.array([
            [output_scale, 0.0, 0.0],
            [0.0, output_scale, 0.0],
            [0.0, 0.0, 1.0],
        ], dtype=np.float64)

        full_matrix = scale_matrix @ full_matrix
        output_width = max(
            1,
            int(round(output_width * output_scale)),
        )
        output_height = max(
            1,
            int(round(output_height * output_scale)),
        )

    corrected = cv2.warpPerspective(
        image,
        full_matrix,
        (output_width, output_height),
        flags=cv2.INTER_LANCZOS4,
        borderMode=cv2.BORDER_REFLECT_101,
    )

    if not cv2.imwrite(
        str(dst),
        corrected,
        [cv2.IMWRITE_JPEG_QUALITY, 95],
    ):
        raise HTTPException(
            500,
            "Не удалось сохранить результат",
        )

    report = {
        "mode": "full_frame_perspective_grid",
        "crop_applied": False,
        "source_size": {
            "width": width,
            "height": height,
        },
        "output_size": {
            "width": output_width,
            "height": output_height,
        },
        "plane_target_size": {
            "width": target_width,
            "height": target_height,
        },
        "quad": quad,
        "matrix": full_matrix.tolist(),
        "status": "manual_review_required",
        "note": (
            "Выбранная плоскость выровнена, при этом гомография "
            "применена ко всему исходному изображению без кропа "
            "по управляющему четырёхугольнику."
        ),
    }

    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        "utf-8",
    )
    return report

@app.post("/api/projects/{project_id}/geometry/manual")
def run_manual_geometry(
    project_id: str,
    guides_json: str = Form(...),
) -> dict:
    p = project_dir(project_id)
    state = load_state(p)

    source_rel = state["files"].get("source")
    if not source_rel:
        raise HTTPException(409, "Upload source first")

    try:
        guides = json.loads(guides_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(400, "Invalid guides JSON") from exc

    src = p / source_rel
    dst = p / "geometry" / "geometry_manual.jpg"
    report_path = p / "geometry" / "geometry_manual.json"

    report = manual_perspective_correct(
        src,
        dst,
        report_path,
        guides,
    )

    state["files"]["geometry"] = "geometry/geometry_manual.jpg"
    state["files"]["geometry_report"] = "geometry/geometry_manual.json"
    state["geometry_grid"] = guides.get("quad", [])
    state["geometry_mode"] = "manual_grid"
    state["statuses"]["geometry"] = "review"
    state["stage"] = "geometry_review"

    state["comments"].append({
        "stage": "geometry",
        "type": "manual_guides",
        "text": "Геометрия построена по пользовательским направляющим.",
        "at": now(),
    })

    save_state(p, state)
    log_event(p, "manual_geometry_generated", report)
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


def compile_stage_system_prompt(
    project_path: Path,
    stage: str,
) -> str:
    allowed_stages = {
        "geometry",
        "environment",
        "branding",
    }

    if stage not in allowed_stages:
        raise HTTPException(400, "Unsupported AI stage")

    skill_text = ensure_skill(
        project_path,
        stage,
    ).read_text("utf-8")

    stage_rules = {
        "geometry": """
TASK: residual architectural geometry correction.

The supplied image may already contain an approved manual
perspective transformation.

Treat the supplied image as the immutable geometric source of truth.

Do not return to the original camera perspective.
Do not undo the manual projective transformation.
Do not crop the image.
Do not change framing, field of view or camera position.
Do not remove any part of the building.
Do not redesign the facade.
Do not move windows, doors, columns, slabs or roof elements.

Correct only residual optical distortions that prevent architectural
verticals from being parallel and the selected horizon from being
level.
""",
        "environment": """
TASK: environment cleanup and extension.

Preserve the approved building geometry, camera position, framing,
facade proportions and all architectural elements exactly.

Remove only temporary visual obstructions explicitly allowed by the
Skill: wires, poles, temporary vehicles, visual rubbish and other
listed objects.

Extend missing surroundings naturally without modifying the building.
Do not crop or reframe the approved geometry.
""",
        "branding": """
TASK: architectural signage integration.

Preserve the approved final image, architecture, perspective,
materials, lighting and framing.

Add only the requested logo or signage in the specified placement
zone, using the material, thickness, mounting and illumination
parameters recorded in the Skill and operator request.
""",
    }

    return f"""SYSTEM ROLE
You are the image execution model of Marins Fasad Control Center.

The current approved Skill is the primary instruction source.
Operator comments may refine the task but may not cancel locked
constraints from previous approved stages.

CURRENT STAGE
{stage}

STAGE-SPECIFIC RULES
{stage_rules[stage].strip()}

CURRENT SKILL
----------------
{skill_text.strip()}
----------------

OUTPUT REQUIREMENTS
Return one edited image.
Preserve maximum photorealism and source resolution.
Do not add captions, explanatory text, watermarks or UI elements.
"""


@app.get("/api/projects/{project_id}/prompt/{stage}")
def get_stage_system_prompt(
    project_id: str,
    stage: str,
) -> dict:
    p = project_dir(project_id)

    return {
        "stage": stage,
        "model": os.getenv(
            "OPENROUTER_IMAGE_MODEL",
            "google/gemini-2.5-flash-image",
        ),
        "prompt": compile_stage_system_prompt(p, stage),
    }


def image_as_data_url(image_path: Path) -> str:
    mime_type = (
        mimetypes.guess_type(image_path.name)[0]
        or "image/jpeg"
    )

    encoded = base64.b64encode(
        image_path.read_bytes()
    ).decode("ascii")

    return f"data:{mime_type};base64,{encoded}"


@app.post("/api/projects/{project_id}/ai/{stage}")
def run_ai_stage(
    project_id: str,
    stage: str,
    operator_comment: str = Form(""),
) -> dict:
    p = project_dir(project_id)
    state = load_state(p)

    if stage == "geometry":
        # Критически важно:
        # ручной результат имеет приоритет над исходником.
        source_rel = (
            state["files"].get("geometry")
            or state["files"].get("source")
        )
        output_rel = "geometry/geometry_ai.jpg"

    elif stage == "environment":
        source_rel = state["files"].get("geometry")
        output_rel = "environment/environment_ai.jpg"

    elif stage == "branding":
        source_rel = (
            state["files"].get("final")
            or state["files"].get("environment")
        )
        output_rel = "branding/branding_ai.jpg"

    else:
        raise HTTPException(400, "Unsupported AI stage")

    if not source_rel:
        raise HTTPException(
            409,
            "Не найден утверждённый входной файл этапа",
        )

    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(
            409,
            "OPENROUTER_API_KEY не задан в Codespaces secrets",
        )

    model = os.getenv(
        "OPENROUTER_IMAGE_MODEL",
        "google/gemini-2.5-flash-image",
    ).strip()

    source_path = p / source_rel
    output_path = p / output_rel

    system_prompt = compile_stage_system_prompt(
        p,
        stage,
    )

    final_prompt = system_prompt

    if operator_comment.strip():
        final_prompt += (
            "\n\nOPERATOR REQUEST\n"
            + operator_comment.strip()
        )

    prompt_path = p / stage / "system_prompt.txt"
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(final_prompt, "utf-8")

    payload = {
        "model": model,
        "prompt": final_prompt,
        "n": 1,
        "quality": "high",
        "output_format": "jpeg",
        "input_references": [
            {
                "type": "image_url",
                "image_url": {
                    "url": image_as_data_url(source_path),
                },
            },
        ],
    }

    request = urllib.request.Request(
        "https://openrouter.ai/api/v1/images",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/Kontrakevich/MarinsFasad",
            "X-Title": "Marins Fasad Control Center",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=300,
        ) as response:
            result = json.loads(
                response.read().decode("utf-8")
            )

    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode(
            "utf-8",
            errors="replace",
        )

        raise HTTPException(
            exc.code,
            f"OpenRouter: {error_body[:2000]}",
        ) from exc

    except urllib.error.URLError as exc:
        raise HTTPException(
            502,
            f"OpenRouter connection error: {exc}",
        ) from exc

    image_items = result.get("data") or []

    if not image_items:
        raise HTTPException(
            502,
            "OpenRouter не вернул изображение",
        )

    image_base64 = image_items[0].get("b64_json")
    if not image_base64:
        raise HTTPException(
            502,
            "В ответе OpenRouter отсутствует b64_json",
        )

    try:
        output_path.write_bytes(
            base64.b64decode(image_base64)
        )
    except Exception as exc:
        raise HTTPException(
            502,
            "Не удалось декодировать изображение OpenRouter",
        ) from exc

    state["files"][f"{stage}_system_prompt"] = str(
        prompt_path.relative_to(p)
    ).replace("\\", "/")

    if stage == "geometry":
        state["files"]["geometry"] = output_rel
        state["statuses"]["geometry"] = "review"
        state["stage"] = "geometry_review"

    elif stage == "environment":
        state["files"]["environment"] = output_rel
        state["statuses"]["environment"] = "review"
        state["stage"] = "environment_review"

    elif stage == "branding":
        state["files"]["branding"] = output_rel
        state["statuses"]["branding"] = "review"
        state["stage"] = "branding_review"

    state["comments"].append({
        "stage": stage,
        "type": "ai_generation",
        "text": operator_comment.strip(),
        "model": model,
        "input_file": source_rel,
        "output_file": output_rel,
        "at": now(),
    })

    save_state(p, state)

    log_event(
        p,
        f"{stage}_ai_generated",
        {
            "model": model,
            "input_file": source_rel,
            "output_file": output_rel,
            "usage": result.get("usage"),
        },
    )

    return state
