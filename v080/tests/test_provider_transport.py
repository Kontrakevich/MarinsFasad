from pathlib import Path

from PIL import Image

from app.ai_engine import OpenRouterImageEngine
from app.system_prompts import ENVIRONMENT_SYSTEM_PROMPT, PROMPT_CONTRACT_VERSION


def make_geometry(path: Path, size=(1200, 900)):
    image = Image.effect_noise(size, 100).convert("RGBA")
    image.putalpha(Image.new("L", size, 255))
    image.save(path, format="PNG")


def make_mask(path: Path, size=(1200, 900)):
    image = Image.new("L", size, 0)
    image.paste(255, (0, 0, size[0] // 4, size[1]))
    image.save(path, format="PNG")


def test_provider_size_selection_matches_master_orientation():
    assert OpenRouterImageEngine._select_provider_size(8064, 6048) == (1536, 1024)
    assert OpenRouterImageEngine._select_provider_size(6048, 8064) == (1024, 1536)
    assert OpenRouterImageEngine._select_provider_size(4096, 4096) == (1024, 1024)


def test_effective_mask_unites_white_mask_and_transparent_geometry(tmp_path):
    geometry = tmp_path / "geometry.png"
    approved_mask = tmp_path / "approved-mask.png"
    effective_mask = tmp_path / "effective-mask.png"

    image = Image.new("RGBA", (32, 16), (10, 20, 30, 255))
    for x in range(28, 32):
        for y in range(16):
            image.putpixel((x, y), (0, 0, 0, 0))
    image.save(geometry, format="PNG")

    mask = Image.new("L", (32, 16), 0)
    mask.paste(255, (0, 0, 4, 16))
    mask.save(approved_mask, format="PNG")

    OpenRouterImageEngine._effective_edit_mask(
        geometry,
        approved_mask,
        effective_mask,
    )

    with Image.open(effective_mask) as result:
        result = result.convert("L")
        assert result.getpixel((1, 8)) == 255
        assert result.getpixel((15, 8)) == 0
        assert result.getpixel((30, 8)) == 255


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
        "supported_output_sizes": ["1024x1024", "1024x1536", "1536x1024"],
        "providers": [],
        "discovery_errors": [],
    })

    result = engine.prepare_environment_inputs(
        prompt="Regenerate the complete frame from the corrected geometry.",
        geometry_image=geometry,
        outpaint_mask=mask,
        output_dir=tmp_path / "transport",
        width=source_size[0],
        height=source_size[1],
    )

    assert result["provider_output_size"] == "1536x1024"
    assert result["request_body_bytes"] <= result["target_request_bytes"]
    assert result["request_body_bytes"] <= engine.transmit_max_request_bytes
    assert result["resized_for_provider"] is True
    assert result["source_contract"] == "corrected-approved-geometry-full-frame-reference"
    assert result["system_prompt_in_request"] is True
    assert result["system_prompt_contract"] == PROMPT_CONTRACT_VERSION
    assert result["full_canvas_generation"] is True
    assert result["generation_mode"] == "full-frame-reference"
    assert result["input_reference_count"] == 1
    assert result["mask_role"] == "quality-control-only"
    assert result["mask_policy"] == "qc-only-white-mask-or-transparent-geometry"
    assert result["approved_geometry_sha256"]
    assert result["approved_mask_sha256"]
    assert result["effective_mask_sha256"]
    assert Path(result["effective_mask_path"]).is_file()
    assert geometry.read_bytes() == geometry_before
    assert mask.read_bytes() == mask_before

    with Image.open(result["transport_geometry_path"]) as transport_geometry:
        geometry_size = transport_geometry.size
    with Image.open(result["transport_mask_path"]) as transport_mask:
        mask_size = transport_mask.size
        assert set(transport_mask.getdata()).issubset({0, 255})

    assert geometry_size == mask_size
    assert geometry_size == (result["transport_width"], result["transport_height"])
    assert 0 < result["content_box_normalized"]["width"] <= 1
    assert 0 < result["content_box_normalized"]["height"] <= 1


