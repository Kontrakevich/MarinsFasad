from app.prompt_engine import PromptContext, PromptEngine
from app.system_prompts import ENVIRONMENT_SYSTEM_PROMPT, PROMPT_CONTRACT_VERSION


def test_environment_compiled_prompt_contains_authoritative_system_contract(tmp_path):
    result = PromptEngine().compile(
        PromptContext(
            stage="environment",
            master_prompt="generic fallback",
            skill="Fill the approved outpaint area.",
            comments=["Use a clear daytime sky."],
        ),
        tmp_path,
    )

    assert result["system_prompt"] == ENVIRONMENT_SYSTEM_PROMPT
    assert result["contract_version"] == PROMPT_CONTRACT_VERSION
    assert ENVIRONMENT_SYSTEM_PROMPT in result["prompt"]
    assert "Use a clear daytime sky." in result["prompt"]
    assert "corrected and approved geometry" in result["prompt"]
    assert result["system_prompt_sha256"]
    assert (tmp_path / result["file"]).is_file()
