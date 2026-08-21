from pathlib import Path

from PIL import Image

from app.ai_engine import OpenRouterImageEngine
from app.image_engine import ImageEngine


def test_large_landscape_source_is_downscaled_before_grid(tmp_path: Path) -> None:
    source = tmp_path / "camera.jpg"
    Image.new("RGB", (3200, 2400), (120, 130, 140)).save(source, quality=90)

    project = tmp_path / "project"
    result = ImageEngine().ingest_master(source, project)

    working = Path(result["path"])
    archive = Path(result["archive_path"])

    assert archive.is_file()
    assert working.is_file()
    assert archive != working
    assert (result["original_width"], result["original_height"]) == (3200, 2400)
    assert (result["width"], result["height"]) == (1365, 1024)
    assert result["downscaled"] is True
    assert result["policy"] == "generation-sized-working-master"

    with Image.open(archive) as image:
        assert image.size == (3200, 2400)
    with Image.open(working) as image:
        assert image.size == (1365, 1024)


def test_working_master_uses_same_default_provider_canvas_selection() -> None:
    image_engine = ImageEngine()
    for width, height in (
        (8064, 6048),
        (6048, 8064),
        (4096, 4096),
        (4032, 3024),
    ):
        assert image_engine._generation_canvas(width, height) == OpenRouterImageEngine._select_provider_size(width, height)


def test_small_source_is_never_upscaled(tmp_path: Path) -> None:
    source = tmp_path / "small.png"
    Image.new("RGB", (800, 600), (100, 110, 120)).save(source)

    result = ImageEngine().ingest_master(source, tmp_path / "project")

    assert (result["width"], result["height"]) == (800, 600)
    assert result["downscaled"] is False
