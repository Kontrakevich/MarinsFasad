from pathlib import Path

from app.prompt_engine import PromptContext, PromptEngine
from app.system_prompts import PROMPT_CONTRACT_VERSION


def test_environment_prompt_requests_geometry_only_outpaint_and_local_edit(tmp_path: Path):
    result = PromptEngine().compile(
        PromptContext(
            stage="environment",
            master_prompt="ignored for environment",
            skill="Regenerate the whole image.",
            comments=["Заменить только автомобиль справа на дерево."],
            approved_geometry_asset="images/stages/geometry/candidate.png",
        ),
        tmp_path,
    )

    prompt = result["prompt"]
    assert result["contract_version"] == PROMPT_CONTRACT_VERSION
    assert result["generation_mode"] == "automatic-outpaint-and-selective-edit"
    assert result["outpaint_detection"] == "automatic-from-approved-geometry"
    assert result["provider_model"] == "google/gemini-2.5-flash-image"
    assert result["pixel_preservation"] == "existing-visible-pixels-exact"
    assert "AUTOMATIC OUTPAINT" in prompt
    assert "Do not regenerate" in prompt
    assert "only approved project input" in prompt
    assert "Regenerate the whole image." not in prompt
    assert "Заменить только автомобиль справа на дерево." in prompt
    assert "mask" not in prompt.lower()
