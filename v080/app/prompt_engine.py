from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .system_prompts import ENVIRONMENT_SYSTEM_PROMPT, PROMPT_CONTRACT_VERSION


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
            stage_skill = (
                "Use Nano Banana for selective image editing only. "
                "Treat the approved corrected image as the immutable base. "
                "Modify only the exact local objects or areas named by the operator and all mandatory white-mask areas. "
                "Do not regenerate, recolor, relight or redesign the complete frame. "
                "Every unaffected pixel must remain identical after final compositing."
            )
            mask_description = (
                f"{context.approved_mask_asset}\n"
                "White pixels are mandatory edit/outpaint areas. Black pixels remain protected unless the operator prompt explicitly names one local target there."
                if context.approved_mask_asset
                else "No mandatory outpaint mask is present. Local edit targets must be derived only from the operator prompt."
            )
            execution = (
                "Use reference image 1 as the immutable approved base and reference image 2 as the mandatory edit map. "
                "Perform only the point changes explicitly requested in OPERATOR COMMENTS. "
                "Keep edits localized. Preserve every unaffected element and do not create a full-frame variation. "
                "Return one complete image at the same composition and dimensions."
            )
        else:
            stage_skill = context.skill or "No stage-specific skill supplied."
            mask_description = context.approved_mask_asset or "No approved outpaint mask supplied."
            execution = "Execute the active stage according to the authoritative system prompt and mandatory operator comments."

        sections = [
            ("SYSTEM PROMPT — AUTHORITATIVE", system_prompt),
            ("PROMPT CONTRACT", contract_version),
            ("CURRENT STAGE", context.stage.upper()),
            (
                "APPROVED IMMUTABLE BASE",
                context.approved_geometry_asset
                or (
                    "Reference image 1 supplied by the environment pipeline is the corrected and approved immutable base."
                    if is_environment
                    else "No approved geometry asset supplied."
                ),
            ),
            ("EDIT MASK ROLE", mask_description),
            ("STAGE SKILL", stage_skill),
            ("KNOWLEDGE", context.knowledge or "No additional knowledge supplied."),
            (
                "VALIDATED HISTORY",
                "\n".join(f"- {item}" for item in context.history)
                or "No validated history.",
            ),
            (
                "OPERATOR COMMENTS — MANDATORY LOCAL CHANGES",
                "\n".join(f"- {item}" for item in context.comments)
                or "No additional local changes. Fill only mandatory outpaint areas.",
            ),
            ("EXECUTION", execution),
        ]
        prompt = "\n\n".join(
            f"{title}\n{body.strip()}" for title, body in sections
        )

        folder = project_dir / "prompts" / context.stage
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        path = folder / f"compiled_{stamp}.txt"
        path.write_text(prompt + "\n", "utf-8")

        return {
            "prompt": prompt,
            "file": str(path.relative_to(project_dir)),
            "path": str(path.relative_to(project_dir)),
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
        }
