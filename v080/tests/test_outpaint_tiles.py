from PIL import Image

from app.ai_engine import OpenRouterImageEngine


def test_legacy_tiled_repair_is_disabled():
    engine = OpenRouterImageEngine()
    assert engine.internal_outpaint_tiles_allowed is False
    assert engine.outpaint_repair_mode == "single-pass"
    assert engine.outpaint_tile_max_calls == 0
    assert engine.outpaint_tile_planner == "disabled"


def test_compatibility_marker_is_neutral_and_not_used_for_transport():
    marker = OpenRouterImageEngine._missing_region_marker((64, 48)).convert("RGBA")
    colors = set(marker.getdata())
    assert colors == {(127, 127, 127, 255)}
    assert OpenRouterImageEngine.missing_region_transport_policy == "native-transparency-single-reference"


def test_placeholder_analysis_rejects_solid_white_and_accepts_scene_texture():
    engine = OpenRouterImageEngine()
    plan = Image.new("L", (160, 120), 255)

    white = Image.new("RGB", (160, 120), (255, 255, 255))
    _, white_stats = engine._placeholder_analysis(white, plan)
    assert white_stats["outpaint_reconstructed"] is False

    textured = Image.new("RGB", (160, 120))
    pixels = textured.load()
    for y in range(120):
        for x in range(160):
            pixels[x, y] = (
                70 + (x % 37),
                95 + (y % 41),
                120 + ((x + y) % 53),
            )
    _, texture_stats = engine._placeholder_analysis(textured, plan)
    assert texture_stats["outpaint_reconstructed"] is True


def test_compatibility_tile_prompt_keeps_original_prompt():
    engine = OpenRouterImageEngine()
    original = "Убрать столбы и провода и продолжить покрытие парковки."
    prompt = engine._tile_prompt(original, 1)
    assert original in prompt
