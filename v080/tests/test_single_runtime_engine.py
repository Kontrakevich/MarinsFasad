from pathlib import Path

from app.ai_engine import OpenRouterImageEngine


ROOT = Path(__file__).resolve().parents[1]


def test_only_hybrid_engine_is_imported_by_app_package():
    init = (ROOT / "app" / "__init__.py").read_text("utf-8")
    assert "hybrid_engine" in init
    assert "stable_engine" not in init
    for obsolete in (
        "provider_policy",
        "selective_policy",
        "prompt_enforcement_policy",
        "outpaint_qc_policy",
        "missing_region_policy",
        "tile_planner_policy",
        "runtime_version_policy",
        "geometry_only_outpaint_policy",
    ):
        assert obsolete not in init
        assert not (ROOT / "app" / f"{obsolete}.py").exists()


def test_active_engine_contract_is_hybrid_v3200():
    engine = OpenRouterImageEngine()
    assert engine.transport_engine_version == "3.2.0"
    assert engine.model == "google/gemini-2.5-flash-image"
    assert engine.default_generation_mode == "hybrid"
    assert engine.available_generation_modes == ("hybrid", "edit", "outpaint")
    assert engine.environment_input_policy == "approved-geometry-only"
    assert engine.outpaint_detection_policy == "automatic-from-approved-geometry-transparency"
    assert engine.provider_input_policy == "single-approved-geometry-reference"
    assert engine.prompt_transport_policy == "primary-ui-prompt-verbatim-plus-internal-outpaint-pass"
    assert engine.missing_region_transport_policy == "native-transparency-single-reference"
    assert engine.outpaint_repair_mode == "hybrid-second-pass"
    assert engine.user_mask_required is False
    assert engine.internal_outpaint_tiles_allowed is False
