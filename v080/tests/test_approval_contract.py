import json
from pathlib import Path

import pytest
from PIL import Image

from app.ai_engine import AIEngineError, OpenRouterImageEngine


def create_project_assets(root: Path, approved: bool) -> tuple[Path, Path]:
    project = root / "project-a"
    geometry_dir = project / "images" / "stages" / "geometry"
    geometry_dir.mkdir(parents=True)
    geometry = geometry_dir / "candidate.png"
    mask = geometry_dir / "outpaint-mask.png"

    Image.new("RGBA", (320, 240), (20, 30, 40, 255)).save(geometry)
    edit_mask = Image.new("L", (320, 240), 0)
    edit_mask.paste(255, (0, 0, 80, 240))
    edit_mask.save(mask)

    state = {
        "id": "project-a",
        "pipeline": {"geometry": "approved" if approved else "ready"},
        "geometry": {"status": "approved" if approved else "review"},
        "assets": {
            "geometry_candidate": "images/stages/geometry/candidate.png",
            "geometry_outpaint_mask": "images/stages/geometry/outpaint-mask.png",
        },
    }
    (project / "project.json").write_text(json.dumps(state), "utf-8")
    return geometry, mask


def test_exact_approved_geometry_and_mask_are_accepted(tmp_path):
    geometry, mask = create_project_assets(tmp_path, approved=True)
    result = OpenRouterImageEngine()._approval_contract(geometry, mask)
    assert result["approval_verified"] is True
    assert result["geometry_status"] == "approved"
    assert result["pipeline_status"] == "approved"


def test_unapproved_geometry_is_blocked_before_provider_call(tmp_path):
    geometry, mask = create_project_assets(tmp_path, approved=False)
    with pytest.raises(AIEngineError) as captured:
        OpenRouterImageEngine()._approval_contract(geometry, mask)
    assert captured.value.details["provider_call_made"] is False
    assert captured.value.details["credits_spent"] is False
    assert captured.value.details["reason"] == "geometry_not_approved"
