from pathlib import Path

from app.prompt_engine import PromptContext, PromptEngine
from app.system_prompts import PROMPT_CONTRACT_VERSION


def test_environment_prompt_requests_full_frame_and_marks_mask_qc_only(tmp_path: Path):
    result = PromptEngine().compile(
        PromptContext(
            stage="environment",
            master_prompt="ignored for environment",
            skill="Generate only masked pixels and preserve all opaque pixels.",
            comments=["Сделать ясное дневное небо."],
            approved_geometry_asset="images/stages/geometry/candidate.png",
            approved_mask_asset="images/stages/geometry/outpaint-mask.png",
        ),
        tmp_path,
    )

    prompt = result["prompt"]
    assert result["contract_version"] == PROMPT_CONTRACT_VERSION
    assert result["generation_mode"] == "full-frame-reference"
    assert result["mask_role"] == "quality-control-only"
    assert "Regenerate the entire canvas" in prompt
    assert "Do not limit generation" in prompt
    assert "quality control only" in prompt
    assert "Generate only masked pixels and preserve all opaque pixels." not in prompt
    assert "Сделать ясное дневное небо." in prompt
