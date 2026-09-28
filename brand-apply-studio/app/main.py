from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "projects"
STATIC = ROOT / "static"
DATA.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Brand Apply Studio", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def project_dir(project_id: str) -> Path:
    path = DATA / project_id
    if not path.exists():
        raise HTTPException(404, "Project not found")
    return path


def state_path(path: Path) -> Path:
    return path / "project.json"


def load_state(path: Path) -> dict:
    return json.loads(state_path(path).read_text("utf-8"))


def save_state(path: Path, state: dict) -> None:
    state["updated_at"] = now()
    state_path(path).write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        "utf-8",
    )


def validate_quad(raw_quad: object, width: int, height: int) -> np.ndarray:
    if not isinstance(raw_quad, list) or len(raw_quad) != 4:
        raise HTTPException(400, "Required four perspective points")

    try:
        points = np.float32([
            [float(p["x"]), float(p["y"])]
            for p in raw_quad
        ])
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(400, "Invalid perspective coordinates") from exc

    contour = points.reshape((-1, 1, 2))

    if not cv2.isContourConvex(contour):
        raise HTTPException(400, "Perspective grid must be convex")

    area = abs(float(cv2.contourArea(contour)))
    if area < width * height * 0.002:
        raise HTTPException(400, "Perspective surface is too small")

    if (
        points[:, 0].min() < 0
        or points[:, 1].min() < 0
        or points[:, 0].max() > width
        or points[:, 1].max() > height
    ):
        raise HTTPException(400, "Perspective points must stay inside master image")

    return points


def quad_size(points: np.ndarray) -> tuple[int, int]:
    tl, tr, br, bl = points
    width = int(round(max(
        np.linalg.norm(tr - tl),
        np.linalg.norm(br - bl),
    )))
    height = int(round(max(
        np.linalg.norm(bl - tl),
        np.linalg.norm(br - tr),
    )))
    return max(width, 2), max(height, 2)


def bilinear_point(points: np.ndarray, u: float, v: float) -> tuple[int, int]:
    tl, tr, br, bl = points
    top = tl + (tr - tl) * u
    bottom = bl + (br - bl) * u
    point = top + (bottom - top) * v
    return int(round(point[0])), int(round(point[1]))


def make_guide(master: np.ndarray, points: np.ndarray) -> np.ndarray:
    guide = master.copy()
    line_color = (199, 212, 0)
    outline_color = (255, 255, 255)

    for column in range(9):
        u = column / 8
        poly = np.array(
            [bilinear_point(points, u, step / 40) for step in range(41)],
            dtype=np.int32,
        )
        cv2.polylines(guide, [poly], False, line_color, 2, cv2.LINE_AA)

    for row in range(7):
        v = row / 6
        poly = np.array(
            [bilinear_point(points, step / 40, v) for step in range(41)],
            dtype=np.int32,
        )
        cv2.polylines(guide, [poly], False, line_color, 2, cv2.LINE_AA)

    cv2.polylines(
        guide,
        [points.astype(np.int32)],
        True,
        outline_color,
        3,
        cv2.LINE_AA,
    )

    for index, (x, y) in enumerate(points.astype(int), start=1):
        cv2.circle(guide, (x, y), 13, (144, 138, 0), -1, cv2.LINE_AA)
        cv2.circle(guide, (x, y), 13, outline_color, 2, cv2.LINE_AA)
        cv2.putText(
            guide,
            str(index),
            (x - 5, y + 6),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            outline_color,
            2,
            cv2.LINE_AA,
        )

    return guide


