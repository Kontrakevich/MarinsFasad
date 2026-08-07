from app.ai_engine import OpenRouterImageEngine


def test_legacy_tiled_repair_is_disabled():
    engine = OpenRouterImageEngine()
    assert engine.internal_outpaint_tiles_allowed is False
    assert engine.outpaint_repair_mode == "hybrid-second-pass"
    assert engine.outpaint_tile_max_calls == 0
    assert engine.outpaint_tile_planner == "disabled"


def test_hybrid_second_pass_replaces_legacy_tile_repair():
    engine = OpenRouterImageEngine()
    prompt = (
        "OPERATOR PROMPT — EXECUTE EXACTLY\n"
        "1. Убрать столбы и провода.\n\n"
        "GENERATION MODE\nHYBRID"
    )
    outpaint_prompt = engine._internal_outpaint_prompt(prompt)
    assert "OUTPAINT ONLY" in outpaint_prompt
    assert "GENERATION MODE\nOUTPAINT" in outpaint_prompt
    assert engine.missing_region_transport_policy == "native-transparency-single-reference"


def test_hybrid_primary_prompt_mode_is_detected():
    engine = OpenRouterImageEngine()
    assert engine._mode_from_prompt("GENERATION MODE\nHYBRID") == "hybrid"
    assert engine._mode_from_prompt("GENERATION MODE\nEDIT") == "edit"
    assert engine._mode_from_prompt("GENERATION MODE\nOUTPAINT") == "outpaint"
