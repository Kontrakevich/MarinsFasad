from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .system_prompts import ENVIRONMENT_SYSTEM_PROMPT, PROMPT_CONTRACT_VERSION


OPERATOR_PROMPT_MARKER = "OPERATOR PROMPT — EXECUTE EXACTLY"
FINAL_COMMAND_MARKER = "FINAL COMMAND — EXECUTE THE OPERATOR PROMPT"
GENERATION_MODE_MARKER = "GENERATION MODE"
GENERATION_QUALITY_MARKER = "GENERATION QUALITY"
MODE_COMMENT_PREFIX = "__MARINS_GENERATION_MODE__:"
QUALITY_COMMENT_PREFIX = "__MARINS_GENERATION_QUALITY__:"
VALID_GENERATION_MODES = {"hybrid", "relight", "edit", "outpaint"}
VALID_GENERATION_QUALITIES = {"draft", "standard", "high", "max"}


@dataclass
class PromptContext:
    stage: str
    master_prompt: str
    skill: str = ""
    knowledge: str = ""
    history: list[str] = field(default_factory=list)
    comments: list[str] = field(default_factory=list)
    approved_geometry_asset: str = ""
    contract_version: str = ""
    generation_mode: str = ""
    generation_quality: str = ""


class PromptEngine:
    @staticmethod
    def _normalize_mode(value: str | None) -> str:
        mode = str(value or "").strip().lower()
        return mode if mode in VALID_GENERATION_MODES else "hybrid"

    @staticmethod
    def _normalize_quality(value: str | None) -> str:
        quality = str(value or "").strip().lower()
        return quality if quality in VALID_GENERATION_QUALITIES else "high"

    @classmethod
    def _mode_from_comments(cls, comments: list[str], explicit: str = "") -> str:
        mode = cls._normalize_mode(explicit) if str(explicit or "").strip() else "hybrid"
        for item in comments:
            text = str(item or "").strip()
            if text.lower().startswith(MODE_COMMENT_PREFIX.lower()):
                mode = cls._normalize_mode(text.split(":", 1)[1] if ":" in text else "")
        return mode

    @classmethod
    def _quality_from_comments(cls, comments: list[str], explicit: str = "") -> str:
        quality = cls._normalize_quality(explicit) if str(explicit or "").strip() else "high"
        for item in comments:
            text = str(item or "").strip()
            if text.lower().startswith(QUALITY_COMMENT_PREFIX.lower()):
                quality = cls._normalize_quality(text.split(":", 1)[1] if ":" in text else "")
        return quality

    @staticmethod
    def _is_service_comment(text: str) -> bool:
        lowered = str(text or "").strip().lower()
        return (
            lowered.startswith(MODE_COMMENT_PREFIX.lower())
            or lowered.startswith(QUALITY_COMMENT_PREFIX.lower())
        )

    @classmethod
    def _operator_comments(cls, comments: list[str]) -> list[str]:
        output: list[str] = []
        for item in comments:
            text = str(item or "").strip()
            if not text or cls._is_service_comment(text):
                continue
            output.append(text)
        return output

    @classmethod
    def _operator_prompt(cls, comments: list[str]) -> str:
        cleaned = cls._operator_comments(comments)
        if cleaned:
            return "\n".join(
                f"{index}. {item}" for index, item in enumerate(cleaned, start=1)
            )
        return (
            "1. Не вносить дополнительных смысловых изменений. "
            "Естественно восстановить отсутствующее окружение, если оно есть."
        )

    @staticmethod
    def _mode_contract(mode: str) -> str:
        if mode == "relight":
            return (
                "RELIGHT / NEW LIGHTING SKILL.\n"
                "The operator request defines a scene-wide lighting and atmosphere transformation.\n"
                "You may change illumination across every visible pixel: sky, cloud cover, sun direction, ambient light, exposure, white balance, shadows, reflections, wetness response, time of day and photographic atmosphere.\n"
                "Do NOT restore original source pixels after relighting; a coherent global lighting transformation is required.\n"
                "Preserve camera, framing, perspective, building geometry, facade proportions, openings and architectural identity.\n"
                "Do not remove or replace unrelated physical objects unless the operator also explicitly requests that edit."
            )
        if mode == "edit":
            return (
                "IMAGE EDIT SKILL.\n"
                "The operator request is the dominant task. Perform the requested semantic edit strongly and visibly.\n"
                "Object removals, replacements, cleanup and property changes are allowed exactly where requested.\n"
                "If the request explicitly changes weather, atmosphere or lighting, that requested change may affect the full frame.\n"
                "Do NOT restore original pixels over requested edits; reconstruct the physically plausible scene after the edit.\n"
                "Preserve corrected camera position and architectural geometry unless an exact architectural element is explicitly targeted."
            )
        if mode == "outpaint":
            return (
                "OUTPAINT SKILL.\n"
                "Reconstruct only visual information missing after perspective correction.\n"
                "Existing visible pixels are immutable and must be preserved exactly.\n"
                "The FULL OPERATOR PROMPT remains mandatory scene context: its weather, lighting, materials, atmosphere and visual requirements define how the missing continuation must look.\n"
                "Seam blending is allowed only inside the missing region in a narrow transition band at its boundary.\n"
                "Do not independently execute unrelated semantic edits outside the missing region."
            )
        return (
            "HYBRID SKILL — SEMANTIC EDIT / RELIGHT FIRST, OUTPAINT SECOND.\n"
            "Pass 1: execute every semantic edit and scene-wide lighting/weather transformation explicitly requested by the operator.\n"
            "Do not restore original pixels over the completed Pass-1 edit. Preserve corrected architectural geometry.\n"
            "Pass 2: reconstruct only the visual information missing after perspective correction, while retaining the FULL compiled prompt as mandatory context so the continuation matches every requested lighting, weather, material and atmosphere requirement.\n"
            "The final image must be one coherent photorealistic photograph."
        )

    @staticmethod
    def _quality_contract(quality: str) -> str:
        if quality == "draft":
            return (
                "DRAFT QUALITY. Fast preview-oriented execution. Preserve geometry and prompt intent, "
                "but minimize repair passes and local refinement."
            )
        if quality == "standard":
            return (
                "STANDARD QUALITY. Use normal full-frame generation and repair only detected failures. "
                "Maintain coherent texture and scene continuation."
            )
        if quality == "max":
            return (
                "MAXIMUM QUALITY. Prefer seamless scene continuation over speed. Use the largest useful surrounding context, "
                "multiple local candidates when needed, strong seam harmonization and maximum available detail consistency."
            )
        return (
            "HIGH QUALITY. Prioritize photorealistic continuity and detail. Use context-rich local edge refinement for outpaint, "
            "harmonize tone/detail at seams and reject visibly low-detail patch-like continuation."
        )

    def compile(self, context: PromptContext, project_dir: Path) -> dict:
        is_environment = context.stage.lower() == "environment"
        system_prompt = (
            ENVIRONMENT_SYSTEM_PROMPT
            if is_environment
            else context.master_prompt.strip()
        )
        contract_version = (
            PROMPT_CONTRACT_VERSION
            if is_environment
            else (context.contract_version or "unversioned")
        )
        system_sha256 = hashlib.sha256(system_prompt.encode("utf-8")).hexdigest()

        generation_mode = (
            self._mode_from_comments(context.comments, context.generation_mode)
            if is_environment
            else "stage-default"
        )
        generation_quality = (
            self._quality_from_comments(context.comments, context.generation_quality)
            if is_environment
            else "stage-default"
        )
        operator_prompt = self._operator_prompt(context.comments)
        operator_prompt_sha256 = hashlib.sha256(
            operator_prompt.encode("utf-8")
        ).hexdigest()

        if is_environment:
            approved_base = (
                context.approved_geometry_asset
                or "Approved corrected geometry image supplied by the pipeline"
            )
            sections = [
                (OPERATOR_PROMPT_MARKER, operator_prompt),
                (GENERATION_MODE_MARKER, generation_mode.upper()),
                (GENERATION_QUALITY_MARKER, generation_quality.upper()),
                ("ACTIVE SKILL CONTRACT", self._mode_contract(generation_mode)),
                ("QUALITY EXECUTION CONTRACT", self._quality_contract(generation_quality)),
                (
                    "FULL PROMPT CONTEXT RULE",
                    (
                        "Every operator instruction above remains active context for every internal generation pass.\n"
                        "Never reduce the request to only the first phrase such as 'outpaint' or 'continue the image'.\n"
                        "For outpaint, use the entire operator request to match weather, lighting, time of day, materials, atmosphere, removals already completed in a previous pass, and all other scene constraints."
                    ),
                ),
                (
                    "APPROVED CORRECTED GEOMETRY",
                    (
                        f"{approved_base}\n"
                        "This corrected photograph is the authoritative camera and geometry reference.\n"
                        "Do not crop, reframe, stretch or geometrically redesign the building."
                    ),
                ),
                (
                    "SEMANTIC IMAGE EDITING",
                    (
                        "When the active skill permits semantic editing, execute all explicit operator instructions visibly.\n"
                        "Removing poles, overhead wires, cables, cars, signs or temporary clutter is a normal image-edit operation when requested.\n"
                        "Reconstruct the physically plausible background behind removed objects.\n"
                        "Do not use pixel restoration that would undo the requested edit."
                    ),
                ),
                (
                    "SCENE-WIDE LIGHTING",
                    (
                        "When RELIGHT is active, or when HYBRID/IMAGE EDIT explicitly requests new weather or lighting, the entire visible photograph may change photometrically.\n"
                        "Global illumination, sky, shadows, reflections, exposure and atmosphere must remain physically coherent across the whole frame.\n"
                        "Geometry preservation does not mean pixel preservation in these skills."
                    ),
                ),
                (
                    "AUTOMATIC OUTPAINT",
                    (
                        "When the active skill includes outpaint, detect and reconstruct every area where the corrected geometry contains no visual information.\n"
                        "Continue existing structures and textures through the missing area; never create an independent patch or a visually unrelated replacement.\n"
                        "Match neighbouring perspective, scale, texture frequency, sharpness, colour, lighting and photographic noise.\n"
                        "Do not return blank, flat-colour or low-detail wedges."
                    ),
                ),
                ("SYSTEM PRESERVATION CONTRACT", system_prompt),
                ("PROMPT CONTRACT", contract_version),
                (
                    "VALIDATED HISTORY",
                    "\n".join(f"- {item}" for item in context.history)
                    or "No validated history.",
                ),
                ("KNOWLEDGE", context.knowledge or "No additional knowledge supplied."),
                (
                    FINAL_COMMAND_MARKER,
                    (
                        f"{operator_prompt}\n\n"
                        f"Generation mode: {generation_mode.upper()}. Generation quality: {generation_quality.upper()}. "
                        "Execute the complete operator prompt, not only its first clause. Preserve corrected camera and architectural geometry. "
                        "Apply pixel-exact preservation only when the active skill is OUTPAINT; do not use it to undo RELIGHT or IMAGE EDIT results."
                    ),
                ),
            ]
        else:
            sections = [
                ("SYSTEM PROMPT — AUTHORITATIVE", system_prompt),
                ("PROMPT CONTRACT", contract_version),
                ("CURRENT STAGE", context.stage.upper()),
                ("STAGE SKILL", context.skill or "No stage-specific skill supplied."),
                ("KNOWLEDGE", context.knowledge or "No additional knowledge supplied."),
                (
                    "VALIDATED HISTORY",
                    "\n".join(f"- {item}" for item in context.history)
                    or "No validated history.",
                ),
                ("OPERATOR COMMENTS — MANDATORY", operator_prompt),
                (
                    "EXECUTION",
                    "Execute the active stage according to the authoritative system prompt and mandatory operator comments.",
                ),
            ]

        prompt = "\n\n".join(
            f"{title}\n{body.strip()}" for title, body in sections
        )
        prompt_sha256 = hashlib.sha256(prompt.encode("utf-8")).hexdigest()

        folder = project_dir / "prompts" / context.stage
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        path = folder / f"compiled_{stamp}.txt"
        path.write_text(prompt + "\n", "utf-8")

        visible_comments = self._operator_comments(context.comments)
        return {
            "prompt": prompt,
            "file": str(path.relative_to(project_dir)),
            "path": str(path.relative_to(project_dir)),
            "prompt_sha256": prompt_sha256,
            "prompt_length": len(prompt),
            "operator_prompt": operator_prompt,
            "operator_prompt_sha256": operator_prompt_sha256,
            "operator_prompt_marker": OPERATOR_PROMPT_MARKER,
            "final_command_marker": FINAL_COMMAND_MARKER,
            "generation_mode_marker": GENERATION_MODE_MARKER,
            "generation_quality_marker": GENERATION_QUALITY_MARKER,
            "system_prompt": system_prompt,
            "system_prompt_sha256": system_sha256,
            "contract_version": contract_version,
            "approved_geometry_asset": context.approved_geometry_asset,
            "operator_comment_count": len(visible_comments),
            "generation_mode": generation_mode,
            "generation_quality": generation_quality,
            "outpaint_detection": "automatic-from-approved-geometry" if is_environment else "stage-default",
            "provider_model": "google/gemini-2.5-flash-image" if is_environment else "stage-default",
            "pixel_preservation": (
                "existing-visible-pixels-exact"
                if is_environment and generation_mode == "outpaint"
                else "geometry-preserved-photometry-may-change"
                if is_environment and generation_mode == "relight"
                else "geometry-preserved-requested-edits-retained"
                if is_environment and generation_mode in {"edit", "hybrid"}
                else "stage-default"
            ),
            "prompt_transport_policy": "ui-compiled-prompt-sent-verbatim" if is_environment else "stage-default",
            "missing_region_policy": "automatic-outpaint-when-skill-includes-it" if is_environment else "stage-default",
            "full_prompt_context_policy": "all-operator-instructions-propagate-to-every-pass" if is_environment else "stage-default",
        }
