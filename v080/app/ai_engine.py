from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path

import requests
from PIL import Image, ImageOps


class AIEngineError(RuntimeError):
    pass


class OpenRouterImageEngine:
    endpoint = "https://openrouter.ai/api/v1/images"

    def __init__(self) -> None:
        self.api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        self.model = os.getenv("OPENROUTER_IMAGE_MODEL", "openai/gpt-image-1").strip()
        self.timeout = int(os.getenv("OPENROUTER_IMAGE_TIMEOUT", "240"))

    @staticmethod
    def _data_url(path: Path) -> str:
        suffix = path.suffix.lower()
        mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(suffix, "image/png")
        return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")

    def generate_environment(
        self,
        *,
        prompt: str,
        geometry_image: Path,
        outpaint_mask: Path,
        output_dir: Path,
        width: int,
        height: int,
    ) -> dict:
        if not self.api_key:
            raise AIEngineError("OPENROUTER_API_KEY is not configured")
        output_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "model": self.model,
            "prompt": prompt,
            "n": 1,
            "size": f"{width}x{height}",
            "quality": "high",
            "output_format": "png",
            "background": "opaque",
            "input_references": [
                {"type": "image_url", "image_url": {"url": self._data_url(geometry_image)}},
                {"type": "image_url", "image_url": {"url": self._data_url(outpaint_mask)}},
            ],
        }
        started = time.time()
        response = requests.post(
            self.endpoint,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/Kontrakevich/MarinsFasad",
                "X-Title": "Marins Facade Control Center",
            },
            json=payload,
            timeout=self.timeout,
        )
        elapsed = round(time.time() - started, 3)
        if response.status_code >= 400:
            raise AIEngineError(f"OpenRouter {response.status_code}: {response.text[:2000]}")
        data = response.json()
        items = data.get("data") or []
        if not items or not items[0].get("b64_json"):
            raise AIEngineError("OpenRouter returned no image data")
        raw = base64.b64decode(items[0]["b64_json"])
        raw_path = output_dir / "provider-output.png"
        raw_path.write_bytes(raw)
        with Image.open(raw_path) as im:
            oriented = ImageOps.exif_transpose(im)
            output_size = oriented.size
            if output_size != (width, height):
                raise AIEngineError(
                    f"Provider returned {output_size[0]}x{output_size[1]}, expected exact master canvas {width}x{height}. "
                    "The result was retained for diagnostics but not promoted."
                )
            final = oriented.convert("RGB")
            candidate = output_dir / "candidate.png"
            final.save(candidate, format="PNG", optimize=False)
        metadata = {
            "provider": "openrouter",
            "model": self.model,
            "endpoint": self.endpoint,
            "duration_seconds": elapsed,
            "width": width,
            "height": height,
            "candidate": str(candidate),
            "provider_output": str(raw_path),
            "usage": data.get("usage") or {},
            "request": {k: v for k, v in payload.items() if k != "input_references"},
        }
        (output_dir / "generation.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), "utf-8")
        return metadata
