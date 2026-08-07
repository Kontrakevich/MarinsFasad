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
    assert engine.outpaint_repair_mode == "hybrid-second-pass"


def test_hybrid_reapplies_original_missing_alpha_between_passes(tmp_path: Path) -> None:
    geometry = tmp_path / "geometry.png"
    edited = tmp_path / "edited.png"
    intermediate = tmp_path / "intermediate.png"

    base = Image.new("RGBA", (80, 60), (50, 70, 90, 255))
    base.paste((0, 0, 0, 0), (0, 0, 12, 60))
    base.save(geometry, format="PNG")

    Image.new("RGB", (80, 60), (120, 150, 180)).save(edited, format="PNG")
    OpenRouterImageEngine._reapply_geometry_alpha(edited, geometry, intermediate)

    with Image.open(intermediate) as result:
        result = result.convert("RGBA")
        assert result.getpixel((2, 30))[3] == 0
        assert result.getpixel((40, 30)) == (120, 150, 180, 255)


def test_internal_second_pass_is_outpaint_only() -> None:
    engine = OpenRouterImageEngine()
    source_prompt = (
        "OPERATOR PROMPT — EXECUTE EXACTLY\n"
        "1. Убрать столбы и провода.\n"
        "2. Сделать облачную погоду.\n\n"
        "GENERATION MODE\nHYBRID"
    )
    prompt = engine._internal_outpaint_prompt(source_prompt)
    assert "INTERNAL HYBRID PASS 2/2 — OUTPAINT ONLY" in prompt
    assert "GENERATION MODE\nOUTPAINT" in prompt
    assert "Existing visible pixels" in prompt
    assert "ALREADY EXECUTED IN PASS 1" in prompt
