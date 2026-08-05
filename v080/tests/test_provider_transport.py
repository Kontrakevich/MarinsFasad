from pathlib import Path

from PIL import Image

from app.ai_engine import OpenRouterImageEngine


def make_geometry(path: Path, size=(1200, 900)):
    image = Image.effect_noise(size, 100).convert("RGBA")
    image.putalpha(Image.new("L", size, 255))
    image.save(path, format="PNG")


def make_mask(path: Path, size=(1200, 900)):
    image = Image.new("L", size, 0)
    image.paste(255, (0, 0, size[0] // 4, size[1]))
    image.save(path, format="PNG")


def test_transport_fits_limit_without_changing_masters(tmp_path, monkeypatch):
    geometry = tmp_path / "geometry.png"
    mask = tmp_path / "mask.png"
    make_geometry(geometry)
    make_mask(mask)
    geometry_before = geometry.read_bytes()
    mask_before = mask.read_bytes()

    engine = OpenRouterImageEngine()
    engine.max_input_side = 0
    engine.max_input_pixels = 0
    engine.safety_margin = 0.90
    monkeypatch.setattr(engine, "discover_capabilities", lambda: {
        "provider": "openrouter",
        "model": engine.model,
        "max_request_bytes": 260000,
        "safe_request_bytes": 234000,
        "request_limit_source": "test",
        "safety_margin": 0.90,
        "supported_parameters": {},
        "providers": [],
        "discovery_errors": [],
    })

    result = engine.prepare_environment_inputs(
        prompt="Preserve architecture and fill the mask.",
        geometry_image=geometry,
        outpaint_mask=mask,
        output_dir=tmp_path / "transport",
        width=1200,
        height=900,
    )

    assert result["request_body_bytes"] <= result["safe_request_bytes"]
    assert result["resized_for_provider"] is True
    assert geometry.read_bytes() == geometry_before
    assert mask.read_bytes() == mask_before

    with Image.open(result["transport_geometry_path"]) as transport_geometry:
        geometry_size = transport_geometry.size
    with Image.open(result["transport_mask_path"]) as transport_mask:
        mask_size = transport_mask.size
        assert set(transport_mask.getdata()).issubset({0, 255})

    assert geometry_size == mask_size
    assert geometry_size == (result["transport_width"], result["transport_height"])


def test_extract_request_limit():
    text = "maximum allowed size of 52428800 bytes"
    assert OpenRouterImageEngine._extract_request_limit(text) == 52428800
