from __future__ import annotations

import re
import sys
from pathlib import Path

runtime = Path(sys.argv[1])
main_path = runtime / "app/main.py"
index_path = runtime / "app/web/index.html"
test_path = runtime / "tests/test_openrouter_stream_transport.py"

main = main_path.read_text("utf-8")
main = re.sub(
    r'^APP_VERSION = "[^"]+"$',
    'APP_VERSION = "0.6.7"',
    main,
    count=1,
    flags=re.MULTILINE,
)

marker = "# v0.6.7 streaming OpenRouter transport with resized alpha reference"
if marker not in main:
    main += r'''

# v0.6.7 streaming OpenRouter transport with resized alpha reference
import io as _mf067_io
import json as _mf067_json
import os as _mf067_os
import urllib.error as _mf067_urlerror
import urllib.request as _mf067_urlrequest
from PIL import Image as _mf067_Image


def _mf067_reference_data_url(source: _mf_Path) -> tuple[str, dict]:
    """Prepare a bounded PNG reference while preserving alpha for outpaint."""
    max_edge = max(512, int(_mf067_os.getenv("OPENROUTER_REFERENCE_MAX_EDGE", "2048")))
    with _mf067_Image.open(source) as opened:
        image = opened.convert("RGBA")
        original_size = image.size
        if max(image.size) > max_edge:
            image.thumbnail((max_edge, max_edge), _mf067_Image.Resampling.LANCZOS)
        prepared_size = image.size
        buffer = _mf067_io.BytesIO()
        image.save(buffer, format="PNG", optimize=True)
    raw = buffer.getvalue()
    encoded = _mf_base64.b64encode(raw).decode("ascii")
    return "data:image/png;base64," + encoded, {
        "original_size": {"width": original_size[0], "height": original_size[1]},
        "prepared_size": {"width": prepared_size[0], "height": prepared_size[1]},
        "prepared_bytes": len(raw),
        "alpha_preserved": True,
        "max_edge": max_edge,
    }


def _mf067_decode_data_url(value: str) -> tuple[bytes, str] | None:
    if not value.startswith("data:") or "," not in value:
        return None
    header, encoded = value.split(",", 1)
    media_type = header.split(";", 1)[0].split(":", 1)[1]
    try:
        return _mf_base64.b64decode(encoded), media_type
    except Exception:
        return None


def _mf067_is_image_bytes(value: bytes) -> bool:
    return (
        value.startswith(b"\x89PNG\r\n\x1a\n")
        or value.startswith(b"\xff\xd8\xff")
        or (len(value) > 12 and value[:4] == b"RIFF" and value[8:12] == b"WEBP")
        or value.lstrip().startswith(b"<svg")
    )


def _mf067_extract_image(payload: object) -> tuple[bytes, str] | None:
    """Accept buffered image API payloads and streaming event variants."""
    if isinstance(payload, dict):
        for key in ("b64_json", "base64", "image_base64"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                decoded_url = _mf067_decode_data_url(value)
                if decoded_url:
                    return decoded_url
                try:
                    raw = _mf_base64.b64decode(value)
                    if _mf067_is_image_bytes(raw):
                        return raw, str(payload.get("media_type") or "image/png")
                except Exception:
                    pass

        for key in ("url", "image_url"):
            value = payload.get(key)
            if isinstance(value, dict):
                value = value.get("url")
            if isinstance(value, str):
                decoded_url = _mf067_decode_data_url(value)
                if decoded_url:
                    return decoded_url
                if value.startswith(("https://", "http://")):
                    with _mf067_urlrequest.urlopen(value, timeout=120) as response:
                        return response.read(), response.headers.get_content_type()

        for key in ("data", "image", "images", "output", "result", "partial", "choices", "message"):
            if key in payload:
                found = _mf067_extract_image(payload[key])
                if found:
                    return found

    elif isinstance(payload, list):
        for item in payload:
            found = _mf067_extract_image(item)
            if found:
                return found

    elif isinstance(payload, str):
        return _mf067_decode_data_url(payload)

    return None


def _mf067_error_message(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or error.get("detail") or error)
    if error:
        return str(error)
    if payload.get("type") == "error":
        return str(payload.get("message") or payload)
    return None


def _mf_openrouter_generate(source: _mf_Path, prompt: str) -> tuple[bytes, str, dict]:
    """Generate through the official streaming Image API with a bounded reference."""
    api_key = _mf_os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY не задан в Codespaces secrets")

    model = _mf_os.getenv(
        "OPENROUTER_IMAGE_MODEL",
        "google/gemini-2.5-flash-image",
    ).strip()
    timeout_seconds = max(300, int(_mf067_os.getenv("OPENROUTER_IMAGE_TIMEOUT", "900")))
    reference_url, reference_meta = _mf067_reference_data_url(source)

    payload = {
        "model": model,
        "prompt": prompt,
        "n": 1,
        "output_format": "png",
        "stream": True,
        "input_references": [
            {
                "type": "image_url",
                "image_url": {"url": reference_url},
            }
        ],
    }
    resolution = _mf067_os.getenv("OPENROUTER_IMAGE_RESOLUTION", "").strip()
    if resolution:
        payload["resolution"] = resolution

    request = _mf067_urlrequest.Request(
        "https://openrouter.ai/api/v1/images",
        data=_mf067_json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream, application/json",
            "HTTP-Referer": "https://github.com/Kontrakevich/MarinsFasad",
            "X-Title": "Marins Facade Control Center",
        },
        method="POST",
    )

    try:
        with _mf067_urlrequest.urlopen(request, timeout=timeout_seconds) as response:
            content_type = (response.headers.get("Content-Type") or "").lower()
            if "text/event-stream" not in content_type:
                body = response.read().decode("utf-8", errors="replace")
                result = _mf067_json.loads(body)
                provider_error = _mf067_error_message(result)
                if provider_error:
                    raise RuntimeError(provider_error)
                found = _mf067_extract_image(result)
                if not found:
                    raise RuntimeError("OpenRouter ответил без изображения")
                image_bytes, media_type = found
                return image_bytes, media_type, {
                    "model": result.get("model") or model,
                    "usage": result.get("usage"),
                    "created": result.get("created"),
                    "transport": "buffered",
                    "timeout_seconds": timeout_seconds,
                    "reference": reference_meta,
                }

            last_image: tuple[bytes, str] | None = None
            usage = None
            returned_model = model
            created = None
            event_count = 0
            last_event_type = None

            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line or line.startswith(":") or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    event = _mf067_json.loads(data)
                except _mf067_json.JSONDecodeError:
                    continue

                event_count += 1
                if isinstance(event, dict):
                    last_event_type = event.get("type") or last_event_type
                    returned_model = event.get("model") or returned_model
                    usage = event.get("usage") or usage
                    created = event.get("created") or created

                provider_error = _mf067_error_message(event)
                if provider_error:
                    raise RuntimeError(provider_error)

                found = _mf067_extract_image(event)
                if found:
                    last_image = found

            if not last_image:
                raise RuntimeError(
                    "OpenRouter завершил streaming-ответ без изображения"
                    + (f"; последнее событие: {last_event_type}" if last_event_type else "")
                )

            image_bytes, media_type = last_image
            return image_bytes, media_type, {
                "model": returned_model,
                "usage": usage,
                "created": created,
                "transport": "sse",
                "stream_events": event_count,
                "timeout_seconds": timeout_seconds,
                "reference": reference_meta,
            }

    except _mf067_urlerror.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = _mf067_json.loads(body)
            detail = _mf067_error_message(parsed) or parsed.get("message") or parsed.get("detail") or body
        except Exception:
            detail = body or str(exc)
        raise RuntimeError(f"OpenRouter HTTP {exc.code}: {str(detail)[:1800]}") from exc
    except _mf067_urlerror.URLError as exc:
        raise RuntimeError(f"Не удалось подключиться к OpenRouter: {exc.reason}") from exc
    except TimeoutError as exc:
        raise RuntimeError(f"OpenRouter не передавал данные {timeout_seconds} секунд") from exc
    except _mf067_json.JSONDecodeError as exc:
        raise RuntimeError("OpenRouter вернул некорректный JSON") from exc
'''

