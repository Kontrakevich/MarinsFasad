from pathlib import Path

import numpy as np
from PIL import Image

from app.ai_engine import OpenRouterImageEngine


def make_geometry_and_plan(root: Path) -> tuple[Path, Path]:
    geometry_path = root / "geometry.png"
    plan_path = root / "plan.png"

    geometry = Image.new("RGBA", (120, 90), (80, 100, 120, 255))
    geometry.paste((0, 0, 0, 0), (0, 0, 14, 90))
    geometry.paste((0, 0, 0, 0), (106, 0, 120, 90))
    geometry.paste((0, 0, 0, 0), (14, 0, 106, 8))
    geometry.save(geometry_path, format="PNG")

    alpha = np.asarray(geometry.getchannel("A"), dtype=np.uint8)
    plan = Image.fromarray(np.where(alpha < 250, 255, 0).astype(np.uint8), mode="L")
    plan.save(plan_path, format="PNG")
    return geometry_path, plan_path


def test_large_blank_outpaint_is_detected_but_not_thrown_by_detector() -> None:
    engine = OpenRouterImageEngine()
    candidate = Image.new("RGB", (80, 60), (255, 255, 255))
    plan = Image.new("L", (80, 60), 255)

    report = engine._outpaint_placeholder_stats(candidate, plan)

    assert report["outpaint_placeholder_detected"] is True
    assert report["largest_placeholder_component_ratio"] >= 0.99


def test_edge_targets_partition_every_missing_pixel_and_high_uses_more_context(tmp_path: Path) -> None:
    engine = OpenRouterImageEngine()
    geometry_path, plan_path = make_geometry_and_plan(tmp_path)

    standard = engine._build_edge_targets(
        base_image=geometry_path,
        outpaint_plan=plan_path,
        output_dir=tmp_path / "standard",
        generation_quality="standard",
    )
    high = engine._build_edge_targets(
        base_image=geometry_path,
        outpaint_plan=plan_path,
        output_dir=tmp_path / "high",
        generation_quality="high",
    )

    with Image.open(plan_path) as plan_source:
        plan = np.asarray(plan_source.convert("L"), dtype=np.uint8) > 0
    covered = np.zeros_like(plan, dtype=bool)
    for target in high:
        x1, y1, x2, y2 = target["bbox"]
        with Image.open(target["mask"]) as mask_source:
            mask = np.asarray(mask_source.convert("L"), dtype=np.uint8) > 0
        covered[y1:y2, x1:x2] |= mask

    assert high
    assert np.array_equal(covered, plan)
    assert {target["side"] for target in high}.issubset({"top", "bottom", "left", "right"})
    assert min(target["padding"] for target in high) >= min(target["padding"] for target in standard)


def test_placeholder_result_routes_to_quality_edge_refinement(monkeypatch, tmp_path: Path) -> None:
    engine = OpenRouterImageEngine()
    geometry_path, plan_path = make_geometry_and_plan(tmp_path)
    repaired_candidate = tmp_path / "repaired.png"
    Image.new("RGB", (120, 90), (100, 120, 140)).save(repaired_candidate, format="PNG")

    calls = []

    def fake_refinement(**kwargs):
        calls.append(kwargs)
        return {
            "candidate": str(repaired_candidate),
            "outpaint_refinement_used": True,
            "outpaint_fallback_used": True,
            "outpaint_fallback_mode": engine.outpaint_fallback_mode,
            "outpaint_refinement_reason": "full-frame-placeholder",
            "fallback_provider_calls": 3,
            "fallback_failed_edges": [],
            "fallback_remaining_pixels": 0,
            "fallback_final_placeholder": {"outpaint_placeholder_detected": False},
        }

    monkeypatch.setattr(engine, "_run_edge_tile_refinement", fake_refinement)
    result = engine._repair_or_refine_outpaint(
        result={
            "candidate": str(tmp_path / "blank.png"),
            "generation_mode": "outpaint",
            "requested_generation_mode": "outpaint",
            "outpaint_placeholder_detected": True,
            "automatic_outpaint_plan": str(plan_path),
            "provider_call_count": 1,
        },
        kwargs={
            "prompt": "GENERATION MODE\nOUTPAINT\n\nGENERATION QUALITY\nHIGH\n\nReconstruct missing surroundings.",
            "geometry_image": geometry_path,
            "outpaint_mask": plan_path,
            "output_dir": tmp_path / "environment",
            "prepared_input": {"effective_mask_path": str(plan_path)},
        },
        mode="outpaint",
    )

    assert len(calls) == 1
    assert calls[0]["require_complete"] is True
    assert calls[0]["seed_candidate"] is None
    assert result["candidate"] == str(repaired_candidate)
    assert result["outpaint_fallback_used"] is True
    assert result["initial_outpaint_placeholder_detected"] is True
    assert result["outpaint_placeholder_detected"] is False
    assert result["provider_call_count"] == 4


