import json
from pathlib import Path

import pytest
from PIL import Image

from app.ai_engine import AIEngineError, OpenRouterImageEngine


def create_project_geometry(root: Path, approved: bool) -> Path:
    project = root / "project-a"
    geometry_dir = project / "images" / "stages" / "geometry"
    geometry_dir.mkdir(parents=True)
    geometry = geometry_dir / "candidate.png"

    image = Image.new("RGBA", (320, 240), (20, 30, 40, 255))
    image.paste((0, 0, 0, 0), (0, 0, 80, 240))
    image.save(geometry)

    state = {
        "id": "project-a",
        "pipeline": {"geometry": "approved" if approved else "ready"},
        "geometry": {"status": "approved" if approved else "review"},
        "assets": {"geometry_candidate": "images/stages/geometry/candidate.png"},
    }
    (project / "project.json").write_text(json.dumps(state), "utf-8")
    return geometry


def test_exact_approved_geometry_is_accepted_without_extra_project_asset(tmp_path):
    geometry = create_project_geometry(tmp_path, approved=True)
    result = OpenRouterImageEngine()._approval_contract(geometry)
    assert result["approval_verified"] is True
    assert result["geometry_status"] == "approved"
    assert result["pipeline_status"] == "approved"
    assert result["environment_input_policy"] == "approved-geometry-only"


def test_unapproved_geometry_is_blocked_before_provider_call(tmp_path):
    geometry = create_project_geometry(tmp_path, approved=False)
    with pytest.raises(AIEngineError) as captured:
        OpenRouterImageEngine()._approval_contract(geometry)
    assert captured.value.details["provider_call_made"] is False
    assert captured.value.details["credits_spent"] is False
    assert captured.value.details["reason"] == "geometry_not_approved"
