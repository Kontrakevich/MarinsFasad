from pathlib import Path

from PIL import Image

from app.ai_engine import OpenRouterImageEngine
from app.system_prompts import ENVIRONMENT_SYSTEM_PROMPT, PROMPT_CONTRACT_VERSION


NANO_BANANA = "google/gemini-2.5-flash-image"


def make_geometry(path: Path, size=(1200, 900), color=(10, 20, 30, 255)):
    image = Image.new("RGBA", size, color)
    image.paste((0, 0, 0, 0), (0, 0, max(1, size[0] // 8), size[1]))
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


def test_nano_banana_and_geometry_only_contract_are_hard_locked(monkeypatch):
    monkeypatch.setenv("OPENROUTER_IMAGE_MODEL", "openai/gpt-image-1")
    engine = OpenRouterImageEngine()
    assert engine.model == NANO_BANANA
    assert engine.required_model == NANO_BANANA
    assert engine.transport_engine_version == "3.0.0"
    assert engine.environment_input_policy == "approved-geometry-only"
    assert engine.outpaint_detection_policy == "automatic-from-approved-geometry-transparency"
    assert engine.user_mask_required is False
    assert engine.provider_input_policy == "single-approved-geometry-reference"
    assert engine.internal_outpaint_tiles_allowed is False


def test_provider_size_selection_matches_master_orientation():
    assert OpenRouterImageEngine._select_provider_size(8064, 6048) == (1536, 1024)
    assert OpenRouterImageEngine._select_provider_size(6048, 8064) == (1024, 1536)
    assert OpenRouterImageEngine._select_provider_size(4096, 4096) == (1024, 1024)


def test_automatic_outpaint_plan_is_derived_from_geometry_alpha(tmp_path):
    geometry = tmp_path / "geometry.png"
    plan = tmp_path / "automatic-outpaint-plan.png"
    make_geometry(geometry, (32, 16))

    _, stats = OpenRouterImageEngine._derive_outpaint_plan(geometry, plan)
    with Image.open(plan) as result:
        result = result.convert("L")
        assert result.getpixel((1, 8)) == 255
        assert result.getpixel((20, 8)) == 0
    assert stats["outpaint_required"] is True
    assert stats["missing_pixels"] > 0


def test_transport_uses_one_geometry_reference_and_auto_detection(tmp_path, monkeypatch):
    geometry = tmp_path / "geometry.png"
    source_size = (2400, 1800)
    make_geometry(geometry, source_size)

    engine = OpenRouterImageEngine()
    engine.transmit_max_request_bytes = 2 * 1024 * 1024
    monkeypatch.setattr(engine, "discover_capabilities", lambda: capabilities(engine))

    result = engine.prepare_environment_inputs(
        prompt="Дорисовать отсутствующее окружение и убрать только автомобиль справа.",
        geometry_image=geometry,
        outpaint_mask=tmp_path / "ignored.png",
        output_dir=tmp_path / "transport",
        width=source_size[0],
        height=source_size[1],
    )

    assert result["provider_output_size"] == "1536x1024"
    assert result["request_body_bytes"] <= engine.transmit_max_request_bytes
    assert result["model"] == NANO_BANANA
    assert result["environment_input_policy"] == "approved-geometry-only"
    assert result["outpaint_detection"] == "automatic-from-approved-geometry-transparency"
    assert result["user_outpaint_file_required"] is False
    assert result["provider_reference_count"] == 1
    assert result["input_reference_count"] == 1
    assert result["generation_mode"] == "automatic-outpaint-and-selective-edit"
    assert result["system_prompt_contract"] == PROMPT_CONTRACT_VERSION
    assert Path(result["effective_mask_path"]).is_file()


def test_payload_contains_exact_prompt_and_only_geometry_reference(tmp_path):
    geometry = tmp_path / "approved-geometry.png"
    make_geometry(geometry, (320, 240))

    payload = OpenRouterImageEngine()._build_payload(
        prompt="Operator requirement: replace only the car on the right.",
        geometry_image=geometry,
        outpaint_mask=tmp_path / "ignored.png",
        provider_size=(1536, 1024),
    )

    assert payload["model"] == NANO_BANANA
    assert ENVIRONMENT_SYSTEM_PROMPT in payload["prompt"]
    assert PROMPT_CONTRACT_VERSION in payload["prompt"]
    assert "replace only the car on the right" in payload["prompt"]
    assert len(payload["input_references"]) == 1
    assert payload["input_references"][0]["image_url"]["url"].startswith("data:image/")


def test_prepared_request_content_length_is_exact():
    engine = OpenRouterImageEngine()
    body = b'{"model":"test","prompt":"x"}'
    prepared = engine._prepare_http_request(body)
    assert prepared.body == body
    assert int(prepared.headers["Content-Length"]) == len(body)
    assert prepared.headers["X-Marins-Transport-Engine"] == "3.0.0"
