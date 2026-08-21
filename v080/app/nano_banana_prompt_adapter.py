from __future__ import annotations

import hashlib
import re
from typing import Any

from . import ai_engine as _engine_module
from .prompt_engine import (
    FINAL_COMMAND_MARKER,
    GENERATION_MODE_MARKER,
    GENERATION_QUALITY_MARKER,
    OPERATOR_PROMPT_MARKER,
)
from .provider_retry import OpenRouterImageEngine as _RetryOpenRouterImageEngine


class OpenRouterImageEngine(_RetryOpenRouterImageEngine):
    """Final Nano Banana prompt adapter.

    The long compiled prompt remains the internal/audit contract. Nano Banana
    receives a shorter execution prompt that preserves the operator request,
    active skill, quality and geometry constraints without repeating every skill
    contract. Already concise internal-pass prompts and manually edited provider
    prompts are sent verbatim.
    """

    nano_banana_prompt_adapter_version = "1.0.1"
    nano_banana_prompt_transport_policy = "internal-contract-to-concise-nano-banana-execution-v1"
    adapter_marker = "NANO BANANA EXECUTION PROMPT v1"

    @staticmethod
    def _section(text: str, start_marker: str, end_marker: str | None = None) -> str:
        source = str(text or "")
        start = source.find(start_marker)
        if start < 0:
            return ""
        start += len(start_marker)
        if source[start:start + 1] == "\n":
            start += 1
        if end_marker:
            end = source.find(end_marker, start)
            if end >= 0:
                return source[start:end].strip()
        return source[start:].strip()

    @classmethod
    def _mode(cls, prompt: str) -> str:
        block = cls._section(prompt, GENERATION_MODE_MARKER, GENERATION_QUALITY_MARKER)
        first = block.splitlines()[0].strip().lower() if block else "hybrid"
        return first if first in {"hybrid", "relight", "edit", "outpaint"} else "hybrid"

    @classmethod
    def _quality(cls, prompt: str) -> str:
        block = cls._section(prompt, GENERATION_QUALITY_MARKER, "ACTIVE SKILL CONTRACT")
        first = block.splitlines()[0].strip().lower() if block else "high"
        return first if first in {"draft", "standard", "high", "max"} else "high"

    @classmethod
    def _operator(cls, prompt: str) -> str:
        block = cls._section(prompt, OPERATOR_PROMPT_MARKER, GENERATION_MODE_MARKER)
        if block:
            return block
        final = cls._section(prompt, FINAL_COMMAND_MARKER)
        if final:
            mode_pos = re.search(r"\n\s*Generation mode:", final, re.IGNORECASE)
            return final[: mode_pos.start()].strip() if mode_pos else final.strip()
        return str(prompt or "").strip()

    @staticmethod
    def _mode_rules(mode: str) -> str:
        if mode == "outpaint":
            return (
                "- Reconstruct only transparent or otherwise missing border regions of the provided corrected photograph.\n"
                "- Treat them as missing continuation of the same photograph, never as a separate patch.\n"
                "- Preserve every valid visible pixel outside missing regions.\n"
                "- Match neighbouring perspective, texture scale, sharpness, colour, lighting, grain and scene content."
            )
        if mode == "relight":
            return (
                "- Apply the requested lighting/weather/atmosphere transformation coherently across the full visible frame.\n"
                "- Preserve camera, framing, perspective and architectural geometry; original pixel values do not need to remain unchanged.\n"
                "- Do not remove or replace physical objects unless explicitly requested."
            )
        if mode == "edit":
            return (
                "- Execute all requested semantic edits visibly on the provided photograph.\n"
                "- Reconstruct physically plausible background behind removed objects.\n"
                "- Preserve camera, framing, perspective and architectural geometry except for explicitly requested local edits."
            )
        return (
            "- First execute all requested semantic edits and/or scene-wide lighting changes on the visible photograph.\n"
            "- Then reconstruct every transparent or otherwise missing border region as continuation of that edited photograph.\n"
            "- The second step must preserve the first-step edits and match their lighting, weather, materials and atmosphere.\n"
            "- Preserve corrected camera, framing, perspective and architectural geometry throughout."
        )

    @staticmethod
    def _quality_rule(quality: str) -> str:
        return {
            "draft": "Fast preview. Minimize extra refinement while preserving intent and geometry.",
            "standard": "Balanced quality. Maintain coherent detail and seamless continuation.",
            "high": "High quality. Prioritize photorealistic continuity, local detail and clean seams.",
            "max": "Maximum quality. Prefer fidelity over speed; use maximum useful context and detail consistency.",
        }[quality]

    @classmethod
    def _is_internal_compiled_contract(cls, prompt: str) -> bool:
        text = str(prompt or "")
        return (
            "SYSTEM PRESERVATION CONTRACT" in text
            or "ACTIVE SKILL CONTRACT" in text
            or FINAL_COMMAND_MARKER in text
        )

    @classmethod
    def adapt_execution_prompt(cls, compiled_prompt: str) -> str:
        source = str(compiled_prompt or "").strip()
        if not source:
            return source
        if source.startswith(cls.adapter_marker):
            return source
        if not cls._is_internal_compiled_contract(source):
            return source

        mode = cls._mode(source)
        quality = cls._quality(source)
        operator = cls._operator(source)
        return (
            f"{cls.adapter_marker}\n\n"
            "INPUT IMAGE ROLE\n"
            "The supplied image is the approved perspective-corrected architectural photograph and is the authoritative visual reference. "
            "Keep its canvas, camera position, framing, perspective, facade proportions, openings, floor count and architectural identity stable.\n\n"
            f"{OPERATOR_PROMPT_MARKER}\n{operator}\n\n"
            f"{GENERATION_MODE_MARKER}\n{mode.upper()}\n\n"
            f"{GENERATION_QUALITY_MARKER}\n{quality.upper()}\n\n"
            "EXECUTION RULES\n"
            f"{cls._mode_rules(mode)}\n\n"
            "QUALITY\n"
            f"{cls._quality_rule(quality)}\n\n"
            "IMPORTANT\n"
            "- Follow the complete operator request, not only its first clause.\n"
            "- Do not crop, rotate, reframe or stretch the photograph.\n"
            "- Do not invent unrelated architectural changes or unrelated objects.\n"
            "- Transparent/no-information corners created by perspective correction mean missing scene content that must be naturally reconstructed when the active skill includes outpaint.\n"
            "- Return one coherent photorealistic image, not a collage or a visibly patched image."
        )

    @classmethod
    def prompt_adapter_metadata(cls, compiled_prompt: str) -> dict[str, Any]:
        adapted = cls.adapt_execution_prompt(compiled_prompt)
        return {
            "provider_prompt": adapted,
            "provider_prompt_sha256": hashlib.sha256(adapted.encode("utf-8")).hexdigest(),
            "provider_prompt_length": len(adapted),
            "nano_banana_prompt_adapter_version": cls.nano_banana_prompt_adapter_version,
            "nano_banana_prompt_transport_policy": cls.nano_banana_prompt_transport_policy,
        }

    def _provider_prompt(self, prompt: str) -> tuple[str, bool]:
        exact = str(prompt or "").strip()
        adapted = self.adapt_execution_prompt(exact)
        return adapted, OPERATOR_PROMPT_MARKER in exact


_engine_module.OpenRouterImageEngine = OpenRouterImageEngine
