from __future__ import annotations

import hashlib
import json
from pathlib import Path
from PIL import Image, ImageOps


class ImageEngine:
    def ingest_master(self, source: Path, project_dir: Path) -> dict:
        target_dir = project_dir / "images" / "master"
        target_dir.mkdir(parents=True, exist_ok=True)
        suffix = source.suffix.lower() if source.suffix else ".png"
        target = target_dir / f"source{suffix}"
        target.write_bytes(source.read_bytes())
        with Image.open(target) as im:
            oriented = ImageOps.exif_transpose(im)
            width, height = oriented.size
        meta = self.metadata(target)
        meta.update({"width": width, "height": height, "role": "master", "immutable": True})
        (target_dir / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), "utf-8")
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
