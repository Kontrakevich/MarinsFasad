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


def test_edge_targets_partition_every_missing_pixel(tmp_path: Path) -> None:
    engine = OpenRouterImageEngine()
    geometry_path, plan_path = make_geometry_and_plan(tmp_path)

    targets = engine._build_edge_targets(
        base_image=geometry_path,
        outpaint_plan=plan_path,
        output_dir=tmp_path / "targets",
    )

    with Image.open(plan_path) as plan_source:
        plan = np.asarray(plan_source.convert("L"), dtype=np.uint8) > 0
    covered = np.zeros_like(plan, dtype=bool)
    for target in targets:
        x1, y1, x2, y2 = target["bbox"]
        with Image.open(target["mask"]) as mask_source:
            mask = np.asarray(mask_source.convert("L"), dtype=np.uint8) > 0
        covered[y1:y2, x1:x2] |= mask

    assert targets
    assert np.array_equal(covered, plan)
    assert {target["side"] for target in targets}.issubset({"top", "bottom", "left", "right"})


def test_placeholder_result_routes_to_edge_fallback(monkeypatch, tmp_path: Path) -> None:
    engine = OpenRouterImageEngine()
    geometry_path, plan_path = make_geometry_and_plan(tmp_path)
    repaired_candidate = tmp_path / "repaired.png"
    Image.new("RGB", (120, 90), (100, 120, 140)).save(repaired_candidate, format="PNG")

    calls = []

    def fake_fallback(**kwargs):
        calls.append(kwargs)
        return {
            "candidate": str(repaired_candidate),
            "outpaint_fallback_used": True,
            "outpaint_fallback_mode": engine.outpaint_fallback_mode,
            "outpaint_fallback_reason": "full-frame-placeholder",
            "fallback_provider_calls": 3,
            "fallback_failed_edges": [],
            "fallback_remaining_pixels": 0,
        }

    monkeypatch.setattr(engine, "_run_edge_tile_fallback", fake_fallback)
    result = engine._repair_placeholder_if_needed(
        result={
            "candidate": str(tmp_path / "blank.png"),
            "generation_mode": "outpaint",
            "requested_generation_mode": "outpaint",
            "outpaint_placeholder_detected": True,
            "automatic_outpaint_plan": str(plan_path),
            "provider_call_count": 1,
        },
        kwargs={
            "prompt": "GENERATION MODE\nOUTPAINT\nReconstruct missing surroundings.",
            "geometry_image": geometry_path,
            "outpaint_mask": plan_path,
            "output_dir": tmp_path / "environment",
            "prepared_input": {"effective_mask_path": str(plan_path)},
        },
        mode="outpaint",
    )

    assert len(calls) == 1
    assert result["candidate"] == str(repaired_candidate)
    assert result["outpaint_fallback_used"] is True
    assert result["initial_outpaint_placeholder_detected"] is True
    assert result["outpaint_placeholder_detected"] is False
    assert result["provider_call_count"] == 4


def test_successful_outpaint_does_not_start_fallback(monkeypatch, tmp_path: Path) -> None:
    engine = OpenRouterImageEngine()
    called = False

    def unexpected_fallback(**kwargs):
        nonlocal called
        called = True
        raise AssertionError("fallback must not run")

    monkeypatch.setattr(engine, "_run_edge_tile_fallback", unexpected_fallback)
    result = engine._repair_placeholder_if_needed(
        result={
            "generation_mode": "outpaint",
            "requested_generation_mode": "outpaint",
            "outpaint_placeholder_detected": False,
        },
        kwargs={"output_dir": tmp_path},
        mode="outpaint",
    )

    assert called is False
    assert result["outpaint_fallback_used"] is False
