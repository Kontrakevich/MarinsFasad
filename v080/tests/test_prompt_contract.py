from app.prompt_engine import PromptContext, PromptEngine
from app.system_prompts import ENVIRONMENT_SYSTEM_PROMPT, PROMPT_CONTRACT_VERSION


def test_environment_compiled_prompt_contains_hybrid_image_edit_contract(tmp_path):
    result = PromptEngine().compile(
        PromptContext(
            stage="environment",
            master_prompt="generic fallback",
            skill="Regenerate everything.",
            comments=[
                "Убрать столбы и провода.",
                "Сделать облачную погоду.",
            ],
            approved_geometry_asset="images/stages/geometry/candidate.png",
        ),
        tmp_path,
    )

    assert result["system_prompt"] == ENVIRONMENT_SYSTEM_PROMPT
    assert result["contract_version"] == PROMPT_CONTRACT_VERSION
    assert ENVIRONMENT_SYSTEM_PROMPT in result["prompt"]
    assert "Убрать столбы и провода." in result["prompt"]
    assert "Сделать облачную погоду." in result["prompt"]
    assert "APPROVED CORRECTED GEOMETRY" in result["prompt"]
    assert "SEMANTIC EDIT PRIORITY" in result["prompt"]
    assert "AUTOMATIC OUTPAINT" in result["prompt"]
    assert "GENERATION MODE\nHYBRID" in result["prompt"]
    assert "weather" in result["prompt"].lower()
    assert "overhead wires" in result["prompt"].lower()
    assert "mask" not in result["prompt"].lower()
    assert result["generation_mode"] == "hybrid"
    assert result["outpaint_detection"] == "automatic-from-approved-geometry"
    assert result["provider_model"] == "google/gemini-2.5-flash-image"
    assert result["pixel_preservation"] == "architecture-geometry-preserved-by-prompt"
    assert result["system_prompt_sha256"]
    assert (tmp_path / result["file"]).is_file()


def test_mode_control_comment_is_not_exposed_as_operator_instruction(tmp_path):
    result = PromptEngine().compile(
        PromptContext(
            stage="environment",
            master_prompt="ignored",
            comments=[
                "__MARINS_GENERATION_MODE__:edit",
                "Удалить провода над зданием.",
            ],
        ),
        tmp_path,
    )
    assert result["generation_mode"] == "edit"
    assert "__MARINS_GENERATION_MODE__" not in result["prompt"]
    assert "GENERATION MODE\nEDIT" in result["prompt"]
    assert "Удалить провода над зданием." in result["prompt"]
    assert result["operator_comment_count"] == 1
