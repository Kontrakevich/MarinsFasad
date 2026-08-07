from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_generation_polling_retries_transient_codespaces_errors():
    bridge = (ROOT / "ui_single_window" / "async-generation-bridge.js").read_text("utf-8")
    for status in ("408", "425", "429", "502", "503", "504"):
        assert status in bridge
    assert "TRANSIENT_HTTP_STATUSES" in bridge
    assert "generation-status" in bridge
    assert "Запрос не будет продублирован" in bridge


def test_skill_build_keeps_resilient_generation_bridge():
    build = (ROOT / "build.sh").read_text("utf-8")
    start = (ROOT / "start.sh").read_text("utf-8")
    assert "skill-contracts-3300" in build
    assert "skill-contracts-3300" in start
    assert "async-generation-bridge.js" in build
    assert "async-generation-bridge.js" in start
    assert "hybrid-mode-patch.js" in build
    assert "hybrid-mode-patch.js" in start
