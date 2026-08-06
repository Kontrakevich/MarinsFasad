from pathlib import Path

import pytest
from PIL import Image

from app.ai_engine import AIEngineError, OpenRouterImageEngine
from app.system_prompts import ENVIRONMENT_SYSTEM_PROMPT, PROMPT_CONTRACT_VERSION


NANO_BANANA = "google/gemini-2.5-flash-image"


def make_geometry(path: Path, size=(1200, 900), color=(10, 20, 30, 255)):
    Image.new("RGBA", size, color).save(path, format="PNG")


def make_mask(path: Path, size=(1200, 900)):
    image = Image.new("L", size, 0)
    image.paste(255, (0, 0, size[0] // 4, size[1]))
    image.save(path, format="PNG")


def capabilities(engine):
    return {
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
    }


def test_nano_banana_model_is_hard_locked(monkeypatch):
    monkeypatch.setenv("OPENROUTER_IMAGE_MODEL", "openai/gpt-image-1")
    engine = OpenRouterImageEngine()
    assert engine.model == NANO_BANANA
    assert engine.required_model == NANO_BANANA
    assert engine.generation_mode == "selective-edit"


def test_provider_size_selection_matches_master_orientation():
    assert OpenRouterImageEngine._select_provider_size(8064, 6048) == (1536, 1024)
    assert OpenRouterImageEngine._select_provider_size(6048, 8064) == (1024, 1536)
    assert OpenRouterImageEngine._select_provider_size(4096, 4096) == (1024, 1024)


def test_effective_mask_unites_white_mask_and_transparent_geometry(tmp_path):
    geometry = tmp_path / "geometry.png"
    approved_mask = tmp_path / "approved-mask.png"
    effective_mask = tmp_path / "effective-mask.png"

    image = Image.new("RGBA", (32, 16), (10, 20, 30, 255))
    image.paste((0, 0, 0, 0), (28, 0, 32, 16))
    image.save(geometry, format="PNG")
    mask = Image.new("L", (32, 16), 0)
    mask.paste(255, (0, 0, 4, 16))
    mask.save(approved_mask, format="PNG")

    OpenRouterImageEngine._effective_edit_mask(geometry, approved_mask, effective_mask)
    with Image.open(effective_mask) as result:
        result = result.convert("L")
        assert result.getpixel((1, 8)) == 255
        assert result.getpixel((15, 8)) == 0
        assert result.getpixel((30, 8)) == 255


def test_transport_is_selective_and_does_not_change_masters(tmp_path, monkeypatch):
    geometry = tmp_path / "geometry.png"
    mask = tmp_path / "mask.png"
    source_size = (2400, 1800)
    make_geometry(geometry, source_size)
    make_mask(mask, source_size)
    geometry_before = geometry.read_bytes()
    mask_before = mask.read_bytes()

    engine = OpenRouterImageEngine()
    engine.transmit_max_request_bytes = 2 * 1024 * 1024
    monkeypatch.setattr(engine, "discover_capabilities", lambda: capabilities(engine))

    result = engine.prepare_environment_inputs(
        prompt="Заменить только автомобиль справа на дерево.",
        geometry_image=geometry,
        outpaint_mask=mask,
        output_dir=tmp_path / "transport",
        width=source_size[0],
        height=source_size[1],
    )

    assert result["provider_output_size"] == "1536x1024"
    assert result["request_body_bytes"] <= engine.transmit_max_request_bytes
    assert result["model"] == NANO_BANANA
    assert result["model_lock"] == "nano-banana-only"
    assert result["generation_mode"] == "selective-edit"
    assert result["source_contract"] == "approved-geometry-pixel-preserved-outside-edit-area"
    assert result["input_reference_count"] == 2
    assert result["full_canvas_generation"] is False
    assert result["pixel_preservation_required"] is True
    assert result["system_prompt_contract"] == PROMPT_CONTRACT_VERSION
    assert Path(result["effective_mask_path"]).is_file()
    assert geometry.read_bytes() == geometry_before
    assert mask.read_bytes() == mask_before


def test_payload_contains_system_prompt_geometry_and_mask_references(tmp_path):
    geometry = tmp_path / "approved-geometry.png"
    mask = tmp_path / "approved-mask.png"
    make_geometry(geometry, (320, 240))
    make_mask(mask, (320, 240))

    payload = OpenRouterImageEngine()._build_payload(
        prompt="Operator requirement: replace only the car on the right.",
        geometry_image=geometry,
        outpaint_mask=mask,
        provider_size=(1536, 1024),
    )

    assert payload["model"] == NANO_BANANA
    assert ENVIRONMENT_SYSTEM_PROMPT in payload["prompt"]
    assert PROMPT_CONTRACT_VERSION in payload["prompt"]
    assert "replace only the car on the right" in payload["prompt"]
    assert len(payload["input_references"]) == 2
    assert all(item["image_url"]["url"].startswith("data:image/") for item in payload["input_references"])


def test_empty_mandatory_mask_allows_prompt_localized_edit(tmp_path, monkeypatch):
    geometry = tmp_path / "geometry.png"
    mask = tmp_path / "empty-mask.png"
    make_geometry(geometry, (320, 240))
    Image.new("L", (320, 240), 0).save(mask, format="PNG")

    engine = OpenRouterImageEngine()
    monkeypatch.setattr(engine, "discover_capabilities", lambda: capabilities(engine))
    prepared = engine.prepare_environment_inputs(
        prompt="Удалить только фонарь слева.",
        geometry_image=geometry,
        outpaint_mask=mask,
        output_dir=tmp_path / "transport",
        width=320,
        height=240,
    )

    assert prepared["editable_pixels"] == 0
    assert prepared["generation_mode"] == "selective-edit"
    assert prepared["mask_policy"] == "prompt-localized-edit-with-empty-mandatory-mask"


def test_candidate_preserves_base_outside_local_edit(tmp_path):
    size = (100, 80)
    geometry = tmp_path / "geometry.png"
    mask = tmp_path / "mask.png"
    provider = tmp_path / "provider.png"
    make_geometry(geometry, size, (10, 20, 30, 255))

    mandatory = Image.new("L", size, 0)
    mandatory.paste(255, (0, 0, 10, 80))
    mandatory.save(mask, format="PNG")

    generated = Image.new("RGB", size, (10, 20, 30))
    generated.paste((100, 150, 200), (0, 0, 10, 80))
    generated.paste((220, 40, 50), (70, 30, 80, 40))
    generated.save(provider, format="PNG")

    prepared = {
        "content_box_normalized": {"x": 0, "y": 0, "width": 1, "height": 1},
        "effective_mask_path": str(mask),
    }
    result = OpenRouterImageEngine()._promote_provider_output(
        provider_output=provider,
        geometry_image=geometry,
        outpaint_mask=mask,
        prepared=prepared,
        output_dir=tmp_path,
        width=size[0],
        height=size[1],
    )

    with Image.open(result["candidate"]) as candidate:
        candidate = candidate.convert("RGB")
        assert candidate.getpixel((5, 40)) == (100, 150, 200)
        assert candidate.getpixel((75, 35)) == (220, 40, 50)
        assert candidate.getpixel((50, 60)) == (10, 20, 30)

    assert result["approved_geometry_preserved"] is True
    assert result["pixel_preservation_verified"] is True
    assert result["outside_changed_pixels"] == 0
    assert result["generation_mode"] == "selective-edit"
    assert result["provider_model"] == NANO_BANANA


def test_global_regeneration_is_rejected(tmp_path):
    size = (100, 80)
    geometry = tmp_path / "geometry.png"
    mask = tmp_path / "mask.png"
    provider = tmp_path / "provider.png"
    make_geometry(geometry, size, (10, 20, 30, 255))
    Image.new("L", size, 0).save(mask, format="PNG")
    Image.new("RGB", size, (200, 100, 50)).save(provider, format="PNG")

    with pytest.raises(AIEngineError) as captured:
        OpenRouterImageEngine()._promote_provider_output(
            provider_output=provider,
            geometry_image=geometry,
            outpaint_mask=mask,
            prepared={
                "content_box_normalized": {"x": 0, "y": 0, "width": 1, "height": 1},
                "effective_mask_path": str(mask),
            },
            output_dir=tmp_path,
            width=size[0],
            height=size[1],
        )
    assert captured.value.details["reason"] == "semantic_edit_area_too_large"


def test_prepared_request_content_length_is_exact():
    engine = OpenRouterImageEngine()
    body = b'{"model":"test","prompt":"x"}'
    prepared = engine._prepare_http_request(body)
    assert prepared.body == body
    assert int(prepared.headers["Content-Length"]) == len(body)
    assert prepared.headers["X-Marins-Transport-Engine"] == "2.7.0"


def test_extract_openrouter_limits_and_supported_sizes():
    text = (
        '{"error":{"message":"Invalid size \'8064x6048\'. Supported sizes are '
        '1024x1024, 1024x1536, 1536x1024, and auto.","code":400}}'
    )
    assert OpenRouterImageEngine._extract_supported_sizes(text) == [
        (1024, 1024), (1024, 1536), (1536, 1024)
    ]
    size_error = '{"error":{"message":"Request body exceeds the maximum allowed size of 52428800 bytes","code":413}}'
    assert OpenRouterImageEngine._extract_request_limit(size_error) == 52428800


def test_environment_limit_cannot_raise_gateway_or_transmit_cap(monkeypatch):
    monkeypatch.setenv("OPENROUTER_MAX_REQUEST_BYTES", str(100 * 1024 * 1024))
    monkeypatch.setenv("OPENROUTER_TRANSMIT_MAX_BYTES", str(100 * 1024 * 1024))
    engine = OpenRouterImageEngine()
    assert engine._effective_gateway_limit() == 50 * 1024 * 1024
    assert engine.transmit_max_request_bytes == 32 * 1024 * 1024