def test_payload_contains_system_prompt_and_only_geometry_reference(tmp_path):
    geometry = tmp_path / "approved-geometry.png"
    mask = tmp_path / "approved-mask.png"
    make_geometry(geometry, (320, 240))
    make_mask(mask, (320, 240))

    payload = OpenRouterImageEngine()._build_payload(
        prompt="Operator requirement: clear daytime sky.",
        geometry_image=geometry,
        outpaint_mask=mask,
        provider_size=(1536, 1024),
    )

    assert ENVIRONMENT_SYSTEM_PROMPT in payload["prompt"]
    assert PROMPT_CONTRACT_VERSION in payload["prompt"]
    assert "Operator requirement: clear daytime sky." in payload["prompt"]
    assert len(payload["input_references"]) == 1
    assert payload["input_references"][0]["image_url"]["url"].startswith("data:image/")
    assert "mask" not in payload


def test_empty_effective_mask_does_not_limit_full_frame_generation(tmp_path, monkeypatch):
    geometry = tmp_path / "geometry.png"
    mask = tmp_path / "empty-mask.png"
    make_geometry(geometry, (320, 240))
    Image.new("L", (320, 240), 0).save(mask, format="PNG")

    engine = OpenRouterImageEngine()
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
        "supported_output_sizes": ["1024x1024", "1024x1536", "1536x1024"],
        "providers": [],
        "discovery_errors": [],
    })

    prepared = engine.prepare_environment_inputs(
        prompt="Generate the complete frame.",
        geometry_image=geometry,
        outpaint_mask=mask,
        output_dir=tmp_path / "transport",
        width=320,
        height=240,
    )

    assert prepared["editable_pixels"] == 0
    assert prepared["generation_mode"] == "full-frame-reference"
    assert prepared["input_reference_count"] == 1


def test_provider_output_becomes_entire_candidate_without_geometry_composite(tmp_path):
    geometry = tmp_path / "geometry.png"
    mask = tmp_path / "mask.png"
    provider = tmp_path / "provider.png"

    Image.new("RGBA", (8, 6), (10, 20, 30, 255)).save(geometry, format="PNG")
    mask_image = Image.new("L", (8, 6), 0)
    mask_image.paste(255, (0, 0, 2, 6))
    mask_image.save(mask, format="PNG")
    Image.new("RGB", (12, 8), (200, 100, 50)).save(provider, format="PNG")

    prepared = {
        "content_box_normalized": {
            "x": 1 / 12,
            "y": 0,
            "width": 10 / 12,
            "height": 1,
        },
        "approved_geometry_sha256": "test",
        "effective_mask_path": str(mask),
    }
    result = OpenRouterImageEngine()._promote_provider_output(
        provider_output=provider,
        geometry_image=geometry,
        outpaint_mask=mask,
        prepared=prepared,
        output_dir=tmp_path,
        width=8,
        height=6,
    )

    with Image.open(result["candidate"]) as candidate:
        assert candidate.mode == "RGB"
        assert candidate.size == (8, 6)
        assert candidate.getpixel((3, 3)) == (200, 100, 50)
        assert candidate.getpixel((0, 3)) == (200, 100, 50)

    assert result["remapped_to_master"] is True
    assert result["approved_geometry_preserved"] is False
    assert result["approved_geometry_used_as_reference"] is True
    assert result["meaningful_generation"] is True
    assert result["full_canvas_generation"] is True
    assert result["generation_mode"] == "full-frame-reference"
    assert result["non_mask_change_ratio"] > 0


def test_prepared_request_content_length_is_exact():
    engine = OpenRouterImageEngine()
    body = b'{"model":"test","prompt":"x"}'
    prepared = engine._prepare_http_request(body)
    assert prepared.body == body
    assert int(prepared.headers["Content-Length"]) == len(body)
    assert prepared.headers["X-Marins-Transport-Engine"] == "2.6.0"
    assert prepared.headers["X-Marins-Request-Bytes"] == str(len(body))


def test_extract_openrouter_limits_and_supported_sizes():
    text = (
        '{"error":{"message":"Invalid size \'8064x6048\'. Supported sizes are '
        '1024x1024, 1024x1536, 1536x1024, and auto.","code":400}}'
    )
    assert OpenRouterImageEngine._extract_supported_sizes(text) == [
        (1024, 1024),
        (1024, 1536),
        (1536, 1024),
    ]

    size_error = '{"error":{"message":"Request body of 54580686 bytes exceeds the maximum allowed size of 52428800 bytes","code":413}}'
    assert OpenRouterImageEngine._extract_request_limit(size_error) == 52428800


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
