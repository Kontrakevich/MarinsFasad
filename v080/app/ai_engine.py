from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import re
import time
from pathlib import Path
from typing import Any, Iterable

import requests
from PIL import Image, ImageChops, ImageOps


class AIEngineError(RuntimeError):
    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


class OpenRouterImageEngine:
    endpoint = "https://openrouter.ai/api/v1/images"
    image_models_endpoint = "https://openrouter.ai/api/v1/images/models"
    transport_engine_version = "2.3.0"

    gateway_hard_max_request_bytes = 50 * 1024 * 1024
    default_transmit_max_request_bytes = 32 * 1024 * 1024
    emergency_retry_max_request_bytes = 20 * 1024 * 1024

    default_supported_output_sizes = (
        (1024, 1024),
        (1024, 1536),
        (1536, 1024),
    )

    def __init__(self) -> None:
        self.api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        self.model = os.getenv("OPENROUTER_IMAGE_MODEL", "openai/gpt-image-1").strip()
        self.timeout = int(os.getenv("OPENROUTER_IMAGE_TIMEOUT", "240"))
        self.capability_timeout = int(os.getenv("OPENROUTER_CAPABILITY_TIMEOUT", "15"))

        configured_transmit = int(os.getenv("OPENROUTER_TRANSMIT_MAX_BYTES", "0") or 0)
        self.transmit_max_request_bytes = min(
            self.default_transmit_max_request_bytes,
            configured_transmit if configured_transmit > 0 else self.default_transmit_max_request_bytes,
        )

        self.max_input_side = max(0, int(os.getenv("OPENROUTER_MAX_INPUT_SIDE", "0")))
        self.max_input_pixels = max(0, int(os.getenv("OPENROUTER_MAX_INPUT_PIXELS", "0")))
        self.transport_quality = min(
            98,
            max(70, int(os.getenv("OPENROUTER_TRANSPORT_QUALITY", "92"))),
        )
        self._learned_max_request_bytes: int | None = None

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/Kontrakevich/MarinsFasad",
            "X-Title": "Marins Facade Control Center",
            "X-Marins-Transport-Engine": self.transport_engine_version,
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
    def _extract_supported_sizes(text: str) -> list[tuple[int, int]]:
        output: list[tuple[int, int]] = []
        for width, height in re.findall(r"\b(\d{3,5})x(\d{3,5})\b", text or ""):
            size = (int(width), int(height))
            if size not in output:
                output.append(size)
        return output

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

    @staticmethod
    def _sizes_from_value(value: Any) -> list[tuple[int, int]]:
        found: list[tuple[int, int]] = []

        def visit(item: Any) -> None:
            if isinstance(item, dict):
                for nested in item.values():
                    visit(nested)
            elif isinstance(item, (list, tuple, set)):
                for nested in item:
                    visit(nested)
            elif isinstance(item, str):
                for size in OpenRouterImageEngine._extract_supported_sizes(item):
                    if size not in found:
                        found.append(size)

        visit(value)
        return found

    @classmethod
    def _select_provider_size(
        cls,
        width: int,
        height: int,
        supported_sizes: Iterable[tuple[int, int]] | None = None,
    ) -> tuple[int, int]:
        candidates = [
            (int(candidate_width), int(candidate_height))
            for candidate_width, candidate_height in (
                supported_sizes or cls.default_supported_output_sizes
            )
            if int(candidate_width) > 0 and int(candidate_height) > 0
        ]
        if not candidates:
            candidates = list(cls.default_supported_output_sizes)

        override = os.getenv("OPENROUTER_IMAGE_SIZE", "").strip().lower()
        if override and override != "auto":
            parsed = cls._extract_supported_sizes(override)
            if parsed and parsed[0] in candidates:
                return parsed[0]

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

        return min(candidates, key=score)

    @staticmethod
    def _fit_content_box(
        source_size: tuple[int, int],
        canvas_size: tuple[int, int],
    ) -> tuple[int, int, int, int]:
        source_width, source_height = source_size
        canvas_width, canvas_height = canvas_size
        scale = min(
            canvas_width / float(max(1, source_width)),
            canvas_height / float(max(1, source_height)),
        )
        fitted_width = max(1, min(canvas_width, int(round(source_width * scale))))
        fitted_height = max(1, min(canvas_height, int(round(source_height * scale))))
        left = (canvas_width - fitted_width) // 2
        top = (canvas_height - fitted_height) // 2
        return left, top, fitted_width, fitted_height

    def _effective_gateway_limit(self, candidate: int | None = None) -> int:
        values = [self.gateway_hard_max_request_bytes]
        configured = int(os.getenv("OPENROUTER_MAX_REQUEST_BYTES", "0") or 0)
        if configured > 0:
            values.append(configured)
        if self._learned_max_request_bytes:
            values.append(self._learned_max_request_bytes)
        if candidate:
            values.append(candidate)
        return max(1024 * 1024, min(values))

    def _target_request_bytes(self, candidate: int | None = None) -> int:
        gateway_limit = self._effective_gateway_limit(candidate)
        return max(
            1024 * 1024,
            min(self.transmit_max_request_bytes, int(gateway_limit * 0.64)),
        )

    def discover_capabilities(self) -> dict:
        max_request_bytes = self._effective_gateway_limit()
        limit_source = "gateway_hard_cap"
        supported_parameters: dict[str, Any] = {}
        providers: list[str] = []
        discovery_errors: list[str] = []

        if self.api_key and "/" in self.model:
            author, slug = self.model.split("/", 1)
            url = f"{self.image_models_endpoint}/{author}/{slug}/endpoints"
            try:
                response = requests.get(
                    url,
                    headers=self.headers,
                    timeout=self.capability_timeout,
                )
                if response.ok:
                    data = response.json()
                    for endpoint in data.get("endpoints") or []:
                        provider = (
                            endpoint.get("provider_name")
                            or endpoint.get("provider_slug")
                        )
                        if provider and provider not in providers:
                            providers.append(str(provider))
                        for key, descriptor in (
                            endpoint.get("supported_parameters") or {}
                        ).items():
                            supported_parameters.setdefault(key, descriptor)
                else:
                    discovery_errors.append(
                        f"model_endpoints_http_{response.status_code}"
                    )
            except Exception as exc:
                discovery_errors.append(
                    f"model_endpoints:{type(exc).__name__}"
                )

        if self.api_key:
            try:
                response = requests.options(
                    self.endpoint,
                    headers=self.headers,
                    timeout=self.capability_timeout,
                )
                header_limit = self._header_limit(response.headers)
                if header_limit:
                    max_request_bytes = self._effective_gateway_limit(header_limit)
                    limit_source = "response_header_capped"
            except Exception as exc:
                discovery_errors.append(f"options:{type(exc).__name__}")

        if self._learned_max_request_bytes:
            max_request_bytes = self._effective_gateway_limit(
                self._learned_max_request_bytes
            )
            limit_source = "observed_413_capped"

        discovered_sizes = self._sizes_from_value(supported_parameters)
        supported_output_sizes = (
            discovered_sizes
            if discovered_sizes
            else list(self.default_supported_output_sizes)
        )

        return {
            "provider": "openrouter",
            "model": self.model,
            "transport_engine_version": self.transport_engine_version,
            "gateway_hard_max_request_bytes": self.gateway_hard_max_request_bytes,
            "max_request_bytes": int(max_request_bytes),
            "transmit_max_request_bytes": self.transmit_max_request_bytes,
            "target_request_bytes": self._target_request_bytes(max_request_bytes),
            "request_limit_source": limit_source,
            "supported_parameters": supported_parameters,
            "supported_output_sizes": [
                f"{width}x{height}" for width, height in supported_output_sizes
            ],
            "providers": providers,
            "discovery_errors": discovery_errors,
        }

    def _build_payload(
        self,
        *,
        prompt: str,
        geometry_image: Path,
        outpaint_mask: Path,
        provider_size: tuple[int, int],
    ) -> dict:
        return {
            "model": self.model,
            "prompt": prompt,
            "n": 1,
            "size": f"{provider_size[0]}x{provider_size[1]}",
            "quality": "high",
            "output_format": "png",
            "background": "opaque",
            "input_references": [
                {
                    "type": "image_url",
                    "image_url": {"url": self._data_url(geometry_image)},
                },
                {
                    "type": "image_url",
                    "image_url": {"url": self._data_url(outpaint_mask)},
                },
            ],
        }

    def _save_transport_geometry(
        self,
        image: Image.Image,
        directory: Path,
        quality: int,
    ) -> tuple[Path, str]:
        path = directory / "geometry-input.webp"
        image.save(
            path,
            format="WEBP",
            lossless=False,
            quality=quality,
            method=6,
            exact=True,
        )
        return path, f"webp-q{quality}"

    @staticmethod
    def _save_transport_mask(mask: Image.Image, directory: Path) -> Path:
        path = directory / "outpaint-mask.png"
        mask.save(path, format="PNG", optimize=True, compress_level=9)
        return path

    @staticmethod
    def _reference_canvases(
        geometry_master: Image.Image,
        mask_master: Image.Image,
        reference_size: tuple[int, int],
    ) -> tuple[Image.Image, Image.Image, tuple[int, int, int, int]]:
        left, top, content_width, content_height = (
            OpenRouterImageEngine._fit_content_box(
                geometry_master.size,
                reference_size,
            )
        )

        geometry_resized = geometry_master.resize(
            (content_width, content_height),
            Image.Resampling.LANCZOS,
        )
        mask_resized = mask_master.resize(
            (content_width, content_height),
            Image.Resampling.NEAREST,
        ).point(lambda value: 255 if value >= 128 else 0, mode="L")

        geometry_canvas = Image.new("RGBA", reference_size, (0, 0, 0, 0))
        geometry_canvas.paste(geometry_resized, (left, top), geometry_resized)

        mask_canvas = Image.new("L", reference_size, 255)
        mask_canvas.paste(mask_resized, (left, top))

        return (
            geometry_canvas,
            mask_canvas,
            (left, top, content_width, content_height),
        )

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
        forced_target_request_bytes: int | None = None,
        supported_sizes: Iterable[tuple[int, int]] | None = None,
    ) -> dict:
        output_dir.mkdir(parents=True, exist_ok=True)
        capabilities = self.discover_capabilities()
        gateway_limit = self._effective_gateway_limit(forced_max_request_bytes)
        target_request_bytes = self._target_request_bytes(gateway_limit)
        if forced_target_request_bytes:
            target_request_bytes = min(
                target_request_bytes,
                int(forced_target_request_bytes),
            )
        target_request_bytes = min(
            target_request_bytes,
            self.transmit_max_request_bytes,
        )

        capability_sizes = self._sizes_from_value(
            capabilities.get("supported_output_sizes")
        )
        provider_size = self._select_provider_size(
            width,
            height,
            supported_sizes or capability_sizes or self.default_supported_output_sizes,
        )

        with Image.open(geometry_image) as source:
            geometry_master = ImageOps.exif_transpose(source).convert("RGBA")
        with Image.open(outpaint_mask) as source_mask:
            mask_master = ImageOps.exif_transpose(source_mask).convert("L")

        if geometry_master.size != (width, height):
            raise AIEngineError(
                f"Geometry master {geometry_master.size[0]}x{geometry_master.size[1]} "
                f"does not match declared master canvas {width}x{height}"
            )
        if mask_master.size != geometry_master.size:
            raise AIEngineError(
                f"Outpaint mask {mask_master.size[0]}x{mask_master.size[1]} "
                f"does not match geometry {geometry_master.size[0]}x{geometry_master.size[1]}"
            )

        reference_scale = 1.0
        if self.max_input_side and max(provider_size) > self.max_input_side:
            reference_scale = min(
                reference_scale,
                self.max_input_side / float(max(provider_size)),
            )
        if self.max_input_pixels and provider_size[0] * provider_size[1] > self.max_input_pixels:
            reference_scale = min(
                reference_scale,
                math.sqrt(
                    self.max_input_pixels
                    / float(provider_size[0] * provider_size[1])
                ),
            )

        request_body = b""
        geometry_path: Path | None = None
        mask_path: Path | None = None
        encoding = ""
        content_box = (0, 0, provider_size[0], provider_size[1])
        reference_size = provider_size
        attempt = 0

        while attempt < 20:
            attempt += 1
            reference_size = (
                max(256, int(round(provider_size[0] * reference_scale))),
                max(256, int(round(provider_size[1] * reference_scale))),
            )
            geometry_canvas, mask_canvas, content_box = self._reference_canvases(
                geometry_master,
                mask_master,
                reference_size,
            )

            quality = max(70, self.transport_quality - (attempt - 1) * 3)
            geometry_path, encoding = self._save_transport_geometry(
                geometry_canvas,
                output_dir,
                quality,
            )
            mask_path = self._save_transport_mask(mask_canvas, output_dir)

            payload = self._build_payload(
                prompt=prompt,
                geometry_image=geometry_path,
                outpaint_mask=mask_path,
                provider_size=provider_size,
            )
            request_body = self._request_bytes(payload)
            if len(request_body) <= target_request_bytes:
                break

            ratio = math.sqrt(
                target_request_bytes / float(len(request_body))
            ) * 0.82
            reference_scale *= min(0.82, max(0.20, ratio))
            if min(reference_size) <= 256 and quality <= 70:
                raise AIEngineError(
                    "Unable to fit generation references into the OpenRouter transport limit",
                    details={
                        "target_request_bytes": target_request_bytes,
                        "request_body_bytes": len(request_body),
                        "provider_output_size": f"{provider_size[0]}x{provider_size[1]}",
                    },
                )
        else:
            raise AIEngineError(
                "Unable to prepare OpenRouter transport images after 20 attempts",
                details={
                    "target_request_bytes": target_request_bytes,
                    "request_body_bytes": len(request_body),
                },
            )

        assert geometry_path is not None and mask_path is not None
        if len(request_body) > target_request_bytes:
            raise AIEngineError(
                "Transport preflight rejected an oversized request before network transmission",
                details={
                    "target_request_bytes": target_request_bytes,
                    "request_body_bytes": len(request_body),
                },
            )

        left, top, content_width, content_height = content_box
        normalized_box = {
            "x": left / float(reference_size[0]),
            "y": top / float(reference_size[1]),
            "width": content_width / float(reference_size[0]),
            "height": content_height / float(reference_size[1]),
        }

        metadata = {
            "provider": "openrouter",
            "model": self.model,
            "transport_engine_version": self.transport_engine_version,
            "master_geometry_path": str(geometry_image),
            "master_mask_path": str(outpaint_mask),
            "master_width": width,
            "master_height": height,
            "provider_output_width": provider_size[0],
            "provider_output_height": provider_size[1],
            "provider_output_size": f"{provider_size[0]}x{provider_size[1]}",
            "transport_geometry_path": str(geometry_path),
            "transport_mask_path": str(mask_path),
            "transport_width": reference_size[0],
            "transport_height": reference_size[1],
            "transport_content_box": {
                "x": left,
                "y": top,
                "width": content_width,
                "height": content_height,
            },
            "content_box_normalized": normalized_box,
            "geometry_bytes": geometry_path.stat().st_size,
            "mask_bytes": mask_path.stat().st_size,
            "request_body_bytes": len(request_body),
            "max_request_bytes": gateway_limit,
            "transmit_max_request_bytes": self.transmit_max_request_bytes,
            "target_request_bytes": target_request_bytes,
            "request_limit_source": capabilities["request_limit_source"],
            "resized_for_provider": reference_size != (width, height),
            "reference_scale": round(reference_scale, 6),
            "geometry_encoding": encoding,
            "geometry_sha256": self._sha256(geometry_path),
            "mask_sha256": self._sha256(mask_path),
            "attempts": attempt,
            "capabilities": capabilities,
        }
        (output_dir / "transport.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            "utf-8",
        )
        return metadata

    def _prepared_payload(
        self,
        *,
        prompt: str,
        prepared_input: dict,
    ) -> tuple[dict, bytes]:
        provider_size = (
            int(prepared_input["provider_output_width"]),
            int(prepared_input["provider_output_height"]),
        )
        payload = self._build_payload(
            prompt=prompt,
            geometry_image=Path(prepared_input["transport_geometry_path"]),
            outpaint_mask=Path(prepared_input["transport_mask_path"]),
            provider_size=provider_size,
        )
        return payload, self._request_bytes(payload)

    def _prepare_http_request(
        self,
        request_body: bytes,
    ) -> requests.PreparedRequest:
        headers = dict(self.headers)
        headers["X-Marins-Request-Bytes"] = str(len(request_body))
        request = requests.Request(
            "POST",
            self.endpoint,
            headers=headers,
            data=request_body,
        )
        prepared_request = request.prepare()
        body = prepared_request.body
        if isinstance(body, str):
            body_bytes = body.encode("utf-8")
        elif isinstance(body, bytes):
            body_bytes = body
        else:
            raise AIEngineError(
                "Prepared OpenRouter request body is not deterministic"
            )

        content_length = int(
            prepared_request.headers.get("Content-Length", "0") or 0
        )
        if (
            content_length != len(body_bytes)
            or len(body_bytes) != len(request_body)
        ):
            raise AIEngineError(
                "Prepared HTTP request size does not match transport preflight",
                details={
                    "preflight_bytes": len(request_body),
                    "prepared_body_bytes": len(body_bytes),
                    "content_length": content_length,
                },
            )
        if content_length > self.transmit_max_request_bytes:
            raise AIEngineError(
                "Prepared HTTP request exceeds the Marins transmit ceiling",
                details={
                    "content_length": content_length,
                    "transmit_max_request_bytes": self.transmit_max_request_bytes,
                },
            )
        return prepared_request

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
        target_request_bytes: int | None = None,
        supported_sizes: Iterable[tuple[int, int]] | None = None,
    ) -> tuple[dict, dict, bytes, requests.PreparedRequest]:
        payload, request_body = self._prepared_payload(
            prompt=prompt,
            prepared_input=prepared,
        )
        target = min(
            int(target_request_bytes or self.transmit_max_request_bytes),
            self.transmit_max_request_bytes,
        )
        if len(request_body) > target:
            prepared = self.prepare_environment_inputs(
                prompt=prompt,
                geometry_image=geometry_image,
                outpaint_mask=outpaint_mask,
                output_dir=transport_dir,
                width=width,
                height=height,
                forced_target_request_bytes=target,
                supported_sizes=supported_sizes,
            )
            payload, request_body = self._prepared_payload(
                prompt=prompt,
                prepared_input=prepared,
            )
        if len(request_body) > target:
            raise AIEngineError(
                "Hard preflight blocked an oversized OpenRouter request",
                details={
                    "transport": prepared,
                    "request_body_bytes": len(request_body),
                    "target_request_bytes": target,
                },
            )

        prepared_request = self._prepare_http_request(request_body)
        prepared["prepared_content_length"] = int(
            prepared_request.headers["Content-Length"]
        )
        return prepared, payload, request_body, prepared_request

    def _send_prepared(
        self,
        prepared_request: requests.PreparedRequest,
    ) -> requests.Response:
        session = requests.Session()
        try:
            return session.send(
                prepared_request,
                timeout=self.timeout,
                allow_redirects=False,
            )
        finally:
            session.close()

    @staticmethod
    def _provider_crop_box(
        provider_size: tuple[int, int],
        normalized_box: dict,
    ) -> tuple[int, int, int, int]:
        provider_width, provider_height = provider_size
        left = int(round(float(normalized_box["x"]) * provider_width))
        top = int(round(float(normalized_box["y"]) * provider_height))
        width = int(round(float(normalized_box["width"]) * provider_width))
        height = int(round(float(normalized_box["height"]) * provider_height))

        left = max(0, min(provider_width - 1, left))
        top = max(0, min(provider_height - 1, top))
        right = max(left + 1, min(provider_width, left + max(1, width)))
        bottom = max(top + 1, min(provider_height, top + max(1, height)))
        return left, top, right, bottom

    def _promote_provider_output(
        self,
        *,
        provider_output: Path,
        geometry_image: Path,
        outpaint_mask: Path,
        prepared: dict,
        output_dir: Path,
        width: int,
        height: int,
    ) -> dict:
        with Image.open(provider_output) as generated_source:
            generated = ImageOps.exif_transpose(generated_source).convert("RGB")
            provider_actual_size = generated.size

        crop_box = self._provider_crop_box(
            provider_actual_size,
            prepared["content_box_normalized"],
        )
        cropped = generated.crop(crop_box)
        environment_master = cropped.resize(
            (width, height),
            Image.Resampling.LANCZOS,
        )
        environment_master_path = output_dir / "environment-remapped.png"
        environment_master.save(
            environment_master_path,
            format="PNG",
            optimize=False,
        )

        with Image.open(geometry_image) as geometry_source:
            geometry_master = ImageOps.exif_transpose(
                geometry_source
            ).convert("RGBA")
        with Image.open(outpaint_mask) as mask_source:
            outpaint_master = ImageOps.exif_transpose(mask_source).convert("L")

        if geometry_master.size != (width, height):
            raise AIEngineError(
                "Approved geometry no longer matches the master canvas",
                details={
                    "geometry_size": geometry_master.size,
                    "master_size": (width, height),
                },
            )
        if outpaint_master.size != (width, height):
            raise AIEngineError(
                "Approved outpaint mask no longer matches the master canvas",
                details={
                    "mask_size": outpaint_master.size,
                    "master_size": (width, height),
                },
            )

        binary_outpaint = outpaint_master.point(
            lambda value: 255 if value >= 128 else 0,
            mode="L",
        )
        preserve_mask = ImageOps.invert(binary_outpaint)
        preserve_mask = ImageChops.multiply(
            preserve_mask,
            geometry_master.getchannel("A"),
        )

        candidate = Image.composite(
            geometry_master.convert("RGB"),
            environment_master,
            preserve_mask,
        )
        candidate_path = output_dir / "candidate.png"
        candidate.save(candidate_path, format="PNG", optimize=False)

        return {
            "candidate": str(candidate_path),
            "environment_master": str(environment_master_path),
            "provider_actual_width": provider_actual_size[0],
            "provider_actual_height": provider_actual_size[1],
            "provider_crop_box": {
                "left": crop_box[0],
                "top": crop_box[1],
                "right": crop_box[2],
                "bottom": crop_box[3],
            },
            "master_width": width,
            "master_height": height,
            "remapped_to_master": True,
            "approved_geometry_preserved": True,
        }

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
        prepared, payload, request_body, prepared_request = (
            self._hard_preflight(
                prompt=prompt,
                geometry_image=geometry_image,
                outpaint_mask=outpaint_mask,
                transport_dir=transport_dir,
                width=width,
                height=height,
                prepared=prepared,
                target_request_bytes=self.transmit_max_request_bytes,
            )
        )

        started = time.time()
        response = self._send_prepared(prepared_request)
        retry_reasons: list[str] = []

        if response.status_code == 400:
            supported_sizes = self._extract_supported_sizes(response.text)
            if supported_sizes:
                retry_reasons.append("provider_size_400")
                prepared = self.prepare_environment_inputs(
                    prompt=prompt,
                    geometry_image=geometry_image,
                    outpaint_mask=outpaint_mask,
                    output_dir=transport_dir,
                    width=width,
                    height=height,
                    supported_sizes=supported_sizes,
                )
                prepared, payload, request_body, prepared_request = (
                    self._hard_preflight(
                        prompt=prompt,
                        geometry_image=geometry_image,
                        outpaint_mask=outpaint_mask,
                        transport_dir=transport_dir,
                        width=width,
                        height=height,
                        prepared=prepared,
                        target_request_bytes=self.transmit_max_request_bytes,
                        supported_sizes=supported_sizes,
                    )
                )
                response = self._send_prepared(prepared_request)

        if response.status_code == 413:
            retry_reasons.append("request_size_413")
            observed_limit = (
                self._extract_request_limit(response.text)
                or self.gateway_hard_max_request_bytes
            )
            self._learned_max_request_bytes = self._effective_gateway_limit(
                observed_limit
            )
            emergency_target = min(
                self.emergency_retry_max_request_bytes,
                int(self._learned_max_request_bytes * 0.40),
            )
            prepared = self.prepare_environment_inputs(
                prompt=prompt,
                geometry_image=geometry_image,
                outpaint_mask=outpaint_mask,
                output_dir=transport_dir,
                width=width,
                height=height,
                forced_max_request_bytes=self._learned_max_request_bytes,
                forced_target_request_bytes=emergency_target,
            )
            prepared, payload, request_body, prepared_request = (
                self._hard_preflight(
                    prompt=prompt,
                    geometry_image=geometry_image,
                    outpaint_mask=outpaint_mask,
                    transport_dir=transport_dir,
                    width=width,
                    height=height,
                    prepared=prepared,
                    target_request_bytes=emergency_target,
                )
            )
            response = self._send_prepared(prepared_request)

        elapsed = round(time.time() - started, 3)

        if 300 <= response.status_code < 400:
            raise AIEngineError(
                f"OpenRouter returned unexpected redirect {response.status_code}",
                details={
                    "location": response.headers.get("Location"),
                    "transport": prepared,
                    "request_body_bytes": len(request_body),
                },
            )
        if response.status_code >= 400:
            raise AIEngineError(
                f"OpenRouter {response.status_code}: {response.text[:2000]}",
                details={
                    "transport": prepared,
                    "request_body_bytes": len(request_body),
                    "prepared_content_length": prepared.get(
                        "prepared_content_length"
                    ),
                    "retry_reasons": retry_reasons,
                    "transport_engine_version": self.transport_engine_version,
                },
            )

        data = response.json()
        items = data.get("data") or []
        if not items or not items[0].get("b64_json"):
            raise AIEngineError(
                "OpenRouter returned no image data",
                details={"transport": prepared},
            )

        raw = base64.b64decode(items[0]["b64_json"])
        raw_path = output_dir / "provider-output.png"
        raw_path.write_bytes(raw)

        promotion = self._promote_provider_output(
            provider_output=raw_path,
            geometry_image=geometry_image,
            outpaint_mask=outpaint_mask,
            prepared=prepared,
            output_dir=output_dir,
            width=width,
            height=height,
        )

        metadata = {
            "provider": "openrouter",
            "model": self.model,
            "endpoint": self.endpoint,
            "transport_engine_version": self.transport_engine_version,
            "duration_seconds": elapsed,
            "width": width,
            "height": height,
            "provider_requested_size": prepared["provider_output_size"],
            "provider_output": str(raw_path),
            "candidate": promotion["candidate"],
            "environment_master": promotion["environment_master"],
            "provider_actual_width": promotion["provider_actual_width"],
            "provider_actual_height": promotion["provider_actual_height"],
            "provider_crop_box": promotion["provider_crop_box"],
            "remapped_to_master": promotion["remapped_to_master"],
            "approved_geometry_preserved": promotion[
                "approved_geometry_preserved"
            ],
            "usage": data.get("usage") or {},
            "request": {
                key: value
                for key, value in payload.items()
                if key != "input_references"
            },
            "request_body_bytes": len(request_body),
            "prepared_content_length": prepared.get(
                "prepared_content_length"
            ),
            "retry_reasons": retry_reasons,
            "transport": prepared,
        }
        (output_dir / "generation.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            "utf-8",
        )
        return metadata
