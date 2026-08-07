import json
from pathlib import Path

import pytest
from PIL import Image

from app.ai_engine import AIEngineError, OpenRouterImageEngine


def create_project_geometry(root: Path, approved: bool) -> tuple[Path, Path, Path]:
    project = root / "project-a"
    geometry_dir = project / "images" / "stages" / "geometry"
    internal_dir = project / "images" / "transport" / "environment"
    tile_dir = project / "images" / "stages" / "environment" / "outpaint-tiles" / "tile-01"
    geometry_dir.mkdir(parents=True)
    internal_dir.mkdir(parents=True)
    tile_dir.mkdir(parents=True)
    geometry = geometry_dir / "candidate.png"
    internal_plan = internal_dir / "auto-outpaint-plan.png"
    tile = tile_dir / "tile-base.png"

    image = Image.new("RGBA", (320, 240), (20, 30, 40, 255))
    image.paste((0, 0, 0, 0), (0, 0, 80, 240))
    image.save(geometry)
    Image.new("L", (320, 240), 0).save(internal_plan)
    Image.new("RGB", (160, 120), (80, 90, 100)).save(tile)

    state = {
        "id": "project-a",
        "pipeline": {"geometry": "approved" if approved else "ready"},
        "geometry": {"status": "approved" if approved else "review"},
        "assets": {
            "geometry_candidate": "images/stages/geometry/candidate.png",
        },
    }
    (project / "project.json").write_text(json.dumps(state), "utf-8")
    return geometry, internal_plan, tile


def test_exact_approved_geometry_is_accepted_without_project_mask(tmp_path):
    geometry, internal_plan, _ = create_project_geometry(tmp_path, approved=True)
    result = OpenRouterImageEngine()._approval_contract(geometry, internal_plan)
    assert result["approval_verified"] is True
    assert result["geometry_status"] == "approved"
    assert result["pipeline_status"] == "approved"
    assert result["environment_input_policy"] == "approved-geometry-only"
    assert result["internal_outpaint_tile"] is False


def test_internal_outpaint_tile_is_allowed_only_when_project_geometry_is_approved(tmp_path):
    _, internal_plan, tile = create_project_geometry(tmp_path, approved=True)
    result = OpenRouterImageEngine()._approval_contract(tile, internal_plan)
    assert result["approval_verified"] is True
    assert result["approval_source"] == "internal-derived-outpaint-tile"
    assert result["internal_outpaint_tile"] is True


def test_unapproved_geometry_is_blocked_before_provider_call(tmp_path):
    geometry, internal_plan, _ = create_project_geometry(tmp_path, approved=False)
    with pytest.raises(AIEngineError) as captured:
        OpenRouterImageEngine()._approval_contract(geometry, internal_plan)
    assert captured.value.details["provider_call_made"] is False
    assert captured.value.details["credits_spent"] is False
    assert captured.value.details["reason"] == "geometry_not_approved"
    assert "маск" not in str(captured.value).lower()


def test_internal_outpaint_tile_is_blocked_for_unapproved_project(tmp_path):
    _, internal_plan, tile = create_project_geometry(tmp_path, approved=False)
    with pytest.raises(AIEngineError) as captured:
        OpenRouterImageEngine()._approval_contract(tile, internal_plan)
    assert captured.value.details["reason"] == "geometry_not_approved"
    assert captured.value.details["internal_outpaint_tile"] is False
