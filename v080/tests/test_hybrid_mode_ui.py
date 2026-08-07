from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_skill_selector_exposes_four_generation_modes() -> None:
    patch = (ROOT / "ui_single_window" / "hybrid-mode-patch.js").read_text("utf-8")
    assert "HYBRID · EDIT / RELIGHT + OUTPAINT" in patch
    assert "RELIGHT · NEW LIGHTING" in patch
    assert "IMAGE EDIT" in patch
    assert "OUTPAINT" in patch
    assert "__MARINS_GENERATION_MODE__" in patch
    assert "ensureMode" in patch
    assert "generationPattern" in patch
    assert "promptPattern" in patch


def test_skill_mode_control_is_bundled_after_generation_bridge() -> None:
    build = (ROOT / "build.sh").read_text("utf-8")
    start = (ROOT / "start.sh").read_text("utf-8")
    sequence = '"$ROOT/ui_single_window/grid-ux-patch.js" "$ROOT/ui_single_window/hybrid-mode-patch.js"'
    assert sequence in build
    assert sequence in start
    assert "skill-contracts-3300" in build
    assert "skill-contracts-3300" in start
