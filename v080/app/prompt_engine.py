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
    approved_mask_asset: str = ""
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
            "Только естественно заполнить обязательные пустые области маски."
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

        if is_environment:
            operator_prompt = self._operator_prompt(context.comments)
            operator_prompt_sha256 = hashlib.sha256(
                operator_prompt.encode("utf-8")
            ).hexdigest()
            approved_base = (
                context.approved_geometry_asset
                or "Reference image 1 supplied by the pipeline"
            )
            edit_map = (
                context.approved_mask_asset
                or "Reference image 2 supplied by the pipeline"
            )

            # The operator instruction is deliberately placed first and repeated
            # as the final command. This exact text is shown in the UI and sent to
            # Nano Banana without any later rewriting.
            sections = [
                (
                    OPERATOR_PROMPT_MARKER,
                    operator_prompt,
                ),
                (
                    "PRIMARY EXECUTION PRIORITY",
                    (
                        "Execute every operator instruction above visibly and precisely.\n"
                        "The operator prompt is the primary generation task.\n"
                        "Mandatory outpaint completion is secondary and must not replace, weaken or hide the requested changes.\n"
                        "Do not return a result that only fills the mask while ignoring the operator prompt."
                    ),
                ),
                (
                    "APPROVED IMMUTABLE BASE",
                    (
                        f"{approved_base}\n"
                        "Use the corrected and approved immutable base as reference image 1.\n"
                        "Preserve all unaffected content pixel-for-pixel in final compositing."
                    ),
                ),
                (
                    "EDIT REFERENCE",
                    (
                        f"{edit_map}\n"
                        "Reference image 2 is the aligned edit map. White areas are mandatory outpaint areas. "
                        "Black areas are protected except for exact local targets explicitly named by the operator."
                    ),
                ),
                (
                    "SELECTIVE IMAGE EDITING ONLY",
                    (
                        "Use Nano Banana for selective image editing only.\n"
                        "Modify the exact objects, materials or areas named by the operator.\n"
                        "Do not regenerate, redesign, recolor or relight the complete frame.\n"
                        "Every unaffected pixel must remain identical after final compositing.\n"
                        "Keep the approved camera, geometry, perspective, framing and dimensions."
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
                        "Perform these exact changes now. Preserve everything else. "
                        "A result that ignores any operator instruction is invalid."
                    ),
                ),
            ]
        else:
            operator_prompt = self._operator_prompt(context.comments)
            operator_prompt_sha256 = hashlib.sha256(
                operator_prompt.encode("utf-8")
            ).hexdigest()
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
            "approved_mask_asset": context.approved_mask_asset,
            "operator_comment_count": len(context.comments),
            "generation_mode": "selective-edit" if is_environment else "stage-default",
            "mask_role": "mandatory-edit-reference" if is_environment else "stage-default",
            "provider_model": "google/gemini-2.5-flash-image" if is_environment else "stage-default",
            "pixel_preservation": "outside-edit-area-exact" if is_environment else "stage-default",
            "prompt_transport_policy": "ui-compiled-prompt-sent-verbatim" if is_environment else "stage-default",
        }
