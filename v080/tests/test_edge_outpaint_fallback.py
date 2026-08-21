from pathlib import Path

from PIL import Image

from app.ai_engine import OpenRouterImageEngine


def make_geometry(path: Path) -> Path:
    image = Image.new("RGBA", (64, 48), (70, 80, 90, 255))
    image.paste((0, 0, 0, 0), (0, 0, 16, 48))
    image.save(path, format="PNG")
    return path


def make_plan(path: Path) -> Path:
    plan = Image.new("L", (64, 48), 0)
    plan.paste(255, (0, 0, 16, 48))
    plan.save(path, format="PNG")
    return path


def test_white_outpaint_is_recorded_for_refinement_instead_of_raising(tmp_path: Path) -> None:
    engine = OpenRouterImageEngine()
    geometry = make_geometry(tmp_path / "geometry.png")
    plan = make_plan(tmp_path / "plan.png")
    provider = tmp_path / "provider.png"
    Image.new("RGB", (64, 48), (255, 255, 255)).save(provider, format="PNG")

    result = engine._promote_provider_output(
        provider_output=provider,
        geometry_image=geometry,
        outpaint_mask=plan,
        prepared={
            "content_box_normalized": {
                "x": 0.0,
                "y": 0.0,
                "width": 1.0,
                "height": 1.0,
            },
            "effective_mask_path": str(plan),
            "requested_generation_mode": "outpaint",
            "generation_mode": "outpaint",
        },
        output_dir=tmp_path / "promotion",
        width=64,
        height=48,
    )

    assert Path(result["candidate"]).is_file()
    assert result["outpaint_placeholder_detected"] is True
    assert result["initial_outpaint_qc_blocking"] is False
    assert result["generation_mode"] == "outpaint"


def test_placeholder_automatically_promotes_quality_edge_refinement_candidate(monkeypatch, tmp_path: Path) -> None:
    engine = OpenRouterImageEngine()
    geometry = make_geometry(tmp_path / "geometry.png")
    plan = make_plan(tmp_path / "plan.png")
    repaired_candidate = tmp_path / "repaired.png"
    Image.new("RGB", (64, 48), (95, 110, 125)).save(repaired_candidate, format="PNG")

    calls = []

    def fake_refinement(**kwargs):
        calls.append(kwargs)
        return {
            "candidate": str(repaired_candidate),
            "outpaint_refinement_used": True,
            "outpaint_fallback_used": True,
            "outpaint_fallback_mode": engine.outpaint_fallback_mode,
            "outpaint_refinement_reason": "full-frame-placeholder",
            "fallback_provider_calls": 2,
            "fallback_failed_edges": [],
            "fallback_remaining_pixels": 0,
            "fallback_final_placeholder": {"outpaint_placeholder_detected": False},
        }

    monkeypatch.setattr(engine, "_run_edge_tile_refinement", fake_refinement)

    result = engine._repair_or_refine_outpaint(
        result={
            "candidate": str(tmp_path / "bad.png"),
            "automatic_outpaint_plan": str(plan),
            "outpaint_placeholder_detected": True,
            "provider_call_count": 1,
        },
        kwargs={
            "prompt": (
                "GENERATION MODE\nOUTPAINT\n\n"
                "GENERATION QUALITY\nSTANDARD\n\n"
                "Reconstruct missing surroundings."
            ),
            "geometry_image": geometry,
            "outpaint_mask": plan,
            "output_dir": tmp_path / "environment",
            "prepared_input": {"effective_mask_path": str(plan)},
        },
        mode="outpaint",
    )

    assert len(calls) == 1
    assert Path(result["candidate"]) == repaired_candidate
    assert result["environment_master"] == str(repaired_candidate)
    assert result["initial_outpaint_placeholder_detected"] is True
    assert result["outpaint_placeholder_detected"] is False
    assert result["outpaint_fallback_used"] is True
    assert result["outpaint_fallback_mode"] == "quality-aware-edge-refine"
    assert result["provider_call_count"] == 3


def test_standard_valid_outpaint_does_not_trigger_extra_refinement(monkeypatch, tmp_path: Path) -> None:
    engine = OpenRouterImageEngine()
    called = False

    def forbidden_refinement(**kwargs):
        nonlocal called
        called = True
        raise AssertionError("quality edge refinement must not run for a valid STANDARD result")

    monkeypatch.setattr(engine, "_run_edge_tile_refinement", forbidden_refinement)
    original = {"candidate": "ok.png", "outpaint_placeholder_detected": False}
    result = engine._repair_or_refine_outpaint(
        result=original,
        kwargs={
            "prompt": "GENERATION MODE\nOUTPAINT\n\nGENERATION QUALITY\nSTANDARD",
            "output_dir": tmp_path,
        },
        mode="outpaint",
    )

    assert result is original
    assert result["outpaint_fallback_used"] is False
    assert result["outpaint_refinement_used"] is False
    assert result["generation_quality"] == "standard"
    assert called is False
