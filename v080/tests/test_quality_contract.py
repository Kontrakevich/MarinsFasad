from pathlib import Path

from PIL import Image

from app.quality_engine import QualityEngine


def test_quality_contract_exposes_passed_and_ok(tmp_path: Path):
    master = tmp_path / "master.png"
    candidate = tmp_path / "candidate.png"
    Image.new("RGB", (320, 240), (180, 190, 200)).save(master)
    Image.new("RGB", (320, 240), (180, 190, 200)).save(candidate)
    report = QualityEngine().inspect(master, candidate)
    assert report["ok"] is True
    assert report["passed"] is True
    assert report["checks"]["canvas_match"] is True


def test_quality_rejects_wrong_canvas(tmp_path: Path):
    master = tmp_path / "master.png"
    candidate = tmp_path / "candidate.png"
    Image.new("RGB", (320, 240), (180, 190, 200)).save(master)
    Image.new("RGB", (300, 240), (180, 190, 200)).save(candidate)
    report = QualityEngine().inspect(master, candidate)
    assert report["passed"] is False
