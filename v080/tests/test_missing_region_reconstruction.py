from pathlib import Path

from PIL import Image

from app.ai_engine import OpenRouterImageEngine


def test_missing_regions_are_transmitted_as_opaque_service_markers() -> None:
    engine = OpenRouterImageEngine()
    geometry = Image.new("RGBA", (24, 16), (40, 60, 80, 255))
    geometry.paste((0, 0, 0, 0), (0, 0, 6, 16))
    mask = Image.new("L", (24, 16), 0)
    mask.paste(255, (0, 0, 6, 16))

    transport_geometry, transport_mask, _ = engine._reference_canvases(
        geometry,
        mask,
        (24, 16),
    )

    missing_pixel = transport_geometry.convert("RGB").getpixel((2, 8))
    protected_pixel = transport_geometry.convert("RGB").getpixel((12, 8))
    assert missing_pixel in {(255, 0, 255), (0, 255, 255)}
    assert protected_pixel == (40, 60, 80)
    assert transport_geometry.getchannel("A").getextrema() == (255, 255)
    assert transport_mask.getpixel((2, 8)) == 255
    assert engine.missing_region_transport_policy == (
        "opaque-chroma-marker-with-nano-banana-auto-retry"
    )


def test_solid_white_fill_is_not_accepted_as_neural_outpaint(tmp_path: Path) -> None:
    engine = OpenRouterImageEngine()
    candidate = tmp_path / "candidate.png"
    mask = tmp_path / "mask.png"

    Image.new("RGB", (80, 60), (255, 255, 255)).save(candidate, format="PNG")
    Image.new("L", (80, 60), 255).save(mask, format="PNG")

    report = engine._outpaint_reconstruction_statistics(candidate, mask)
    assert report["outpaint_reconstructed"] is False
    assert report["placeholder_component_count"] >= 1
    assert report["placeholder_ratio"] > 0.9
    assert report["solid_white_is_valid_outpaint"] is False


def test_textured_scene_content_is_accepted_as_reconstruction(tmp_path: Path) -> None:
    engine = OpenRouterImageEngine()
    candidate = tmp_path / "candidate.png"
    mask = tmp_path / "mask.png"

    image = Image.new("RGB", (80, 60), (80, 110, 150))
    for y in range(60):
        for x in range(80):
            image.putpixel(
                (x, y),
                (
                    50 + (x * 3 + y) % 120,
                    70 + (x + y * 2) % 120,
                    90 + (x * 2 + y * 3) % 120,
                ),
            )
    image.save(candidate, format="PNG")
    Image.new("L", (80, 60), 255).save(mask, format="PNG")

    report = engine._outpaint_reconstruction_statistics(candidate, mask)
    assert report["outpaint_reconstructed"] is True
    assert report["placeholder_component_count"] == 0
