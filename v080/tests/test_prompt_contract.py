from app.prompt_engine import PromptContext, PromptEngine
from app.system_prompts import ENVIRONMENT_SYSTEM_PROMPT, PROMPT_CONTRACT_VERSION


def test_environment_compiled_prompt_contains_hybrid_skill_and_quality_contract(tmp_path):
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
    assert "SEMANTIC IMAGE EDITING" in result["prompt"]
    assert "SCENE-WIDE LIGHTING" in result["prompt"]
    assert "AUTOMATIC OUTPAINT" in result["prompt"]
    assert "FULL PROMPT CONTEXT RULE" in result["prompt"]
    assert "GENERATION MODE\nHYBRID" in result["prompt"]
    assert "GENERATION QUALITY\nHIGH" in result["prompt"]
    assert "complete operator prompt" in result["prompt"].lower()
    assert "overhead wires" in result["prompt"].lower()
    assert "mask" not in result["prompt"].lower()
    assert result["generation_mode"] == "hybrid"
    assert result["generation_quality"] == "high"
    assert result["outpaint_detection"] == "automatic-from-approved-geometry"
    assert result["provider_model"] == "google/gemini-2.5-flash-image"
    assert result["pixel_preservation"] == "geometry-preserved-requested-edits-retained"
    assert result["full_prompt_context_policy"] == "all-operator-instructions-propagate-to-every-pass"
    assert result["system_prompt_sha256"]
    assert (tmp_path / result["file"]).is_file()


def test_mode_and_quality_service_comments_are_not_operator_instructions(tmp_path):
    result = PromptEngine().compile(
        PromptContext(
            stage="environment",
            master_prompt="ignored",
            comments=[
                "__MARINS_GENERATION_MODE__:edit",
                "__MARINS_GENERATION_QUALITY__:max",
                "Удалить провода над зданием.",
            ],
        ),
        tmp_path,
    )
    assert result["generation_mode"] == "edit"
    assert result["generation_quality"] == "max"
    assert "__MARINS_GENERATION_MODE__" not in result["prompt"]
    assert "__MARINS_GENERATION_QUALITY__" not in result["prompt"]
    assert "GENERATION MODE\nEDIT" in result["prompt"]
    assert "GENERATION QUALITY\nMAX" in result["prompt"]
    assert "Удалить провода над зданием." in result["prompt"]
    assert result["operator_comment_count"] == 1


def test_relight_allows_full_frame_photometric_change_without_pixel_restore(tmp_path):
    result = PromptEngine().compile(
        PromptContext(
            stage="environment",
            master_prompt="ignored",
            comments=[
                "__MARINS_GENERATION_MODE__:relight",
                "Сделать поздний вечер, включить тёплый свет в окнах, после дождя.",
            ],
        ),
        tmp_path,
    )
    prompt = result["prompt"]
    assert result["generation_mode"] == "relight"
    assert result["pixel_preservation"] == "geometry-preserved-photometry-may-change"
    assert "GENERATION MODE\nRELIGHT" in prompt
    assert "RELIGHT / NEW LIGHTING SKILL" in prompt
    assert "Do NOT restore original source pixels after relighting" in prompt
    assert "Geometry preservation does not mean pixel preservation" in prompt


def test_outpaint_uses_full_prompt_context_but_preserves_valid_pixels(tmp_path):
    result = PromptEngine().compile(
        PromptContext(
            stage="environment",
            master_prompt="ignored",
            comments=[
                "__MARINS_GENERATION_MODE__:outpaint",
                "__MARINS_GENERATION_QUALITY__:high",
                "Продолжить мокрый асфальт и вечернее освещение в отсутствующих областях.",
            ],
        ),
        tmp_path,
    )
    prompt = result["prompt"]
    assert result["generation_mode"] == "outpaint"
    assert result["generation_quality"] == "high"
    assert result["pixel_preservation"] == "existing-visible-pixels-exact"
    assert "GENERATION MODE\nOUTPAINT" in prompt
    assert "GENERATION QUALITY\nHIGH" in prompt
    assert "Existing visible pixels are immutable" in prompt
    assert "FULL OPERATOR PROMPT remains mandatory scene context" in prompt
    assert "Продолжить мокрый асфальт" in prompt