def rectify_surface(master: np.ndarray, points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    width, height = quad_size(points)

    target = np.float32([
        [0, 0],
        [width - 1, 0],
        [width - 1, height - 1],
        [0, height - 1],
    ])

    matrix = cv2.getPerspectiveTransform(points, target)
    rectified = cv2.warpPerspective(
        master,
        matrix,
        (width, height),
        flags=cv2.INTER_LANCZOS4,
        borderMode=cv2.BORDER_REFLECT_101,
    )
    return rectified, matrix


def project_design(
    master: np.ndarray,
    design: np.ndarray,
    points: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    master_h, master_w = master.shape[:2]

    if design is None:
        raise HTTPException(400, "Unsupported design image")

    if design.ndim == 2:
        design = cv2.cvtColor(design, cv2.COLOR_GRAY2BGRA)
    elif design.shape[2] == 3:
        design = cv2.cvtColor(design, cv2.COLOR_BGR2BGRA)

    dh, dw = design.shape[:2]
    src = np.float32([
        [0, 0],
        [dw - 1, 0],
        [dw - 1, dh - 1],
        [0, dh - 1],
    ])

    matrix = cv2.getPerspectiveTransform(src, points)

    rgb = design[:, :, :3]
    alpha = design[:, :, 3]

    warped_rgb = cv2.warpPerspective(
        rgb,
        matrix,
        (master_w, master_h),
        flags=cv2.INTER_LANCZOS4,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0),
    )

    warped_alpha = cv2.warpPerspective(
        alpha,
        matrix,
        (master_w, master_h),
        flags=cv2.INTER_LANCZOS4,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0,
    )

    alpha_float = (warped_alpha.astype(np.float32) / 255.0)[..., None]
    composite = (
        warped_rgb.astype(np.float32) * alpha_float
        + master.astype(np.float32) * (1.0 - alpha_float)
    )
    composite = np.clip(composite, 0, 255).astype(np.uint8)

    return composite, warped_alpha, matrix


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse((STATIC / "index.html").read_text("utf-8"))


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
    path = DATA / project_id
    for folder in ["source", "design", "geometry", "render"]:
        (path / folder).mkdir(parents=True, exist_ok=True)

    state = {
        "id": project_id,
        "name": name,
        "created_at": now(),
        "updated_at": now(),
        "files": {},
        "surface": None,
    }
    save_state(path, state)
    return state


@app.get("/api/projects/{project_id}")
def get_project(project_id: str) -> dict:
    return load_state(project_dir(project_id))


@app.post("/api/projects/{project_id}/source")
async def upload_source(
    project_id: str,
    file: UploadFile = File(...),
) -> dict:
    path = project_dir(project_id)
    suffix = Path(file.filename or "source.jpg").suffix.lower() or ".jpg"
    target = path / "source" / f"master{suffix}"

    with target.open("wb") as output:
        shutil.copyfileobj(file.file, output)

    image = cv2.imread(str(target))
    if image is None:
        target.unlink(missing_ok=True)
        raise HTTPException(400, "Unsupported source image")

    h, w = image.shape[:2]
    state = load_state(path)
    state["files"]["source"] = str(target.relative_to(path)).replace("\\", "/")
    state["master_size"] = {"width": w, "height": h}
    state["surface"] = None
    save_state(path, state)
    return state


@app.post("/api/projects/{project_id}/design")
async def upload_design(
    project_id: str,
    file: UploadFile = File(...),
) -> dict:
    path = project_dir(project_id)
    suffix = Path(file.filename or "design.png").suffix.lower() or ".png"

    if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise HTTPException(400, "MVP supports PNG/JPG/WEBP design assets")

    target = path / "design" / f"design{suffix}"
    with target.open("wb") as output:
        shutil.copyfileobj(file.file, output)

    design = cv2.imread(str(target), cv2.IMREAD_UNCHANGED)
    if design is None:
        target.unlink(missing_ok=True)
        raise HTTPException(400, "Unsupported design image")

    state = load_state(path)
    state["files"]["design"] = str(target.relative_to(path)).replace("\\", "/")
    save_state(path, state)
    return state


@app.post("/api/projects/{project_id}/surface")
def save_surface(
    project_id: str,
    guides_json: str = Form(...),
) -> dict:
    path = project_dir(project_id)
    state = load_state(path)

    source_rel = state["files"].get("source")
    if not source_rel:
        raise HTTPException(409, "Upload source first")

    try:
        guides = json.loads(guides_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(400, "Invalid guides JSON") from exc

    master = cv2.imread(str(path / source_rel))
    if master is None:
        raise HTTPException(400, "Unsupported source image")

    h, w = master.shape[:2]
    points = validate_quad(guides.get("quad"), w, h)

    guide = make_guide(master, points)
    guide_path = path / "geometry" / "guide.png"
    cv2.imwrite(str(guide_path), guide)

    rectified, rectification_matrix = rectify_surface(master, points)
    rectified_path = path / "geometry" / "rectified.png"
    cv2.imwrite(str(rectified_path), rectified)

    width, height = quad_size(points)
    rect = np.float32([
        [0, 0],
        [width - 1, 0],
        [width - 1, height - 1],
        [0, height - 1],
    ])
    placement_matrix = cv2.getPerspectiveTransform(rect, points)

    surface = {
        "id": "surface_01",
        "type": "plane",
        "point_order": ["top_left", "top_right", "bottom_right", "bottom_left"],
        "quad": [
            {"x": float(x), "y": float(y)}
            for x, y in points
        ],
        "rectified_size": {"width": width, "height": height},
        "rectification_matrix": rectification_matrix.tolist(),
        "placement_matrix": placement_matrix.tolist(),
    }

    scene = {
        "version": "0.1",
        "project_id": project_id,
        "master_size": {"width": w, "height": h},
        "surface": surface,
    }

    scene_path = path / "geometry" / "scene.json"
    scene_path.write_text(
        json.dumps(scene, ensure_ascii=False, indent=2),
        "utf-8",
    )

    state["surface"] = surface
    state["files"]["guide"] = "geometry/guide.png"
    state["files"]["rectified"] = "geometry/rectified.png"
    state["files"]["scene"] = "geometry/scene.json"
    save_state(path, state)
    return state


@app.post("/api/projects/{project_id}/render")
def render_brand(project_id: str) -> dict:
    path = project_dir(project_id)
    state = load_state(path)

    source_rel = state["files"].get("source")
    design_rel = state["files"].get("design")
    surface = state.get("surface")

    if not source_rel:
        raise HTTPException(409, "Upload source first")
    if not design_rel:
        raise HTTPException(409, "Upload design first")
    if not surface:
        raise HTTPException(409, "Fix perspective surface first")

    master = cv2.imread(str(path / source_rel))
    design = cv2.imread(str(path / design_rel), cv2.IMREAD_UNCHANGED)

    points = np.float32([
        [p["x"], p["y"]]
        for p in surface["quad"]
    ])

    branded, mask, matrix = project_design(master, design, points)

    branded_path = path / "render" / "branded.png"
    mask_path = path / "render" / "design-mask.png"
    cv2.imwrite(str(branded_path), branded)
    cv2.imwrite(str(mask_path), mask)

    state["files"]["branded"] = "render/branded.png"
    state["files"]["mask"] = "render/design-mask.png"
    state["brand_matrix"] = matrix.tolist()
    save_state(path, state)
    return state


@app.get("/api/projects/{project_id}/file/{file_key}")
def get_file(project_id: str, file_key: str):
    path = project_dir(project_id)
    state = load_state(path)
    relative = state["files"].get(file_key)

    if not relative:
        raise HTTPException(404, "File not found")

    target = (path / relative).resolve()
    if path.resolve() not in target.parents:
        raise HTTPException(400, "Invalid path")

    return FileResponse(target)
