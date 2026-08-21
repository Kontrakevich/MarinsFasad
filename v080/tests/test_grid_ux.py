from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_grid_zoom_step_is_five_percent() -> None:
    patch = (ROOT / "ui_single_window" / "grid-ux-patch.js").read_text("utf-8")
    assert "const ZOOM_STEP = 0.05" in patch
    assert "changeZoom(ZOOM_STEP)" in patch
    assert "changeZoom(-ZOOM_STEP)" in patch
    assert "0.25" not in patch


def test_grid_requests_fullscreen_for_geometry_work() -> None:
    patch = (ROOT / "ui_single_window" / "grid-ux-patch.js").read_text("utf-8")
    build = (ROOT / "build.sh").read_text("utf-8")
    start = (ROOT / "start.sh").read_text("utf-8")

    assert "function requestGridFullscreen" in patch
    assert "viewer.requestFullscreen" in patch
    assert 'button[data-view="grid"]' in patch
    assert 'button[data-stage="geometry"]' in patch
    assert "pointerdown" in patch
    assert "grid-ux-patch.js" in build
    assert "grid-ux-patch.js" in start
