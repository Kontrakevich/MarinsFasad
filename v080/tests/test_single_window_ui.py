from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_single_window_workspace_structure():
    html = (ROOT / "ui_single_window" / "index.html").read_text("utf-8")
    for element_id in (
        'pipeline',
        'project-list',
        'geometry-canvas',
        'inspector-stage',
        'timeline-list',
        'candidate-list',
    ):
        assert f'id="{element_id}"' in html


def test_perspective_grid_is_connected_to_v080_api():
    js = (ROOT / "ui_single_window" / "app-v080.js").read_text("utf-8")
    assert "function bilinear" in js
    assert "geometry/apply-grid" in js
    assert "geometry/approve" in js
    assert "geo.history" in js
    assert "geo.future" in js


def test_build_uses_single_window_sources():
    build = (ROOT / "build.sh").read_text("utf-8")
    assert "ui_single_window/index.html" in build
    assert "ui_single_window/styles.css" in build
    assert "ui_single_window/app-v080.js" in build
