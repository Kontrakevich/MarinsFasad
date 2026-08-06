from app.prompt_engine import PromptContext, PromptEngine
from app.system_prompts import ENVIRONMENT_SYSTEM_PROMPT, PROMPT_CONTRACT_VERSION


def test_environment_compiled_prompt_contains_geometry_only_outpaint_contract(tmp_path):
    result = PromptEngine().compile(
        PromptContext(
            stage="environment",
            master_prompt="generic fallback",
            skill="Regenerate everything.",
            comments=["Заменить только автомобиль справа на дерево."],
            approved_geometry_asset="images/stages/geometry/candidate.png",
        ),
        tmp_path,
    )

    assert result["system_prompt"] == ENVIRONMENT_SYSTEM_PROMPT
    assert result["contract_version"] == PROMPT_CONTRACT_VERSION
    assert ENVIRONMENT_SYSTEM_PROMPT in result["prompt"]
    assert "Заменить только автомобиль справа на дерево." in result["prompt"]
    assert "APPROVED IMMUTABLE BASE" in result["prompt"]
    assert "AUTOMATIC OUTPAINT" in result["prompt"]
    assert "only approved project input" in result["prompt"]
    assert "mask" not in result["prompt"].lower()
    assert result["generation_mode"] == "automatic-outpaint-and-selective-edit"
    assert result["outpaint_detection"] == "automatic-from-approved-geometry"
    assert result["provider_model"] == "google/gemini-2.5-flash-image"
    assert result["system_prompt_sha256"]
    assert (tmp_path / result["file"]).is_file()
