from pathlib import Path

from PIL import Image

from app.ai_engine import OpenRouterImageEngine


def test_missing_regions_stay_transparent_in_provider_reference() -> None:
    engine = OpenRouterImageEngine()
    geometry = Image.new("RGBA", (24, 16), (40, 60, 80, 255))
    geometry.paste((0, 0, 0, 0), (0, 0, 6, 16))
    plan = Image.new("L", (24, 16), 0)
    plan.paste(255, (0, 0, 6, 16))

    transport_geometry, transport_plan, _ = engine._reference_canvases(
        geometry,
        plan,
        (24, 16),
    )

    missing_pixel = transport_geometry.getpixel((2, 8))
    protected_pixel = transport_geometry.getpixel((12, 8))
    assert missing_pixel[3] == 0
    assert protected_pixel[:3] == (40, 60, 80)
    assert protected_pixel[3] == 255
    assert transport_plan.getpixel((2, 8)) == 255
    assert engine.missing_region_transport_policy == "native-transparency-single-reference"
    assert engine.outpaint_repair_mode == "single-pass"


def test_solid_white_fill_is_reported_as_failed_reconstruction(tmp_path: Path) -> None:
    engine = OpenRouterImageEngine()
    candidate = tmp_path / "candidate.png"
    plan = tmp_path / "plan.png"

    Image.new("RGB", (80, 60), (255, 255, 255)).save(candidate, format="PNG")
    Image.new("L", (80, 60), 255).save(plan, format="PNG")

    report = engine._outpaint_reconstruction_statistics(candidate, plan)
    assert report["outpaint_reconstructed"] is False
    assert report["placeholder_component_count"] >= 1
    assert report["placeholder_ratio"] > 0.9
    assert report["solid_white_is_valid_outpaint"] is False


def test_textured_scene_content_is_accepted_as_reconstruction(tmp_path: Path) -> None:
    engine = OpenRouterImageEngine()
    candidate = tmp_path / "candidate.png"
    plan = tmp_path / "plan.png"

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
    Image.new("L", (80, 60), 255).save(plan, format="PNG")

    report = engine._outpaint_reconstruction_statistics(candidate, plan)
    assert report["outpaint_reconstructed"] is True