def test_high_quality_refines_even_nonblank_outpaint(monkeypatch, tmp_path: Path) -> None:
    engine = OpenRouterImageEngine()
    geometry_path, plan_path = make_geometry_and_plan(tmp_path)
    seed = tmp_path / "seed.png"
    refined = tmp_path / "refined.png"
    Image.new("RGB", (120, 90), (90, 110, 130)).save(seed, format="PNG")
    Image.new("RGB", (120, 90), (100, 120, 140)).save(refined, format="PNG")
    calls = []

    def fake_refinement(**kwargs):
        calls.append(kwargs)
        return {
            "candidate": str(refined),
            "outpaint_refinement_used": True,
            "outpaint_fallback_used": False,
            "outpaint_refinement_reason": "quality-edge-refine",
            "fallback_provider_calls": 2,
            "fallback_failed_edges": [],
            "fallback_remaining_pixels": 0,
            "fallback_final_placeholder": {"outpaint_placeholder_detected": False},
        }

    monkeypatch.setattr(engine, "_run_edge_tile_refinement", fake_refinement)
    result = engine._repair_or_refine_outpaint(
        result={
            "candidate": str(seed),
            "generation_mode": "outpaint",
            "requested_generation_mode": "outpaint",
            "outpaint_placeholder_detected": False,
            "automatic_outpaint_plan": str(plan_path),
            "provider_call_count": 1,
        },
        kwargs={
            "prompt": "GENERATION MODE\nOUTPAINT\n\nGENERATION QUALITY\nHIGH\n\nContinue the complete scene.",
            "geometry_image": geometry_path,
            "outpaint_mask": plan_path,
            "output_dir": tmp_path / "environment",
            "prepared_input": {"effective_mask_path": str(plan_path)},
        },
        mode="outpaint",
    )

    assert len(calls) == 1
    assert calls[0]["require_complete"] is False
    assert calls[0]["seed_candidate"] == seed
    assert result["candidate"] == str(refined)
    assert result["outpaint_refinement_used"] is True
    assert result["provider_call_count"] == 3


def test_standard_quality_keeps_successful_full_frame_without_extra_calls(monkeypatch, tmp_path: Path) -> None:
    engine = OpenRouterImageEngine()
    called = False

    def unexpected_refinement(**kwargs):
        nonlocal called
        called = True
        raise AssertionError("refinement must not run")

    monkeypatch.setattr(engine, "_run_edge_tile_refinement", unexpected_refinement)
    result = engine._repair_or_refine_outpaint(
        result={
            "generation_mode": "outpaint",
            "requested_generation_mode": "outpaint",
            "outpaint_placeholder_detected": False,
        },
        kwargs={
            "prompt": "GENERATION MODE\nOUTPAINT\n\nGENERATION QUALITY\nSTANDARD\n",
            "output_dir": tmp_path,
        },
        mode="outpaint",
    )

    assert called is False
    assert result["outpaint_refinement_used"] is False
    assert result["generation_quality"] == "standard"


def test_feather_blending_never_changes_valid_pixels() -> None:
    engine = OpenRouterImageEngine()
    existing = Image.new("RGB", (64, 48), (20, 40, 60))
    context = Image.new("RGB", (64, 48), (20, 40, 60))
    generated = Image.new("RGB", (64, 48), (180, 150, 120))
    mask = Image.new("L", (64, 48), 0)
    mask.paste(255, (0, 32, 64, 48))

    result = engine._harmonize_and_blend_inside_missing(
        generated=generated,
        existing=existing,
        context=context,
        mask=mask,
        feather_px=12,
        tone_match_strength=0.7,
    )

    result_np = np.asarray(result, dtype=np.uint8)
    existing_np = np.asarray(existing, dtype=np.uint8)
    mask_np = np.asarray(mask, dtype=np.uint8) > 0
    assert np.array_equal(result_np[~mask_np], existing_np[~mask_np])
    assert np.any(result_np[mask_np] != existing_np[mask_np])
