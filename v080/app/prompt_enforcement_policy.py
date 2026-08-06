from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import ai_engine as _engine_module
from .prompt_engine import FINAL_COMMAND_MARKER, OPERATOR_PROMPT_MARKER
from .system_prompts import ENVIRONMENT_SYSTEM_PROMPT, PROMPT_CONTRACT_VERSION


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

    def _provider_prompt(self, prompt: str) -> tuple[str, bool]:
        exact = self._clean_prompt(prompt)
        is_ui_compiled = (
            OPERATOR_PROMPT_MARKER in exact
            and FINAL_COMMAND_MARKER in exact
        )
        if is_ui_compiled:
            return exact, True
        if ENVIRONMENT_SYSTEM_PROMPT in exact:
            return exact, False
        # Compatibility for direct engine callers and isolated tests. The normal
        # application path always supplies the UI-compiled prompt and therefore
        # never enters this fallback.
        wrapped = (
            f"SYSTEM PROMPT — {PROMPT_CONTRACT_VERSION}\n"
            f"{ENVIRONMENT_SYSTEM_PROMPT}\n\n"
            "PROJECT EXECUTION PROMPT\n"
            f"{exact}"
        )
        return wrapped, False

    def _build_payload(
        self,
        *,
        prompt: str,
        geometry_image: Path,
        outpaint_mask: Path,
        provider_size: tuple[int, int],
    ) -> dict:
        provider_prompt, _ = self._provider_prompt(prompt)
        return {
            "model": self.required_model,
            "prompt": provider_prompt,
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
        ui_prompt = self._clean_prompt(prompt)
        provider_prompt, is_ui_compiled = self._provider_prompt(ui_prompt)
        ui_prompt_sha256 = self._prompt_sha256(ui_prompt)
        sent_prompt_sha256 = self._prompt_sha256(provider_prompt)

        prepared = super().prepare_environment_inputs(
            prompt=ui_prompt,
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
        sent_prompt_path.write_text(provider_prompt + "\n", "utf-8")

        prepared.update(
            {
                "prompt_transport_policy": self.prompt_transport_policy,
                "compiled_prompt_ui": ui_prompt,
                "compiled_prompt_ui_sha256": ui_prompt_sha256,
                "compiled_prompt_sent": provider_prompt,
                "compiled_prompt_sent_path": str(sent_prompt_path),
                "compiled_prompt_sent_sha256": sent_prompt_sha256,
                "compiled_prompt_sent_length": len(provider_prompt),
                "operator_prompt_marker_present": OPERATOR_PROMPT_MARKER in ui_prompt,
                "final_command_marker_present": FINAL_COMMAND_MARKER in ui_prompt,
                "ui_compiled_prompt": is_ui_compiled,
                "prompt_match": provider_prompt == ui_prompt,
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
        ui_prompt = self._clean_prompt(prompt)
        provider_prompt, is_ui_compiled = self._provider_prompt(ui_prompt)
        expected_ui_sha256 = self._prompt_sha256(ui_prompt)
        expected_sent_sha256 = self._prompt_sha256(provider_prompt)

        if prepared_input:
            prepared_sha256 = prepared_input.get("compiled_prompt_sent_sha256")
            if prepared_sha256 and prepared_sha256 != expected_sent_sha256:
                raise AIEngineError(
                    "Промпт в интерфейсе не совпадает с подготовленным запросом. Генерация остановлена.",
                    details={
                        "reason": "prepared_prompt_mismatch",
                        "provider_call_made": False,
                        "credits_spent": False,
                        "ui_prompt_sha256": expected_ui_sha256,
                        "expected_sent_prompt_sha256": expected_sent_sha256,
                        "prepared_prompt_sha256": prepared_sha256,
                    },
                )

        result = super().generate_environment(
            prompt=ui_prompt,
            geometry_image=geometry_image,
            outpaint_mask=outpaint_mask,
            output_dir=output_dir,
            width=width,
            height=height,
            prepared_input=prepared_input,
        )

        sent_prompt = str((result.get("request") or {}).get("prompt") or "")
        sent_sha256 = self._prompt_sha256(sent_prompt) if sent_prompt else ""
        provider_prompt_match = (
            sent_prompt == provider_prompt
            and sent_sha256 == expected_sent_sha256
        )
        ui_prompt_match = sent_prompt == ui_prompt
        if not provider_prompt_match:
            raise AIEngineError(
                "Пользовательский промпт был изменён перед отправкой в Nano Banana.",
                details={
                    "reason": "provider_prompt_mismatch",
                    "ui_prompt_sha256": expected_ui_sha256,
                    "expected_sent_prompt_sha256": expected_sent_sha256,
                    "sent_prompt_sha256": sent_sha256,
                    "provider_call_made": True,
                },
            )
        if is_ui_compiled and not ui_prompt_match:
            raise AIEngineError(
                "Собранный в интерфейсе промпт не был отправлен в Nano Banana дословно.",
                details={
                    "reason": "ui_prompt_not_sent_verbatim",
                    "ui_prompt_sha256": expected_ui_sha256,
                    "sent_prompt_sha256": sent_sha256,
                    "provider_call_made": True,
                },
            )

        result.update(
            {
                "compiled_prompt_ui": ui_prompt,
                "compiled_prompt_sent": sent_prompt,
                "prompt_sha256": expected_ui_sha256,
                "sent_prompt_sha256": sent_sha256,
                "prompt_match": ui_prompt_match,
                "provider_prompt_match": provider_prompt_match,
                "prompt_transport_policy": self.prompt_transport_policy,
                "operator_prompt_marker_present": OPERATOR_PROMPT_MARKER in ui_prompt,
                "final_command_marker_present": FINAL_COMMAND_MARKER in ui_prompt,
                "ui_compiled_prompt": is_ui_compiled,
            }
        )
        (output_dir / "generation.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            "utf-8",
        )
        return result


_engine_module.OpenRouterImageEngine = OpenRouterImageEngine
