from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .system_prompts import ENVIRONMENT_SYSTEM_PROMPT, PROMPT_CONTRACT_VERSION


OPERATOR_PROMPT_MARKER = "OPERATOR PROMPT — EXECUTE EXACTLY"
FINAL_COMMAND_MARKER = "FINAL COMMAND — EXECUTE THE OPERATOR PROMPT"


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


class PromptEngine:
    @staticmethod
    def _operator_prompt(comments: list[str]) -> str:
        cleaned = [str(item).strip() for item in comments if str(item).strip()]
        if cleaned:
            return "\n".join(
                f"{index}. {item}" for index, item in enumerate(cleaned, start=1)
            )
        return (
            "1. Не вносить дополнительных смысловых изменений. "
            "Выполнить естественный outpaint всех отсутствующих участков окружения."
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
                (
                    OPERATOR_PROMPT_MARKER,
                    operator_prompt,
                ),
                (
                    "PRIMARY EXECUTION PRIORITY",
                    (
                        "Execute every operator instruction above visibly and precisely.\n"
                        "The operator prompt is the primary editing task.\n"
                        "Automatic outpaint completion must also be performed wherever the approved geometry has no visual information.\n"
                        "Do not ignore the operator prompt and do not replace it with a generic full-frame regeneration."
                    ),
                ),
                (
                    "APPROVED IMMUTABLE BASE",
                    (
                        f"{approved_base}\n"
                        "This corrected geometry image is the only approved project input.\n"
                        "Preserve all existing visible content pixel-for-pixel during final compositing."
                    ),
                ),
                (
                    "AUTOMATIC OUTPAINT",
                    (
                        "The application automatically detects every transparent or missing area created by perspective correction.\n"
                        "These missing areas are marked inside the supplied geometry image only as a service signal for reconstruction.\n"
                        "They are not part of the photograph. Reconstruct them as a seamless photorealistic continuation of the adjacent scene.\n"
                        "Continue sky, buildings, facade edges, pavement, asphalt, ground, shadows, wires, vegetation and perspective as appropriate.\n"
                        "Never leave white, black, transparent, checkerboard or flat-colour wedges."
                    ),
                ),
                (
                    "SELECTIVE IMAGE EDITING",
                    (
                        "Use Nano Banana to perform the exact local changes named by the operator.\n"
                        "Do not regenerate, redesign, recolour or relight the complete frame.\n"
                        "Keep the approved camera, geometry, framing and dimensions.\n"
                        "Everything not explicitly requested and not missing must remain unchanged."
                    ),
                ),
                (
                    "SYSTEM PRESERVATION CONTRACT",
                    system_prompt,
                ),
                (
                    "PROMPT CONTRACT",
                    contract_version,
                ),
                (
                    "VALIDATED HISTORY",
                    "\n".join(f"- {item}" for item in context.history)
                    or "No validated history.",
                ),
                (
                    "KNOWLEDGE",
                    context.knowledge or "No additional knowledge supplied.",
                ),
                (
                    FINAL_COMMAND_MARKER,
                    (
                        f"{operator_prompt}\n\n"
                        "Perform these exact changes now. Complete all automatically detected missing surroundings with real scene content. "
                        "Preserve everything else. A result that ignores the operator instruction or leaves blank wedges is invalid."
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
            "system_prompt": system_prompt,
            "system_prompt_sha256": system_sha256,
            "contract_version": contract_version,
            "approved_geometry_asset": context.approved_geometry_asset,
            "operator_comment_count": len(context.comments),
            "generation_mode": "automatic-outpaint-and-selective-edit" if is_environment else "stage-default",
            "outpaint_detection": "automatic-from-approved-geometry" if is_environment else "stage-default",
            "provider_model": "google/gemini-2.5-flash-image" if is_environment else "stage-default",
            "pixel_preservation": "existing-visible-pixels-exact" if is_environment else "stage-default",
            "prompt_transport_policy": "ui-compiled-prompt-sent-verbatim" if is_environment else "stage-default",
            "missing_region_policy": "automatically-detected-and-photorealistically-reconstructed" if is_environment else "stage-default",
        }
