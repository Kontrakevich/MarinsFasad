from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_system1_inspector_is_bundled() -> None:
    patch = (ROOT / "ui_single_window" / "system1-intelligence-patch.js").read_text("utf-8")
    build = (ROOT / "build.sh").read_text("utf-8")
    start = (ROOT / "start.sh").read_text("utf-8")

    assert "SYSTEM №1" in patch
    assert "L1 TECHNICAL → L2 HUMAN ALIGNMENT" in patch
    assert "GATED_BY_LAYER1" in patch
    assert "system1_intelligence" in patch
    assert "system1-intelligence-patch.js" in build
    assert "system1-intelligence-patch.js" in start


def test_system1_native_runtime_is_imported_without_second_service() -> None:
    init = (ROOT / "app" / "__init__.py").read_text("utf-8")
    integration = (ROOT / "app" / "intelligence" / "integration.py").read_text("utf-8")
    orchestrator = (ROOT / "app" / "intelligence" / "orchestrator.py").read_text("utf-8")

    assert "system1_intelligence" in init
    assert "ProjectEngine.record = record_with_intelligence" in integration
    assert "GATED_BY_LAYER1" in orchestrator
    assert "8092" not in integration
    assert "FastAPI" not in integration
