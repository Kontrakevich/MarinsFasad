from pathlib import Path

from app.prompt_engine import PromptContext, PromptEngine
from app.system_prompts import PROMPT_CONTRACT_VERSION


def test_hybrid_prompt_allows_strong_environment_edit_without_geometry_drift(tmp_path: Path):
    result = PromptEngine().compile(
        PromptContext(
            stage="environment",
            master_prompt="ignored for environment",
            skill="Regenerate the whole image.",
            comments=[
                "Убрать столбы и провода.",
                "Сделать пасмурную погоду и мокрый асфальт.",
            ],
            approved_geometry_asset="images/stages/geometry/candidate.png",
        ),
        tmp_path,
    )

    prompt = result["prompt"]
    assert result["contract_version"] == PROMPT_CONTRACT_VERSION
    assert result["generation_mode"] == "hybrid"
    assert result["outpaint_detection"] == "automatic-from-approved-geometry"
    assert result["provider_model"] == "google/gemini-2.5-flash-image"
    assert result["pixel_preservation"] == "geometry-preserved-requested-edits-retained"
    assert "GENERATION MODE\nHYBRID" in prompt
    assert "scene-wide lighting" in prompt.lower()
    assert "poles" in prompt.lower()
    assert "overhead wires" in prompt.lower()
    assert "Regenerate the whole image." not in prompt
    assert "Убрать столбы и провода." in prompt
    assert "Сделать пасмурную погоду и мокрый асфальт." in prompt
    assert "mask" not in prompt.lower()


def test_relight_mode_allows_full_frame_photometric_change(tmp_path: Path):
    result = PromptEngine().compile(
        PromptContext(
            stage="environment",
            master_prompt="ignored",
            comments=[
                "__MARINS_GENERATION_MODE__:relight",
                "Сделать вечернее освещение и тёплый свет в окнах.",
            ],
        ),
        tmp_path,
    )
    assert result["generation_mode"] == "relight"
    assert result["pixel_preservation"] == "geometry-preserved-photometry-may-change"
    assert "GENERATION MODE\nRELIGHT" in result["prompt"]
    assert "Do NOT restore original source pixels after relighting" in result["prompt"]


def test_outpaint_mode_restores_strict_pixel_preservation(tmp_path: Path):
    result = PromptEngine().compile(
        PromptContext(
            stage="environment",
            master_prompt="ignored",
            comments=["__MARINS_GENERATION_MODE__:outpaint"],
        ),
        tmp_path,
    )
    assert result["generation_mode"] == "outpaint"
    assert result["pixel_preservation"] == "existing-visible-pixels-exact"
    assert "GENERATION MODE\nOUTPAINT" in result["prompt"]
    assert "Existing visible pixels are immutable" in result["prompt"]
