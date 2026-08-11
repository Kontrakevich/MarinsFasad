from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_generation_polling_retries_transient_codespaces_errors():
    bridge = (ROOT / "ui_single_window" / "async-generation-bridge.js").read_text("utf-8")
    for status in ("408", "425", "429", "502", "503", "504"):
        assert status in bridge
    assert "TRANSIENT_HTTP_STATUSES" in bridge
    assert "generation-status" in bridge
    assert "Запрос не будет продублирован" in bridge


def test_generation_status_404_recovers_without_duplicate_start():
    bridge = (ROOT / "ui_single_window" / "async-generation-bridge.js").read_text("utf-8")
    assert "recoverStatusFromProject" in bridge
    assert "result.status === 404" in bridge
    assert "statusResult.status === 404" in bridge
    assert "normalizeProjectGeneration" in bridge
    assert "Never duplicate the generation request" in bridge


def test_generation_polling_is_detached_from_button_busy_state():
    bridge = (ROOT / "ui_single_window" / "async-generation-bridge.js").read_text("utf-8")
    assert "activePolls" in bridge
    assert "startDetachedPolling" in bridge
    assert "projectSnapshotResponse" in bridge
    assert "Do not keep the UI's busy() promise open" in bridge
    assert "startDetachedPolling(statusUrl, details.projectId)" in bridge
    assert "const snapshot = await projectSnapshotResponse(details.projectId)" in bridge


def test_build_replaces_frontend_cache_key_for_console_only_workspace():
    build = (ROOT / "build.sh").read_text("utf-8")
    start = (ROOT / "start.sh").read_text("utf-8")
    for script in (build, start):
        assert "system1-console-all-3450" in script
        assert "command-console-patch.js" in script
        assert "lower-console-patch.js" in script
        assert "minimum-font-patch.js" in script


def test_lower_workspace_moves_into_command_console():
    patch = (ROOT / "ui_single_window" / "lower-console-patch.js").read_text("utf-8")
    assert ".bottom-pane{display:none!important}" in patch
    assert "commandHistory" in patch
    assert "commandCandidates" in patch
    assert "commandEvents" in patch
    for command in ("history", "candidates", "events"):
        assert command in patch


def test_minimum_font_is_ten_points_for_existing_and_dynamic_ui():
    patch = (ROOT / "ui_single_window" / "minimum-font-patch.js").read_text("utf-8")
    assert "const MIN_FONT_PT = 10" in patch
    assert "MIN_FONT_PT * 96 / 72" in patch
    assert "MutationObserver" in patch
    assert "font-size" in patch


def test_quality_build_keeps_resilient_generation_bridge_and_workspace_controls():
    build = (ROOT / "build.sh").read_text("utf-8")
    start = (ROOT / "start.sh").read_text("utf-8")
    assert "async-generation-bridge.js" in build
    assert "async-generation-bridge.js" in start
    assert "hybrid-mode-patch.js" in build
    assert "hybrid-mode-patch.js" in start
    assert "workspace-controls-patch.js" in build
    assert "workspace-controls-patch.js" in start
    assert "command-console-patch.js" in build
    assert "command-console-patch.js" in start
    assert "lower-console-patch.js" in build
    assert "lower-console-patch.js" in start
    assert "minimum-font-patch.js" in build
    assert "minimum-font-patch.js" in start
    assert "nano_banana_prompt_adapter" in build
    assert "nano_banana_prompt_adapter" in start
