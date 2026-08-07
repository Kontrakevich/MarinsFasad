from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from PIL import Image, ImageOps


class ImageEngine:
    working_master_quality = 95
    generation_canvas_sizes = (
        (1024, 1024),
        (1024, 1536),
        (1536, 1024),
    )

    @classmethod
    def _generation_canvas(cls, width: int, height: int) -> tuple[int, int]:
        """Mirror the default Nano Banana provider-size selection."""
        target_ratio = width / float(max(1, height))

        def score(size: tuple[int, int]) -> tuple[float, int]:
            candidate_ratio = size[0] / float(size[1])
            ratio_error = abs(math.log(candidate_ratio / target_ratio))
            orientation_penalty = 0
            if width > height and size[0] < size[1]:
                orientation_penalty = 1
            elif height > width and size[1] < size[0]:
                orientation_penalty = 1
            return ratio_error + orientation_penalty, -(size[0] * size[1])

        return min(cls.generation_canvas_sizes, key=score)

    @staticmethod
    def _fit_size(
        source_size: tuple[int, int],
        canvas_size: tuple[int, int],
    ) -> tuple[int, int]:
        source_width, source_height = source_size
        canvas_width, canvas_height = canvas_size
        scale = min(
            1.0,
            canvas_width / float(max(1, source_width)),
            canvas_height / float(max(1, source_height)),
        )
        return (
            max(1, int(round(source_width * scale))),
            max(1, int(round(source_height * scale))),
        )

    def ingest_master(self, source: Path, project_dir: Path) -> dict:
        """Archive the exact upload and return a lightweight working master.

        Grid alignment, perspective correction and later Nano Banana generation
        all operate on this working master. Large camera files therefore stop
        travelling through the runtime after upload, while the untouched source
        remains archived inside the project.
        """
        target_dir = project_dir / "images" / "master"
        target_dir.mkdir(parents=True, exist_ok=True)
        suffix = source.suffix.lower() if source.suffix else ".png"

        for old in target_dir.glob("source-original.*"):
            old.unlink(missing_ok=True)

        archive = target_dir / f"source-original{suffix}"
        archive.write_bytes(source.read_bytes())

        with Image.open(archive) as im:
            oriented = ImageOps.exif_transpose(im)
            original_width, original_height = oriented.size

        provider_canvas = self._generation_canvas(original_width, original_height)
        target_size = self._fit_size(
            (original_width, original_height),
            provider_canvas,
        )
        working = self.make_working_master(
            archive,
            project_dir,
            target_size=target_size,
        )
        working.update(
            {
                "archive_path": str(archive),
                "archive_bytes": archive.stat().st_size,
                "archive_sha256": self.metadata(archive)["sha256"],
                "original_width": original_width,
                "original_height": original_height,
                "provider_canvas_width": provider_canvas[0],
                "provider_canvas_height": provider_canvas[1],
                "role": "working-master",
                "immutable": True,
            }
        )
        (target_dir / "metadata.json").write_text(
            json.dumps(working, ensure_ascii=False, indent=2),
            "utf-8",
        )
        return working

    def make_working_master(
        self,
        source: Path,
        project_dir: Path,
        *,
        target_size: tuple[int, int],
    ) -> dict:
        target_dir = project_dir / "images" / "master"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / "source-working.webp"

        with Image.open(source) as im:
            oriented = ImageOps.exif_transpose(im)
            original_width, original_height = oriented.size
            rgba = oriented.convert("RGBA")

            target_width = max(1, int(target_size[0]))
            target_height = max(1, int(target_size[1]))
            scale = min(
                1.0,
                target_width / float(max(1, original_width)),
                target_height / float(max(1, original_height)),
            )
            working_width = max(1, int(round(original_width * scale)))
            working_height = max(1, int(round(original_height * scale)))

            if (working_width, working_height) != (original_width, original_height):
                rgba = rgba.resize(
                    (working_width, working_height),
                    Image.Resampling.LANCZOS,
                )

            rgba.save(
                target,
                format="WEBP",
                quality=self.working_master_quality,
                method=6,
            )

        meta = self.metadata(target)
        meta.update(
            {
                "role": "working-master",
                "immutable": True,
                "original_width": original_width,
                "original_height": original_height,
                "working_width": working_width,
                "working_height": working_height,
                "scale": round(scale, 8),
                "downscaled": scale < 0.999999,
                "target_width": target_width,
                "target_height": target_height,
                "quality": self.working_master_quality,
                "policy": "generation-sized-working-master",
            }
        )
        (target_dir / "working-metadata.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            "utf-8",
        )
        return meta

    def make_preview(self, source: Path, project_dir: Path, name: str = "source") -> dict:
        target_dir = project_dir / "images" / "preview"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{name}.jpg"
        with Image.open(source) as im:
            preview = ImageOps.exif_transpose(im).convert("RGB")
            preview.thumbnail((1600, 1200), Image.Resampling.LANCZOS)
            preview.save(target, quality=90, optimize=True)
        return self.metadata(target)

    def validate_canvas(self, master: Path, candidate: Path) -> dict:
        with Image.open(master) as a, Image.open(candidate) as b:
            master_size = ImageOps.exif_transpose(a).size
            candidate_size = ImageOps.exif_transpose(b).size
        return {"ok": master_size == candidate_size, "master": list(master_size), "candidate": list(candidate_size)}

    @staticmethod
    def metadata(path: Path) -> dict:
        payload = path.read_bytes()
        result = {"path": str(path), "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}
        try:
            with Image.open(path) as im:
                oriented = ImageOps.exif_transpose(im)
                result.update({"width": oriented.width, "height": oriented.height, "megapixels": round(oriented.width * oriented.height / 1_000_000, 3)})
        except Exception:
            pass
        return result
