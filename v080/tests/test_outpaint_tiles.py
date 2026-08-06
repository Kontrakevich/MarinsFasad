from pathlib import Path

from PIL import Image

from app.ai_engine import OpenRouterImageEngine


def test_long_thin_missing_region_is_split_into_zoomed_tiles():
    engine = OpenRouterImageEngine()
    mask = Image.new("L", (1600, 1000), 0)
    mask.paste(255, (0, 0, 1600, 42))

    tiles = engine._component_tile_boxes(mask)

    assert 2 <= len(tiles) <= engine.outpaint_tile_max_calls
    assert all(tile["mask_pixels"] >= engine.outpaint_tile_min_pixels for tile in tiles)
    assert all(tile["crop_box"][3] - tile["crop_box"][1] < 300 for tile in tiles)
    assert tiles[0]["crop_box"][1] == 0


def test_missing_region_marker_is_opaque_and_not_white():
    marker = OpenRouterImageEngine._missing_region_marker((64, 48)).convert("RGBA")
    colors = set(marker.getdata())

    assert colors == {(255, 0, 255, 255), (0, 255, 255, 255)}
    assert all(pixel[3] == 255 for pixel in colors)
    assert (255, 255, 255, 255) not in colors


def test_placeholder_analysis_rejects_solid_white_and_accepts_scene_texture():
    engine = OpenRouterImageEngine()
    mask = Image.new("L", (160, 120), 255)

    white = Image.new("RGB", (160, 120), (255, 255, 255))
    _, white_stats = engine._placeholder_analysis(white, mask)
    assert white_stats["outpaint_reconstructed"] is False
    assert white_stats["placeholder_component_count"] >= 1

    textured = Image.new("RGB", (160, 120))
    pixels = textured.load()
    for y in range(120):
        for x in range(160):
            pixels[x, y] = (
                70 + (x % 37),
                95 + (y % 41),
                120 + ((x + y) % 53),
            )
    _, texture_stats = engine._placeholder_analysis(textured, mask)
    assert texture_stats["outpaint_reconstructed"] is True
    assert texture_stats["placeholder_component_count"] == 0


def test_tile_prompt_keeps_original_operator_prompt():
    engine = OpenRouterImageEngine()
    original = "Убрать только белый автомобиль справа и продолжить покрытие парковки."
    prompt = engine._tile_prompt(original, 1)

    assert original in prompt
    assert "WHITE pixels are the only editable pixels" in prompt
    assert "Do not return white, black, transparent" in prompt
    assert "Do not change any black-mask pixel" in prompt
