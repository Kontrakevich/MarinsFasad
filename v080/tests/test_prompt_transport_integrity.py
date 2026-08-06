from pathlib import Path

from PIL import Image

from app.ai_engine import OpenRouterImageEngine
from app.prompt_engine import (
    FINAL_COMMAND_MARKER,
    OPERATOR_PROMPT_MARKER,
    PromptContext,
    PromptEngine,
)


def test_ui_compiled_prompt_is_sent_to_nano_banana_verbatim(tmp_path: Path):
    compiled = PromptEngine().compile(
        PromptContext(
            stage="environment",
            master_prompt="ignored",
            comments=[
                "Убрать только белый автомобиль справа.",
                "На его месте продолжить покрытие парковки.",
            ],
            approved_geometry_asset="images/stages/geometry/candidate.png",
            approved_mask_asset="images/stages/geometry/outpaint-mask.png",
        ),
        tmp_path,
    )

    geometry = tmp_path / "geometry.png"
    mask = tmp_path / "mask.png"
    Image.new("RGB", (64, 48), (80, 90, 100)).save(geometry, format="PNG")
    Image.new("L", (64, 48), 0).save(mask, format="PNG")

    engine = OpenRouterImageEngine()
    payload = engine._build_payload(
        prompt=compiled["prompt"],
        geometry_image=geometry,
        outpaint_mask=mask,
        provider_size=(1024, 1024),
    )

    assert payload["model"] == "google/gemini-2.5-flash-image"
    assert payload["prompt"] == compiled["prompt"]
    assert OPERATOR_PROMPT_MARKER in payload["prompt"]
    assert FINAL_COMMAND_MARKER in payload["prompt"]
    assert "Убрать только белый автомобиль справа." in payload["prompt"]
    assert "На его месте продолжить покрытие парковки." in payload["prompt"]
    assert compiled["prompt_transport_policy"] == "ui-compiled-prompt-sent-verbatim"
    assert compiled["prompt_sha256"]


def test_operator_prompt_is_primary_and_repeated_as_final_command(tmp_path: Path):
    compiled = PromptEngine().compile(
        PromptContext(
            stage="environment",
            master_prompt="ignored",
            comments=["Заменить только вывеску над входом."],
        ),
        tmp_path,
    )

    prompt = compiled["prompt"]
    first_instruction = prompt.index("Заменить только вывеску над входом.")
    final_marker = prompt.index(FINAL_COMMAND_MARKER)
    last_instruction = prompt.rindex("Заменить только вывеску над входом.")

    assert prompt.startswith(OPERATOR_PROMPT_MARKER)
    assert first_instruction < final_marker < last_instruction
    assert "The operator prompt is the primary generation task." in prompt
    assert "Do not return a result that only fills the mask" in prompt
