from __future__ import annotations

import hashlib
import json
from pathlib import Path
from PIL import Image, ImageOps


class ImageEngine:
    working_master_quality = 95

    def ingest_master(self, source: Path, project_dir: Path) -> dict:
        """Archive the exact uploaded source without resizing or recompression."""
        target_dir = project_dir / "images" / "master"
        target_dir.mkdir(parents=True, exist_ok=True)
        suffix = source.suffix.lower() if source.suffix else ".png"

        # Remove an older archived upload with another extension so every project
        # has one unambiguous original source.
        for old in target_dir.glob("source-original.*"):
            old.unlink(missing_ok=True)

        target = target_dir / f"source-original{suffix}"
        target.write_bytes(source.read_bytes())
        with Image.open(target) as im:
            oriented = ImageOps.exif_transpose(im)
            width, height = oriented.size
        meta = self.metadata(target)
        meta.update(
            {
                "width": width,
                "height": height,
                "role": "source-archive",
                "immutable": True,
            }
        )
        (target_dir / "original-metadata.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            "utf-8",
        )
        return meta

    def make_working_master(
        self,
        source: Path,
        project_dir: Path,
        *,
        target_size: tuple[int, int],
    ) -> dict:
        """Create the lightweight master used by grid, geometry and generation.

        ``target_size`` is derived from the same provider canvas selection used
        by Nano Banana. The image is never upscaled and its aspect ratio is
        preserved exactly.
        """
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

            # WebP keeps the working file compact while preserving enough detail
            # for perspective-grid alignment and Nano Banana reference input.
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