main_path.write_text(main, "utf-8")

smoke_path = runtime / "tests/test_smoke.py"
if smoke_path.exists():
    smoke = smoke_path.read_text("utf-8")
    smoke = re.sub(
        r"assert response\.json\(\)\['version'\] == '[^']+'",
        "assert response.json()['version'] == '0.6.7'",
        smoke,
        count=1,
    )
    smoke_path.write_text(smoke, "utf-8")

index = index_path.read_text("utf-8")
ui_marker = "v0.6.7 runtime version display"
if ui_marker not in index:
    index = index.replace(
        "</body>",
        r'''
<script>
// v0.6.7 runtime version display
(() => {
  const updateVersion = () => {
    document.querySelectorAll('small, span, div').forEach(element => {
      if ((element.textContent || '').trim() === 'V0.6.6') element.textContent = 'V0.6.7';
      if ((element.textContent || '').trim() === '0.6.6') element.textContent = '0.6.7';
    });
  };
  updateVersion();
  document.addEventListener('DOMContentLoaded', updateVersion, { once: true });
})();
</script>
</body>''',
    )
index_path.write_text(index, "utf-8")

test_path.write_text(
    '''from pathlib import Path\n\n\ndef test_openrouter_uses_streaming_and_bounded_alpha_reference():\n    root = Path(__file__).resolve().parents[1]\n    main = (root / "app/main.py").read_text("utf-8")\n    assert "v0.6.7 streaming OpenRouter transport" in main\n    assert '\"stream\": True' in main\n    assert 'OPENROUTER_IMAGE_TIMEOUT", "900"' in main\n    assert 'OPENROUTER_REFERENCE_MAX_EDGE", "2048"' in main\n    assert 'convert("RGBA")' in main\n    assert '"transport": "sse"' in main\n    assert "OpenRouter не передавал данные" in main\n''',
    "utf-8",
)

print("Applied v0.6.7 streaming OpenRouter transport")
