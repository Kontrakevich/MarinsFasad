from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .system_prompts import ENVIRONMENT_SYSTEM_PROMPT, PROMPT_CONTRACT_VERSION


OPERATOR_PROMPT_MARKER = "OPERATOR PROMPT — EXECUTE EXACTLY"
FINAL_COMMAND_MARKER = "FINAL COMMAND — EXECUTE THE OPERATOR PROMPT"
GENERATION_MODE_MARKER = "GENERATION MODE"
MODE_COMMENT_PREFIX = "__MARINS_GENERATION_MODE__:"
VALID_GENERATION_MODES = {"hybrid", "edit", "outpaint"}


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


class PromptEngine:
    @staticmethod
    def _normalize_mode(value: str | None) -> str:
        mode = str(value or "").strip().lower()
        return mode if mode in VALID_GENERATION_MODES else "hybrid"

    @classmethod
    def _mode_from_comments(cls, comments: list[str], explicit: str = "") -> str:
        mode = cls._normalize_mode(explicit) if str(explicit or "").strip() else "hybrid"
        for item in comments:
            text = str(item or "").strip()
            if text.lower().startswith(MODE_COMMENT_PREFIX.lower()):
                mode = cls._normalize_mode(text.split(":", 1)[1] if ":" in text else "")
        return mode

    @staticmethod
    def _operator_comments(comments: list[str]) -> list[str]:
        output: list[str] = []
        for item in comments:
            text = str(item or "").strip()
            if not text:
                continue
            if text.lower().startswith(MODE_COMMENT_PREFIX.lower()):
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
        if mode == "edit":
            return (
                "IMAGE EDIT MODE.\n"
                "The operator request is the dominant task. Perform the requested semantic image edit strongly and visibly.\n"
                "Object removals, replacements and global weather/atmosphere changes are allowed when requested.\n"
                "Preserve corrected camera position and architectural geometry.\n"
                "Do not let missing-edge reconstruction distract from the requested edit."
            )
        if mode == "outpaint":
            return (
                "OUTPAINT MODE.\n"
                "Reconstruct only visual information missing after perspective correction.\n"
                "Existing visible pixels are immutable and must be preserved exactly.\n"
                "Do not perform unrelated semantic edits, weather changes or scene redesign."
            )
        return (
            "HYBRID MODE — IMAGE EDIT + OUTPAINT.\n"
            "First priority: execute every semantic edit requested by the operator, including object cleanup and global weather/atmosphere changes.\n"
            "Also reconstruct all visual information missing after perspective correction.\n"
            "Return one coherent photorealistic edited photograph.\n"
            "Preserve the corrected camera and architectural geometry while allowing the requested environment to change."
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
        operator_prompt = self._operator_prompt(context.comments)
        operator_prompt_sha256 = hashlib.sha256(
            operator_prompt.encode("utf-8")
        ).hexdigest()

        if is_environment:
            approved_base = (
                context.approved_geometry_asset
                or "Approved corrected geometry image supplied by the pipeline"
            )
            mode_contract = self._mode_contract(generation_mode)
            sections = [
                (OPERATOR_PROMPT_MARKER, operator_prompt),
                (GENERATION_MODE_MARKER, generation_mode.upper()),
                ("MODE EXECUTION CONTRACT", mode_contract),
                (
                    "APPROVED CORRECTED GEOMETRY",
                    (
                        f"{approved_base}\n"
                        "This corrected photograph is the authoritative geometry and camera reference.\n"
                        "Do not crop, reframe, stretch or geometrically redesign the building."
                    ),
                ),
                (
                    "SEMANTIC EDIT PRIORITY",
                    (
                        "Execute all explicit operator instructions visibly.\n"
                        "Removing poles, overhead wires, cables, cars, signs or temporary clutter is a normal image-edit task when requested.\n"
                        "Changing weather, clouds, sky, daylight, season, wetness or scene atmosphere may affect the whole environment when explicitly requested.\n"
                        "Reconstruct physically plausible background behind removed objects."
                    ),
                ),
                (
                    "AUTOMATIC OUTPAINT",
                    (
                        "When the selected mode includes outpaint, detect and reconstruct every area where the corrected geometry contains no visual information.\n"
                        "Continue the neighbouring scene naturally with correct perspective and lighting.\n"
                        "Do not return blank or flat-colour wedges."
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
                        f"Generation mode: {generation_mode.upper()}. "
                        "Perform the requested image edit now. Keep the corrected architecture geometrically stable. "
                        "When this mode includes outpaint, also complete every missing part of the surroundings."
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
            "system_prompt": system_prompt,
            "system_prompt_sha256": system_sha256,
            "contract_version": contract_version,
            "approved_geometry_asset": context.approved_geometry_asset,
            "operator_comment_count": len(visible_comments),
            "generation_mode": generation_mode,
            "outpaint_detection": "automatic-from-approved-geometry" if is_environment else "stage-default",
            "provider_model": "google/gemini-2.5-flash-image" if is_environment else "stage-default",
            "pixel_preservation": (
                "existing-visible-pixels-exact"
                if is_environment and generation_mode == "outpaint"
                else "architecture-geometry-preserved-by-prompt"
                if is_environment
                else "stage-default"
            ),
            "prompt_transport_policy": "ui-compiled-prompt-sent-verbatim" if is_environment else "stage-default",
            "missing_region_policy": "automatic-outpaint-when-mode-includes-it" if is_environment else "stage-default",
        }
