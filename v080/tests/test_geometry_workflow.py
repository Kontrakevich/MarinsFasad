from __future__ import annotations

import io
import json

from fastapi.testclient import TestClient
from PIL import Image

from app.main import app

client = TestClient(app)


def sample_image(width: int = 800, height: int = 600) -> bytes:
    image = Image.new("RGB", (width, height), (220, 225, 228))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def create_with_source() -> dict:
    created = client.post("/api/projects", data={"name": "Geometry workflow"})
    assert created.status_code == 200
    project_id = created.json()["id"]
    uploaded = client.post(
        f"/api/projects/{project_id}/source",
        files={"file": ("source.png", sample_image(), "image/png")},
    )
    assert uploaded.status_code == 200
    return uploaded.json()


def test_apply_grid_preserves_canvas_and_records_missing_regions_in_alpha():
    state = create_with_source()
    project_id = state["id"]
    quad = [
        {"x": 80, "y": 50},
        {"x": 730, "y": 70},
        {"x": 760, "y": 560},
        {"x": 45, "y": 540},
    ]
    response = client.post(
        f"/api/projects/{project_id}/geometry/apply-grid",
        data={"quad_json": json.dumps(quad)},
    )
    assert response.status_code == 200, response.text
    state = response.json()
    assert state["master_canvas"] == {"width": 800, "height": 600}
    assert state["geometry"]["canvas_preserved"] is True
    assert state["geometry"]["missing_pixels"] > 0
    assert state["geometry"]["missing_ratio"] > 0
    assert state["geometry"]["outpaint_required"] is True
    assert state["geometry"]["outpaint_detection"] == "automatic-from-candidate-transparency"
    assert state["assets"]["geometry_candidate"].endswith("candidate.png")
    assert "geometry_outpaint_mask" not in state["assets"]

    candidate = client.get(f"/api/projects/{project_id}/assets/geometry_candidate")
    assert candidate.status_code == 200
    with Image.open(io.BytesIO(candidate.content)) as image:
        assert image.size == (800, 600)
        assert image.mode == "RGBA"
        alpha = image.getchannel("A")
        assert alpha.getextrema()[0] == 0
        assert alpha.getextrema()[1] == 255

    obsolete = client.get(f"/api/projects/{project_id}/assets/geometry_outpaint_mask")
    assert obsolete.status_code == 404


def test_geometry_points_are_clamped_inside_canvas():
    state = create_with_source()
    project_id = state["id"]
    quad = [
        {"x": -20, "y": -10},
        {"x": 900, "y": 30},
        {"x": 830, "y": 700},
        {"x": -50, "y": 650},
    ]
    response = client.post(
        f"/api/projects/{project_id}/geometry/apply-grid",
        data={"quad_json": json.dumps(quad)},
    )
    assert response.status_code == 200, response.text
    points = response.json()["geometry"]["quad"]
    assert all(0 <= point["x"] <= 799 for point in points)
    assert all(0 <= point["y"] <= 599 for point in points)


def test_geometry_approve_unlocks_environment_without_separate_mask():
    state = create_with_source()
    project_id = state["id"]
    quad = [
        {"x": 70, "y": 40},
        {"x": 730, "y": 65},
        {"x": 760, "y": 560},
        {"x": 45, "y": 535},
    ]
    applied = client.post(
        f"/api/projects/{project_id}/geometry/apply-grid",
        data={"quad_json": json.dumps(quad)},
    )
    assert applied.status_code == 200
    assert applied.json()["geometry"]["missing_pixels"] > 0
    approved = client.post(f"/api/projects/{project_id}/geometry/approve")
    assert approved.status_code == 200
    state = approved.json()
    assert state["pipeline"]["geometry"] == "approved"
    assert state["pipeline"]["environment"] == "ready"
    assert state["geometry"]["status"] == "approved"
    assert "geometry_outpaint_mask" not in state["assets"]
    history = client.get(f"/api/projects/{project_id}/history").json()
    approved_events = [event for event in history if event["type"] == "GeometryApproved"]
    assert approved_events
    assert approved_events[0]["payload"]["outpaint_detection"] == "automatic-from-approved-geometry"


def test_geometry_revision_requires_comment():
    state = create_with_source()
    project_id = state["id"]
    response = client.post(
        f"/api/projects/{project_id}/geometry/revise",
        data={"comment": ""},
    )
    assert response.status_code == 422
