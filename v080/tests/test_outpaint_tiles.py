from app.ai_engine import OpenRouterImageEngine


def test_legacy_generic_tiled_repair_remains_disabled():
    engine = OpenRouterImageEngine()
    assert engine.internal_outpaint_tiles_allowed is False
    assert engine.outpaint_repair_mode == "hybrid-second-pass"
    assert engine.outpaint_tile_max_calls == 0
    assert engine.outpaint_tile_planner == "disabled"
    assert engine.outpaint_fallback_mode == "quality-aware-edge-refine"


def test_hybrid_second_pass_keeps_full_prompt_context_and_quality():
    engine = OpenRouterImageEngine()
    prompt = (
        "OPERATOR PROMPT — EXECUTE EXACTLY\n"
        "1. Убрать столбы и провода.\n"
        "2. Сделать мокрый асфальт.\n\n"
        "GENERATION MODE\nHYBRID\n\n"
        "GENERATION QUALITY\nMAX"
    )
    outpaint_prompt = engine._internal_outpaint_prompt(prompt)
    assert "OUTPAINT ONLY" in outpaint_prompt
    assert "GENERATION MODE\nOUTPAINT" in outpaint_prompt
    assert "GENERATION QUALITY\nMAX" in outpaint_prompt
    assert "FULL ORIGINAL COMPILED PROMPT — MANDATORY CONTEXT" in outpaint_prompt
    assert prompt in outpaint_prompt
    assert engine.missing_region_transport_policy == "native-transparency-single-reference"


def test_primary_prompt_mode_and_quality_are_detected():
    engine = OpenRouterImageEngine()
    assert engine._mode_from_prompt("GENERATION MODE\nHYBRID") == "hybrid"
    assert engine._mode_from_prompt("GENERATION MODE\nEDIT") == "edit"
    assert engine._mode_from_prompt("GENERATION MODE\nOUTPAINT") == "outpaint"
    assert engine._quality_from_prompt("GENERATION QUALITY\nDRAFT") == "draft"
    assert engine._quality_from_prompt("GENERATION QUALITY\nSTANDARD") == "standard"
    assert engine._quality_from_prompt("GENERATION QUALITY\nHIGH") == "high"
    assert engine._quality_from_prompt("GENERATION QUALITY\nMAX") == "max"
