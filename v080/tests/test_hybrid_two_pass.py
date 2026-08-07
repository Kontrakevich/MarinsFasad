from pathlib import Path

from PIL import Image

from app.ai_engine import OpenRouterImageEngine


HYBRID_PROMPT = (
    "OPERATOR PROMPT — EXECUTE EXACTLY\n"
    "1. Убрать столбы и провода.\n"
    "2. Сделать облачную погоду.\n\n"
    "GENERATION MODE\nHYBRID\n\n"
    "GENERATION QUALITY\nSTANDARD\n\n"
    "FINAL COMMAND — EXECUTE THE OPERATOR PROMPT\n"
    "Убрать столбы и провода. Сделать облачную погоду."
)


def make_geometry(path: Path) -> None:
    image = Image.new("RGBA", (100, 80), (50, 60, 70, 255))
    image.paste((0, 0, 0, 0), (0, 0, 15, 80))
    image.save(path, format="PNG")


def test_hybrid_runs_semantic_edit_then_outpaint(monkeypatch, tmp_path: Path) -> None:
    geometry = tmp_path / "geometry.png"
    plan = tmp_path / "plan.png"
    output = tmp_path / "environment"
    primary_candidate = tmp_path / "primary.png"
    final_candidate = tmp_path / "final.png"
    make_geometry(geometry)
    Image.new("L", (100, 80), 255).save(plan, format="PNG")
    Image.new("RGB", (100, 80), (110, 140, 170)).save(primary_candidate, format="PNG")
    Image.new("RGB", (100, 80), (115, 145, 175)).save(final_candidate, format="PNG")

    engine = OpenRouterImageEngine()
    calls = []

    def fake_single_pass(**kwargs):
        calls.append(kwargs)
        candidate = primary_candidate if len(calls) == 1 else final_candidate
        return {
            "candidate": str(candidate),
            "provider": "openrouter",
            "model": engine.model,
            "duration_seconds": 1.0,
            "usage": {},
            "request": {"prompt": kwargs["prompt"]},
            "transport": kwargs.get("prepared_input") or {},
        }

    monkeypatch.setattr(engine, "_single_pass", fake_single_pass)
    monkeypatch.setattr(
        engine,
        "prepare_environment_inputs",
        lambda **kwargs: {
            "requested_generation_mode": "outpaint",
            "generation_mode": "outpaint",
            "outpaint_required": True,
        },
    )

    result = engine.generate_environment(
        prompt=HYBRID_PROMPT,
        geometry_image=geometry,
        outpaint_mask=plan,
        output_dir=output,
        width=100,
        height=80,
        prepared_input={"outpaint_required": True},
    )

    assert len(calls) == 2
    assert calls[0]["prompt"] == HYBRID_PROMPT
    assert "INTERNAL HYBRID PASS 2/2 — OUTPAINT ONLY" in calls[1]["prompt"]
    assert "GENERATION MODE\nOUTPAINT" in calls[1]["prompt"]
    assert "FULL ORIGINAL COMPILED PROMPT — MANDATORY CONTEXT" in calls[1]["prompt"]
    assert HYBRID_PROMPT in calls[1]["prompt"]
    assert result["hybrid_two_pass"] is True
    assert result["provider_call_count"] == 2
    assert result["generation_mode"] == "hybrid"
    assert result["generation_quality"] == "standard"

    intermediate = Path(result["hybrid_intermediate"])
    with Image.open(intermediate) as image:
        image = image.convert("RGBA")
        assert image.getpixel((5, 40))[3] == 0
        assert image.getpixel((50, 40)) == (110, 140, 170, 255)


def test_hybrid_skips_second_call_when_no_outpaint_is_needed(monkeypatch, tmp_path: Path) -> None:
    geometry = tmp_path / "geometry.png"
    plan = tmp_path / "plan.png"
    candidate = tmp_path / "candidate.png"
    Image.new("RGBA", (100, 80), (50, 60, 70, 255)).save(geometry, format="PNG")
    Image.new("L", (100, 80), 0).save(plan, format="PNG")
    Image.new("RGB", (100, 80), (100, 120, 140)).save(candidate, format="PNG")

    engine = OpenRouterImageEngine()
    calls = []

    def fake_single_pass(**kwargs):
        calls.append(kwargs)
        return {
            "candidate": str(candidate),
            "provider": "openrouter",
            "model": engine.model,
            "duration_seconds": 1.0,
            "usage": {},
            "request": {"prompt": kwargs["prompt"]},
            "transport": kwargs.get("prepared_input") or {},
        }

    monkeypatch.setattr(engine, "_single_pass", fake_single_pass)
    result = engine.generate_environment(
        prompt=HYBRID_PROMPT,
        geometry_image=geometry,
        outpaint_mask=plan,
        output_dir=tmp_path / "environment",
        width=100,
        height=80,
        prepared_input={"outpaint_required": False},
    )

    assert len(calls) == 1
    assert result["provider_call_count"] == 1
    assert result["hybrid_two_pass"] is False
    assert result["outpaint_second_pass_skipped"] is True
    assert result["generation_quality"] == "standard"
