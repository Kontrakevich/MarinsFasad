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

        sections = [
            ("SYSTEM PROMPT — AUTHORITATIVE", system_prompt),
            ("PROMPT CONTRACT", contract_version),
            ("CURRENT STAGE", context.stage.upper()),
            (
                "APPROVED GEOMETRY INPUT",
                context.approved_geometry_asset
                or (
                    "Reference image 1 supplied by the environment pipeline is the corrected and approved geometry."
                    if is_environment
                    else "No approved geometry asset supplied."
                ),
            ),
            (
                "APPROVED OUTPAINT MASK",
                context.approved_mask_asset
                or (
                    "Reference image 2 supplied by the environment pipeline is the aligned approved binary outpaint mask."
                    if is_environment
                    else "No approved outpaint mask supplied."
                ),
            ),
            ("STAGE SKILL", context.skill or "No stage-specific skill supplied."),
            ("KNOWLEDGE", context.knowledge or "No additional knowledge supplied."),
            (
                "VALIDATED HISTORY",
                "\n".join(f"- {item}" for item in context.history)
                or "No validated history.",
            ),
            (
                "OPERATOR COMMENTS — MANDATORY",
                "\n".join(f"- {item}" for item in context.comments)
                or "No operator comments.",
            ),
            (
                "EXECUTION",
                "Use reference image 1 as the corrected and approved geometry. "
                "Use reference image 2 as the aligned binary edit mask. "
                "Generate the requested environment only in mandatory edit areas. "
                "Return a visibly changed and fully filled environment while preserving approved architecture.",
            ),
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
        }
