from pathlib import Path

from PIL import Image

from app.ai_engine import OpenRouterImageEngine


def make_inputs(tmp_path: Path):
    geometry = tmp_path / "geometry.png"
    provider = tmp_path / "provider.png"
    plan = tmp_path / "plan.png"

    base = Image.new("RGBA", (80, 60), (30, 60, 90, 255))
    base.paste((0, 0, 0, 0), (0, 0, 10, 60))
    base.save(geometry)

    generated = Image.new("RGB", (80, 60), (170, 180, 190))
    generated.save(provider)

    plan_image = Image.new("L", (80, 60), 0)
    plan_image.paste(255, (0, 0, 10, 60))
    plan_image.save(plan)
    return geometry, provider, plan


def prepared(plan: Path, mode: str) -> dict:
    return {
        "content_box_normalized": {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0},
        "effective_mask_path": str(plan),
        "requested_generation_mode": mode,
        "generation_mode": mode,
    }


def test_hybrid_accepts_coherent_full_frame_image_edit(tmp_path: Path):
    geometry, provider, plan = make_inputs(tmp_path)
    engine = OpenRouterImageEngine()
    result = engine._promote_provider_output(
        provider_output=provider,
        geometry_image=geometry,
        outpaint_mask=plan,
        prepared=prepared(plan, "hybrid"),
        output_dir=tmp_path / "hybrid",
        width=80,
        height=60,
    )

    with Image.open(result["candidate"]) as candidate:
        assert candidate.convert("RGB").getpixel((40, 30)) == (170, 180, 190)
    assert result["generation_mode"] == "hybrid"
    assert result["full_frame_semantic_edit"] is True
    assert result["strong_image_edit_enabled"] is True
    assert result["geometry_preservation_policy"] == "prompt-enforced-corrected-architecture"


def test_edit_accepts_full_frame_weather_and_cleanup_result(tmp_path: Path):
    geometry, provider, plan = make_inputs(tmp_path)
    engine = OpenRouterImageEngine()
    result = engine._promote_provider_output(
        provider_output=provider,
        geometry_image=geometry,
        outpaint_mask=plan,
        prepared=prepared(plan, "edit"),
        output_dir=tmp_path / "edit",
        width=80,
        height=60,
    )
    with Image.open(result["candidate"]) as candidate:
        assert candidate.convert("RGB").getpixel((40, 30)) == (170, 180, 190)
    assert result["generation_mode"] == "edit"
    assert result["strong_image_edit_enabled"] is True


def test_outpaint_preserves_existing_pixels_exactly(tmp_path: Path):
    geometry, provider, plan = make_inputs(tmp_path)
    engine = OpenRouterImageEngine()
    result = engine._promote_provider_output(
        provider_output=provider,
        geometry_image=geometry,
        outpaint_mask=plan,
        prepared=prepared(plan, "outpaint"),
        output_dir=tmp_path / "outpaint",
        width=80,
        height=60,
    )

    with Image.open(result["candidate"]) as candidate:
        rgb = candidate.convert("RGB")
        assert rgb.getpixel((5, 30)) == (170, 180, 190)
        assert rgb.getpixel((40, 30)) == (30, 60, 90)
    assert result["generation_mode"] == "outpaint"
    assert result["full_frame_semantic_edit"] is False
    assert result["outside_changed_pixels"] == 0
    assert result["pixel_preservation_verified"] is True
