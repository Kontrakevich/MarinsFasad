from pathlib import Path

from app.prompt_engine import PromptContext, PromptEngine
from app.system_prompts import PROMPT_CONTRACT_VERSION


def test_environment_prompt_requests_selective_nano_banana_edit(tmp_path: Path):
    result = PromptEngine().compile(
        PromptContext(
            stage="environment",
            master_prompt="ignored for environment",
            skill="Regenerate the whole image.",
            comments=["Заменить только автомобиль справа на дерево."],
            approved_geometry_asset="images/stages/geometry/candidate.png",
            approved_mask_asset="images/stages/geometry/outpaint-mask.png",
        ),
        tmp_path,
    )

    prompt = result["prompt"]
    assert result["contract_version"] == PROMPT_CONTRACT_VERSION
    assert result["generation_mode"] == "selective-edit"
    assert result["mask_role"] == "mandatory-edit-reference"
    assert result["provider_model"] == "google/gemini-2.5-flash-image"
    assert result["pixel_preservation"] == "outside-edit-area-exact"
    assert "selective image editing only" in prompt
    assert "Do not regenerate" in prompt
    assert "Every unaffected pixel must remain identical" in prompt
    assert "Regenerate the whole image." not in prompt
    assert "Заменить только автомобиль справа на дерево." in prompt
