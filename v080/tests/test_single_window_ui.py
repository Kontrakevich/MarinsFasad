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
        'split-before-label',
        'split-after-label',
    ):
        assert f'id="{element_id}"' in html


def test_workspace_views_are_stage_specific():
    html = (ROOT / "ui_single_window" / "index.html").read_text("utf-8")
    js = (ROOT / "ui_single_window" / "app-v080.js").read_text("utf-8")

    for view in ('original', 'grid', 'result', 'generation', 'split'):
        assert f'data-view="{view}"' in html

    assert 'data-view="overlay"' not in html
    assert 'overlay-view' not in html
    assert "source: ['original']" in js
    assert "geometry: ['grid', 'result', 'split']" in js
    assert "environment: ['original', 'result', 'generation', 'split']" in js
    assert "beforeLabel: 'РЕЗУЛЬТАТ'" in js
    assert "afterLabel: 'ГЕНЕРАЦИЯ'" in js


def test_perspective_grid_is_connected_to_v080_api():
    js = (ROOT / "ui_single_window" / "app-v080.js").read_text("utf-8")
    assert "function bilinear" in js
    assert "geometry/apply-grid" in js
    assert "geometry/approve" in js
    assert "geo.history" in js
    assert "geo.future" in js


def test_background_generation_bridge_and_ui_patches_are_built_in_order():
    bridge = (ROOT / "ui_single_window" / "async-generation-bridge.js").read_text("utf-8")
    build = (ROOT / "build.sh").read_text("utf-8")
    start = (ROOT / "start.sh").read_text("utf-8")

    assert "generation-status" in bridge
    assert "status_url" in bridge
    assert "POLL_INTERVAL_MS" in bridge
    for script in (
        "async-generation-bridge.js",
        "app-v080.js",
        "grid-ux-patch.js",
        "hybrid-mode-patch.js",
    ):
        assert script in build
        assert script in start


def test_build_uses_single_window_sources():
    build = (ROOT / "build.sh").read_text("utf-8")
    assert "ui_single_window/index.html" in build
    assert "ui_single_window/styles.css" in build
    assert "ui_single_window/app-v080.js" in build
