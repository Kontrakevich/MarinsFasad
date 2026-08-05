from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import re
import time
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageOps


class AIEngineError(RuntimeError):
    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


class OpenRouterImageEngine:
    endpoint = "https://openrouter.ai/api/v1/images"
    image_models_endpoint = "https://openrouter.ai/api/v1/images/models"
    transport_engine_version = "2.1.0"
    gateway_hard_max_request_bytes = 50 * 1024 * 1024

    def __init__(self) -> None:
        self.api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        self.model = os.getenv("OPENROUTER_IMAGE_MODEL", "openai/gpt-image-1").strip()
        self.timeout = int(os.getenv("OPENROUTER_IMAGE_TIMEOUT", "240"))
        self.capability_timeout = int(os.getenv("OPENROUTER_CAPABILITY_TIMEOUT", "15"))
        self.safety_margin = min(0.95, max(0.50, float(os.getenv("OPENROUTER_REQUEST_SAFETY_MARGIN", "0.88"))))
        self.max_input_side = max(0, int(os.getenv("OPENROUTER_MAX_INPUT_SIDE", "0")))
        self.max_input_pixels = max(0, int(os.getenv("OPENROUTER_MAX_INPUT_PIXELS", "0")))
        self.transport_format = os.getenv("OPENROUTER_TRANSPORT_FORMAT", "webp").strip().lower()
        self._learned_max_request_bytes: int | None = None

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/Kontrakevich/MarinsFasad",
            "X-Title": "Marins Facade Control Center",
        }

    @staticmethod
    def _data_url(path: Path) -> str:
        suffix = path.suffix.lower()
        mime = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }.get(suffix, "image/png")
        return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")

    @staticmethod
    def _request_bytes(payload: dict) -> bytes:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    @staticmethod
    def _extract_request_limit(text: str) -> int | None:
        patterns = (
            r"maximum allowed size of\s+(\d+)\s+bytes",
            r"max(?:imum)?(?: request)?(?: body)? size[^\d]*(\d+)",
            r"limit[^\d]*(\d+)\s+bytes",
        )
        for pattern in patterns:
            match = re.search(pattern, text or "", flags=re.IGNORECASE)
            if match:
                value = int(match.group(1))
                if value > 1024:
                    return value
        return None

    @staticmethod
    def _header_limit(headers: requests.structures.CaseInsensitiveDict) -> int | None:
        for key in (
            "x-max-request-bytes",
            "x-max-request-size",
            "x-request-body-limit",
            "max-content-length",
        ):
            value = headers.get(key)
            if not value:
                continue
            match = re.search(r"(\d+)", value)
            if match and int(match.group(1)) > 1024:
                return int(match.group(1))
        return None

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _effective_limit(self, candidate: int | None = None) -> int:
        values = [self.gateway_hard_max_request_bytes]
        configured = int(os.getenv("OPENROUTER_MAX_REQUEST_BYTES", "0") or 0)
        if configured > 0:
            values.append(configured)
        if self._learned_max_request_bytes:
            values.append(self._learned_max_request_bytes)
        if candidate:
            values.append(candidate)
        return max(1024 * 1024, min(values))

    def discover_capabilities(self) -> dict:
        max_request_bytes = self._effective_limit()
        limit_source = "gateway_hard_cap"
        supported_parameters: dict[str, Any] = {}
        providers: list[str] = []
        discovery_errors: list[str] = []

        if self.api_key and "/" in self.model:
            author, slug = self.model.split("/", 1)
            url = f"{self.image_models_endpoint}/{author}/{slug}/endpoints"
            try:
                response = requests.get(url, headers=self.headers, timeout=self.capability_timeout)
                if response.ok:
                    data = response.json()
                    for endpoint in data.get("endpoints") or []:
                        provider = endpoint.get("provider_name") or endpoint.get("provider_slug")
                        if provider and provider not in providers:
                            providers.append(str(provider))
                        for key, descriptor in (endpoint.get("supported_parameters") or {}).items():
                            supported_parameters.setdefault(key, descriptor)
                else:
                    discovery_errors.append(f"model_endpoints_http_{response.status_code}")
            except Exception as exc:
                discovery_errors.append(f"model_endpoints:{type(exc).__name__}")

        if self.api_key:
            try:
                response = requests.options(self.endpoint, headers=self.headers, timeout=self.capability_timeout)
                header_limit = self._header_limit(response.headers)
                if header_limit:
                    max_request_bytes = self._effective_limit(header_limit)
                    limit_source = "response_header_capped"
            except Exception as exc:
                discovery_errors.append(f"options:{type(exc).__name__}")

        if self._learned_max_request_bytes:
            max_request_bytes = self._effective_limit(self._learned_max_request_bytes)
            limit_source = "observed_413_capped"

        return {
            "provider": "openrouter",
            "model": self.model,
            "transport_engine_version": self.transport_engine_version,
            "gateway_hard_max_request_bytes": self.gateway_hard_max_request_bytes,
            "max_request_bytes": int(max_request_bytes),
            "safe_request_bytes": int(max_request_bytes * self.safety_margin),
            "request_limit_source": limit_source,
            "safety_margin": self.safety_margin,
            "supported_parameters": supported_parameters,
            "providers": providers,
            "discovery_errors": discovery_errors,
        }

    def _build_payload(
        self,
        *,
        prompt: str,
        geometry_image: Path,
        outpaint_mask: Path,
        width: int,
        height: int,
    ) -> dict:
        return {
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

    def _save_transport_geometry(self, image: Image.Image, directory: Path) -> tuple[Path, str]:
        preferred = self.transport_format
        if preferred == "webp":
            path = directory / "geometry-input.webp"
            try:
                image.save(path, format="WEBP", lossless=True, quality=100, method=6, exact=True)
                return path, "webp-lossless"
            except Exception:
                pass
        path = directory / "geometry-input.png"
        image.save(path, format="PNG", optimize=True, compress_level=9)
        return path, "png-lossless"

    @staticmethod
    def _save_transport_mask(mask: Image.Image, directory: Path) -> Path:
        path = directory / "outpaint-mask.png"
        mask.save(path, format="PNG", optimize=True, compress_level=9)
        return path

    def prepare_environment_inputs(
        self,
        *,
        prompt: str,
        geometry_image: Path,
        outpaint_mask: Path,
        output_dir: Path,
        width: int,
        height: int,
        forced_max_request_bytes: int | None = None,
    ) -> dict:
        output_dir.mkdir(parents=True, exist_ok=True)
        capabilities = self.discover_capabilities()
        if forced_max_request_bytes:
            capped = self._effective_limit(forced_max_request_bytes)
            capabilities["max_request_bytes"] = capped
            capabilities["safe_request_bytes"] = int(capped * self.safety_margin)
            capabilities["request_limit_source"] = "forced_or_observed_limit_capped"
        safe_request_bytes = min(
            int(capabilities["safe_request_bytes"]),
            int(self.gateway_hard_max_request_bytes * self.safety_margin),
        )

        with Image.open(geometry_image) as source:
            geometry_master = ImageOps.exif_transpose(source).convert("RGBA")
        with Image.open(outpaint_mask) as source_mask:
            mask_master = ImageOps.exif_transpose(source_mask).convert("L")
        if mask_master.size != geometry_master.size:
            raise AIEngineError(
                f"Outpaint mask {mask_master.size[0]}x{mask_master.size[1]} does not match geometry {geometry_master.size[0]}x{geometry_master.size[1]}"
            )

        original_size = geometry_master.size
        scale = 1.0
        if self.max_input_side and max(original_size) > self.max_input_side:
            scale = min(scale, self.max_input_side / max(original_size))
        if self.max_input_pixels and original_size[0] * original_size[1] > self.max_input_pixels:
            scale = min(scale, math.sqrt(self.max_input_pixels / float(original_size[0] * original_size[1])))

        request_body = b""
        final_payload: dict | None = None
        geometry_path: Path | None = None
        mask_path: Path | None = None
        encoding = ""
        attempt = 0

        while attempt < 18:
            attempt += 1
            target_width = max(64, int(round(original_size[0] * scale)))
            target_height = max(64, int(round(original_size[1] * scale)))
            target_size = (target_width, target_height)

            if target_size == original_size:
                transport_geometry = geometry_master.copy()
                transport_mask = mask_master.copy()
            else:
                transport_geometry = geometry_master.resize(target_size, Image.Resampling.LANCZOS)
                transport_mask = mask_master.resize(target_size, Image.Resampling.NEAREST)

            transport_mask = transport_mask.point(lambda value: 255 if value >= 128 else 0, mode="L")
            geometry_path, encoding = self._save_transport_geometry(transport_geometry, output_dir)
            mask_path = self._save_transport_mask(transport_mask, output_dir)
            final_payload = self._build_payload(
                prompt=prompt,
                geometry_image=geometry_path,
                outpaint_mask=mask_path,
                width=width,
                height=height,
            )
            request_body = self._request_bytes(final_payload)
            if len(request_body) <= safe_request_bytes:
                break

            ratio = math.sqrt(safe_request_bytes / float(len(request_body))) * 0.88
            scale *= min(0.88, max(0.20, ratio))
            if min(target_size) <= 64:
                raise AIEngineError(
                    "Unable to fit generation references into the OpenRouter request limit",
                    details={"safe_request_bytes": safe_request_bytes, "request_body_bytes": len(request_body)},
                )
        else:
            raise AIEngineError(
                "Unable to prepare OpenRouter transport images after 18 attempts",
                details={"safe_request_bytes": safe_request_bytes, "request_body_bytes": len(request_body)},
            )

        assert final_payload is not None and geometry_path is not None and mask_path is not None
        if len(request_body) > safe_request_bytes:
            raise AIEngineError(
                "Transport preflight rejected an oversized request before network transmission",
                details={"safe_request_bytes": safe_request_bytes, "request_body_bytes": len(request_body)},
            )

        with Image.open(geometry_path) as transport_image:
            transport_size = transport_image.size

        metadata = {
            "provider": "openrouter",
            "model": self.model,
            "transport_engine_version": self.transport_engine_version,
            "master_geometry_path": str(geometry_image),
            "master_mask_path": str(outpaint_mask),
            "master_width": original_size[0],
            "master_height": original_size[1],
            "transport_geometry_path": str(geometry_path),
            "transport_mask_path": str(mask_path),
            "transport_width": transport_size[0],
            "transport_height": transport_size[1],
            "geometry_bytes": geometry_path.stat().st_size,
            "mask_bytes": mask_path.stat().st_size,
            "request_body_bytes": len(request_body),
            "max_request_bytes": capabilities["max_request_bytes"],
            "safe_request_bytes": safe_request_bytes,
            "gateway_hard_max_request_bytes": self.gateway_hard_max_request_bytes,
            "request_limit_source": capabilities["request_limit_source"],
            "resized_for_provider": transport_size != original_size,
            "scale": round(transport_size[0] / float(original_size[0]), 6),
            "geometry_encoding": encoding,
            "geometry_sha256": self._sha256(geometry_path),
            "mask_sha256": self._sha256(mask_path),
            "attempts": attempt,
            "capabilities": capabilities,
        }
        (output_dir / "transport.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), "utf-8")
        return metadata

    def _prepared_payload(self, *, prompt: str, prepared_input: dict, width: int, height: int) -> tuple[dict, bytes]:
        payload = self._build_payload(
            prompt=prompt,
            geometry_image=Path(prepared_input["transport_geometry_path"]),
            outpaint_mask=Path(prepared_input["transport_mask_path"]),
            width=width,
            height=height,
        )
        return payload, self._request_bytes(payload)

    def _hard_preflight(
        self,
        *,
        prompt: str,
        geometry_image: Path,
        outpaint_mask: Path,
        transport_dir: Path,
        width: int,
        height: int,
        prepared: dict,
    ) -> tuple[dict, dict, bytes]:
        payload, request_body = self._prepared_payload(
            prompt=prompt,
            prepared_input=prepared,
            width=width,
            height=height,
        )
        hard_safe = int(self.gateway_hard_max_request_bytes * self.safety_margin)
        if len(request_body) > hard_safe:
            prepared = self.prepare_environment_inputs(
                prompt=prompt,
                geometry_image=geometry_image,
                outpaint_mask=outpaint_mask,
                output_dir=transport_dir,
                width=width,
                height=height,
                forced_max_request_bytes=self.gateway_hard_max_request_bytes,
            )
            payload, request_body = self._prepared_payload(
                prompt=prompt,
                prepared_input=prepared,
                width=width,
                height=height,
            )
        if len(request_body) > hard_safe:
            raise AIEngineError(
                "Hard preflight blocked an oversized OpenRouter request",
                details={
                    "transport": prepared,
                    "request_body_bytes": len(request_body),
                    "hard_safe_request_bytes": hard_safe,
                },
            )
        return prepared, payload, request_body

    def generate_environment(
        self,
        *,
        prompt: str,
        geometry_image: Path,
        outpaint_mask: Path,
        output_dir: Path,
        width: int,
        height: int,
        prepared_input: dict | None = None,
    ) -> dict:
        if not self.api_key:
            raise AIEngineError("OPENROUTER_API_KEY is not configured")

        output_dir.mkdir(parents=True, exist_ok=True)
        transport_dir = output_dir / "transport"
        prepared = prepared_input or self.prepare_environment_inputs(
            prompt=prompt,
            geometry_image=geometry_image,
            outpaint_mask=outpaint_mask,
            output_dir=transport_dir,
            width=width,
            height=height,
        )
        prepared, payload, request_body = self._hard_preflight(
            prompt=prompt,
            geometry_image=geometry_image,
            outpaint_mask=outpaint_mask,
            transport_dir=transport_dir,
            width=width,
            height=height,
            prepared=prepared,
        )

        started = time.time()
        response = requests.post(self.endpoint, headers=self.headers, data=request_body, timeout=self.timeout)
        retry_count = 0

        if response.status_code == 413:
            retry_count = 1
            observed_limit = self._extract_request_limit(response.text) or self.gateway_hard_max_request_bytes
            self._learned_max_request_bytes = self._effective_limit(observed_limit)
            prepared = self.prepare_environment_inputs(
                prompt=prompt,
                geometry_image=geometry_image,
                outpaint_mask=outpaint_mask,
                output_dir=transport_dir,
                width=width,
                height=height,
                forced_max_request_bytes=self._learned_max_request_bytes,
            )
            prepared, payload, request_body = self._hard_preflight(
                prompt=prompt,
                geometry_image=geometry_image,
                outpaint_mask=outpaint_mask,
                transport_dir=transport_dir,
                width=width,
                height=height,
                prepared=prepared,
            )
            response = requests.post(self.endpoint, headers=self.headers, data=request_body, timeout=self.timeout)

        elapsed = round(time.time() - started, 3)
        if response.status_code >= 400:
            raise AIEngineError(
                f"OpenRouter {response.status_code}: {response.text[:2000]}",
                details={
                    "transport": prepared,
                    "request_body_bytes": len(request_body),
                    "retry_count": retry_count,
                    "transport_engine_version": self.transport_engine_version,
                },
            )

        data = response.json()
        items = data.get("data") or []
        if not items or not items[0].get("b64_json"):
            raise AIEngineError("OpenRouter returned no image data", details={"transport": prepared})

        raw = base64.b64decode(items[0]["b64_json"])
        raw_path = output_dir / "provider-output.png"
        raw_path.write_bytes(raw)
        with Image.open(raw_path) as image:
            oriented = ImageOps.exif_transpose(image)
            output_size = oriented.size
            if output_size != (width, height):
                raise AIEngineError(
                    f"Provider returned {output_size[0]}x{output_size[1]}, expected exact master canvas {width}x{height}. The result was retained for diagnostics but not promoted.",
                    details={"transport": prepared, "provider_output": str(raw_path)},
                )
            candidate = output_dir / "candidate.png"
            oriented.convert("RGB").save(candidate, format="PNG", optimize=False)

        metadata = {
            "provider": "openrouter",
            "model": self.model,
            "endpoint": self.endpoint,
            "transport_engine_version": self.transport_engine_version,
            "duration_seconds": elapsed,
            "width": width,
            "height": height,
            "candidate": str(candidate),
            "provider_output": str(raw_path),
            "usage": data.get("usage") or {},
            "request": {key: value for key, value in payload.items() if key != "input_references"},
            "request_body_bytes": len(request_body),
            "retry_count": retry_count,
            "transport": prepared,
        }
        (output_dir / "generation.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), "utf-8")
        return metadata
