from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_build_does_not_call_live_openrouter_during_pytest() -> None:
    build = (ROOT / "build.sh").read_text("utf-8")
    requirements = (ROOT / "requirements.txt").read_text("utf-8")

    assert 'OPENROUTER_API_KEY=""' in build
    assert 'OPENROUTER_IMAGE_MODEL="must-be-ignored/test-model"' in build
    assert 'google/gemini-2.5-flash-image' in build
    assert "--timeout=60" in build
    assert "--timeout-method=thread" in build
    assert "pytest-timeout" in requirements
