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
    source_size = (2400, 1800)
    make_geometry(geometry, source_size)
    make_mask(mask, source_size)
    geometry_before = geometry.read_bytes()
    mask_before = mask.read_bytes()

    engine = OpenRouterImageEngine()
    engine.max_input_side = 0
    engine.max_input_pixels = 0
    engine.transmit_max_request_bytes = 2 * 1024 * 1024
    monkeypatch.setattr(engine, "discover_capabilities", lambda: {
        "provider": "openrouter",
        "model": engine.model,
        "transport_engine_version": engine.transport_engine_version,
        "gateway_hard_max_request_bytes": engine.gateway_hard_max_request_bytes,
        "max_request_bytes": 52428800,
        "transmit_max_request_bytes": engine.transmit_max_request_bytes,
        "target_request_bytes": engine.transmit_max_request_bytes,
        "request_limit_source": "test",
        "supported_parameters": {},
        "providers": [],
        "discovery_errors": [],
    })

    result = engine.prepare_environment_inputs(
        prompt="Preserve architecture and fill the mask.",
        geometry_image=geometry,
        outpaint_mask=mask,
        output_dir=tmp_path / "transport",
        width=source_size[0],
        height=source_size[1],
    )

    assert result["request_body_bytes"] <= result["target_request_bytes"]
    assert result["request_body_bytes"] <= engine.transmit_max_request_bytes
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


def test_prepared_request_content_length_is_exact():
    engine = OpenRouterImageEngine()
    body = b'{"model":"test","prompt":"x"}'
    prepared = engine._prepare_http_request(body)
    assert prepared.body == body
    assert int(prepared.headers["Content-Length"]) == len(body)
    assert prepared.headers["X-Marins-Transport-Engine"] == "2.2.0"
    assert prepared.headers["X-Marins-Request-Bytes"] == str(len(body))


def test_extract_request_limit_from_openrouter_413():
    text = '{"error":{"message":"Request body of 54580686 bytes exceeds the maximum allowed size of 52428800 bytes","code":413}}'
    assert OpenRouterImageEngine._extract_request_limit(text) == 52428800


def test_environment_limit_cannot_raise_gateway_or_transmit_cap(monkeypatch):
    monkeypatch.setenv("OPENROUTER_MAX_REQUEST_BYTES", str(100 * 1024 * 1024))
    monkeypatch.setenv("OPENROUTER_TRANSMIT_MAX_BYTES", str(100 * 1024 * 1024))
    engine = OpenRouterImageEngine()
    assert engine._effective_gateway_limit() == 50 * 1024 * 1024
    assert engine.transmit_max_request_bytes == 32 * 1024 * 1024
    capabilities = engine.discover_capabilities()
    assert capabilities["max_request_bytes"] <= 50 * 1024 * 1024
    assert capabilities["transmit_max_request_bytes"] <= 32 * 1024 * 1024
    assert capabilities["target_request_bytes"] <= 32 * 1024 * 1024
