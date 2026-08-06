from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_generation_polling_retries_transient_codespaces_errors():
    bridge = (ROOT / "ui_single_window" / "async-generation-bridge.js").read_text("utf-8")
    for status in ("408", "425", "429", "502", "503", "504"):
        assert status in bridge
    assert "TRANSIENT_HTTP_STATUSES" in bridge
    assert "continue;" in bridge
    assert "generation-status" in bridge
    assert "Запрос не будет продублирован" in bridge


def test_browser_cache_key_for_resilient_generation_client():
    html = (ROOT / "ui_single_window" / "index.html").read_text("utf-8")
    build = (ROOT / "build.sh").read_text("utf-8")
    start = (ROOT / "start.sh").read_text("utf-8")

    assert "resilient-fullframe-0806" in html
    assert "TRANSIENT_HTTP_STATUSES" in build
    assert "TRANSIENT_HTTP_STATUSES" in start
    assert "async-generation-bridge.js" in build
    assert "async-generation-bridge.js" in start
