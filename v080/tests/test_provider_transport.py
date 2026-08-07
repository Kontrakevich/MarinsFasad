from pathlib import Path

from PIL import Image

from app.ai_engine import OpenRouterImageEngine
from app.prompt_engine import GENERATION_MODE_MARKER, GENERATION_QUALITY_MARKER
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


def test_nano_banana_and_skill_contract_are_hard_locked(monkeypatch):
    monkeypatch.setenv("OPENROUTER_IMAGE_MODEL", "openai/gpt-image-1")
    engine = OpenRouterImageEngine()
    assert engine.model == NANO_BANANA
    assert engine.required_model == NANO_BANANA
    assert engine.transport_engine_version == "3.4.0"
    assert engine.default_generation_mode == "hybrid"
    assert engine.available_generation_modes == ("hybrid", "relight", "edit", "outpaint")
    assert engine.available_generation_qualities == ("draft", "standard", "high", "max")
    assert engine.default_generation_quality == "high"
    assert engine.skill_contract_version == "outpaint-relight-edit-hybrid-quality-v2"
    assert engine.outpaint_fallback_mode == "quality-aware-edge-refine"
    assert engine.environment_input_policy == "approved-geometry-only"
    assert engine.outpaint_detection_policy == "automatic-from-approved-geometry-transparency"
    assert engine.user_mask_required is False
    assert engine.provider_input_policy == "single-approved-geometry-reference"
    assert engine.internal_outpaint_tiles_allowed is False
    assert engine.missing_region_transport_policy == "native-transparency-single-reference"
    assert engine.outpaint_repair_mode == "hybrid-second-pass"


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


def test_reference_keeps_missing_pixels_transparent_without_service_colours():
    geometry = Image.new("RGBA", (24, 16), (40, 60, 80, 255))
    geometry.paste((0, 0, 0, 0), (0, 0, 6, 16))
    plan = Image.new("L", (24, 16), 0)
    plan.paste(255, (0, 0, 6, 16))

    transport_geometry, transport_plan, _ = OpenRouterImageEngine._reference_canvases(
        geometry,
        plan,
        (24, 16),
    )
    assert transport_geometry.getpixel((2, 8))[3] == 0
    assert transport_geometry.getpixel((12, 8))[:3] == (40, 60, 80)
    assert transport_plan.getpixel((2, 8)) == 255


def test_transport_uses_one_geometry_reference_and_hybrid_default(tmp_path, monkeypatch):
    geometry = tmp_path / "geometry.png"
    source_size = (2400, 1800)
    make_geometry(geometry, source_size)

    engine = OpenRouterImageEngine()
    engine.transmit_max_request_bytes = 2 * 1024 * 1024
    monkeypatch.setattr(engine, "discover_capabilities", lambda: capabilities(engine))

    prompt = (
        f"{GENERATION_MODE_MARKER}\nHYBRID\n\n"
        f"{GENERATION_QUALITY_MARKER}\nHIGH\n\n"
        "Убрать столбы и провода. Сделать облачную погоду."
    )
    result = engine.prepare_environment_inputs(
        prompt=prompt,
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
    assert result["generation_mode"] == "hybrid"
    assert result["requested_generation_mode"] == "hybrid"
    assert result["visual_reference_policy"] == "native-alpha-no-service-pattern"
    assert result["system_prompt_contract"] == PROMPT_CONTRACT_VERSION
    assert Path(result["effective_mask_path"]).is_file()


def test_relight_mode_is_recognised_as_full_frame_semantic_skill():
    engine = OpenRouterImageEngine()
    prompt = (
        f"{GENERATION_MODE_MARKER}\nRELIGHT\n\n"
        f"{GENERATION_QUALITY_MARKER}\nMAX\n\n"
        "Сделать вечернее освещение, тёплый свет из окон и мокрый асфальт."
    )
    assert engine._mode_from_prompt(prompt) == "relight"
    assert engine._normalize_generation_mode("relight") == "relight"
    assert engine._quality_from_prompt(prompt) == "max"
    assert "relight" in engine.available_generation_modes


def test_payload_contains_prompt_and_only_geometry_reference(tmp_path):
    geometry = tmp_path / "approved-geometry.png"
    make_geometry(geometry, (320, 240))

    payload = OpenRouterImageEngine()._build_payload(
        prompt="Operator requirement: remove the poles and make the weather cloudy.",
        geometry_image=geometry,
        outpaint_mask=tmp_path / "ignored.png",
        provider_size=(1536, 1024),
    )

    assert payload["model"] == NANO_BANANA
    assert ENVIRONMENT_SYSTEM_PROMPT in payload["prompt"]
    assert PROMPT_CONTRACT_VERSION in payload["prompt"]
    assert "remove the poles" in payload["prompt"]
    assert len(payload["input_references"]) == 1
    assert payload["input_references"][0]["image_url"]["url"].startswith("data:image/")


def test_internal_outpaint_prompt_receives_complete_original_prompt():
    engine = OpenRouterImageEngine()
    prompt = (
        "OPERATOR PROMPT — EXECUTE EXACTLY\n"
        "1. Убрать столбы и провода.\n"
        "2. Сделать облачную погоду.\n"
        "3. Мокрый асфальт и тёплый свет в окнах.\n\n"
        "GENERATION MODE\nHYBRID\n\n"
        "GENERATION QUALITY\nHIGH\n\n"
        "FINAL COMMAND — EXECUTE THE OPERATOR PROMPT\n"
        "Выполнить все три требования."
    )
    internal = engine._internal_outpaint_prompt(prompt)
    assert internal.startswith("INTERNAL HYBRID PASS 2/2 — OUTPAINT ONLY")
    assert "GENERATION MODE\nOUTPAINT" in internal
    assert "GENERATION QUALITY\nHIGH" in internal
    assert "FULL ORIGINAL COMPILED PROMPT — MANDATORY CONTEXT" in internal
    assert prompt in internal
    assert "Мокрый асфальт и тёплый свет в окнах." in internal


def test_prepared_request_content_length_is_exact():
    engine = OpenRouterImageEngine()
    body = b'{"model":"test","prompt":"x"}'
    prepared = engine._prepare_http_request(body)
    assert prepared.body == body
    assert int(prepared.headers["Content-Length"]) == len(body)
    assert prepared.headers["X-Marins-Transport-Engine"] == "3.4.0"
