from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import ai_engine as _engine_module
from .prompt_engine import FINAL_COMMAND_MARKER, OPERATOR_PROMPT_MARKER


_PreviousOpenRouterImageEngine = _engine_module.OpenRouterImageEngine
AIEngineError = _engine_module.AIEngineError


class OpenRouterImageEngine(_PreviousOpenRouterImageEngine):
    """Ensures the exact UI-compiled prompt is the provider prompt."""

    prompt_transport_policy = "ui-compiled-prompt-sent-verbatim"

    @staticmethod
    def _clean_prompt(prompt: str) -> str:
        exact = str(prompt or "").strip()
        if not exact:
            raise AIEngineError(
                "Промпт генерации пустой.",
                details={
                    "reason": "empty_generation_prompt",
                    "provider_call_made": False,
                    "credits_spent": False,
                },
            )
        return exact

    @staticmethod
    def _prompt_sha256(prompt: str) -> str:
        return hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    def _build_payload(
        self,
        *,
        prompt: str,
        geometry_image: Path,
        outpaint_mask: Path,
        provider_size: tuple[int, int],
    ) -> dict:
        # No prompt rewriting is allowed here. The same compiled prompt displayed
        # in the UI becomes the exact provider prompt.
        exact_prompt = self._clean_prompt(prompt)
        return {
            "model": self.required_model,
            "prompt": exact_prompt,
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
        supported_sizes=None,
    ) -> dict:
        exact_prompt = self._clean_prompt(prompt)
        prompt_sha256 = self._prompt_sha256(exact_prompt)

        prepared = super().prepare_environment_inputs(
            prompt=exact_prompt,
            geometry_image=geometry_image,
            outpaint_mask=outpaint_mask,
            output_dir=output_dir,
            width=width,
            height=height,
            forced_max_request_bytes=forced_max_request_bytes,
            forced_target_request_bytes=forced_target_request_bytes,
            supported_sizes=supported_sizes,
        )

        output_dir.mkdir(parents=True, exist_ok=True)
        sent_prompt_path = output_dir / "compiled-prompt-sent.txt"
        sent_prompt_path.write_text(exact_prompt + "\n", "utf-8")

        prepared.update(
            {
                "prompt_transport_policy": self.prompt_transport_policy,
                "compiled_prompt_sent": exact_prompt,
                "compiled_prompt_sent_path": str(sent_prompt_path),
                "compiled_prompt_sent_sha256": prompt_sha256,
                "compiled_prompt_sent_length": len(exact_prompt),
                "operator_prompt_marker_present": OPERATOR_PROMPT_MARKER in exact_prompt,
                "final_command_marker_present": FINAL_COMMAND_MARKER in exact_prompt,
                "prompt_match": True,
            }
        )
        (output_dir / "transport.json").write_text(
            json.dumps(prepared, ensure_ascii=False, indent=2),
            "utf-8",
        )
        return prepared

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
        exact_prompt = self._clean_prompt(prompt)
        expected_sha256 = self._prompt_sha256(exact_prompt)

        if prepared_input:
            prepared_sha256 = prepared_input.get("compiled_prompt_sent_sha256")
            if prepared_sha256 and prepared_sha256 != expected_sha256:
                raise AIEngineError(
                    "Промпт в интерфейсе не совпадает с подготовленным запросом. Генерация остановлена.",
                    details={
                        "reason": "prepared_prompt_mismatch",
                        "provider_call_made": False,
                        "credits_spent": False,
                        "ui_prompt_sha256": expected_sha256,
                        "prepared_prompt_sha256": prepared_sha256,
                    },
                )

        result = super().generate_environment(
            prompt=exact_prompt,
            geometry_image=geometry_image,
            outpaint_mask=outpaint_mask,
            output_dir=output_dir,
            width=width,
            height=height,
            prepared_input=prepared_input,
        )

        sent_prompt = str((result.get("request") or {}).get("prompt") or "")
        sent_sha256 = self._prompt_sha256(sent_prompt) if sent_prompt else ""
        prompt_match = sent_prompt == exact_prompt and sent_sha256 == expected_sha256
        if not prompt_match:
            raise AIEngineError(
                "Пользовательский промпт был изменён перед отправкой в Nano Banana.",
                details={
                    "reason": "provider_prompt_mismatch",
                    "ui_prompt_sha256": expected_sha256,
                    "sent_prompt_sha256": sent_sha256,
                    "provider_call_made": True,
                },
            )

        result.update(
            {
                "compiled_prompt_ui": exact_prompt,
                "compiled_prompt_sent": sent_prompt,
                "prompt_sha256": expected_sha256,
                "sent_prompt_sha256": sent_sha256,
                "prompt_match": True,
                "prompt_transport_policy": self.prompt_transport_policy,
                "operator_prompt_marker_present": OPERATOR_PROMPT_MARKER in exact_prompt,
                "final_command_marker_present": FINAL_COMMAND_MARKER in exact_prompt,
            }
        )
        (output_dir / "generation.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            "utf-8",
        )
        return result


_engine_module.OpenRouterImageEngine = OpenRouterImageEngine
