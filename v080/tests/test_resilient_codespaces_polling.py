from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_generation_polling_retries_transient_codespaces_errors():
    bridge = (ROOT / "ui_single_window" / "async-generation-bridge.js").read_text("utf-8")
    for status in ("408", "425", "429", "502", "503", "504"):
        assert status in bridge
    assert "TRANSIENT_HTTP_STATUSES" in bridge
    assert "generation-status" in bridge
    assert "Запрос не будет продублирован" in bridge


def test_generation_status_404_recovers_from_persisted_project_without_duplicate_start():
    bridge = (ROOT / "ui_single_window" / "async-generation-bridge.js").read_text("utf-8")
    assert "recoverStatusFromProject" in bridge
    assert "result.status === 404" in bridge
    assert "statusResult.status === 404" in bridge
    assert "normalizeProjectGeneration" in bridge
    assert "Never duplicate the generation request" in bridge
    assert "return pollStatus(statusUrl, details.projectId" in bridge


def test_frontend_cache_key_changes_with_status_recovery_bridge():
    index = (ROOT / "ui_single_window" / "index.html").read_text("utf-8")
    assert "system1-status-recovery-3410" in index
    assert "app-v080.js?v=hybrid-two-pass-3200-system1-status-recovery-3410" in index


def test_quality_build_keeps_resilient_generation_bridge():
    build = (ROOT / "build.sh").read_text("utf-8")
    start = (ROOT / "start.sh").read_text("utf-8")
    assert "quality-outpaint-3400" in build
    assert "quality-outpaint-3400" in start
    assert "async-generation-bridge.js" in build
    assert "async-generation-bridge.js" in start
    assert "hybrid-mode-patch.js" in build
    assert "hybrid-mode-patch.js" in start
