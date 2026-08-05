from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class PromptContext:
    stage: str
    master_prompt: str
    skill: str = ""
    knowledge: str = ""
    history: list[str] = field(default_factory=list)
    comments: list[str] = field(default_factory=list)


class PromptEngine:
    def compile(self, context: PromptContext, project_dir: Path) -> dict:
        sections = [
            ("SYSTEM ROLE", context.master_prompt),
            ("CURRENT STAGE", context.stage.upper()),
            ("SKILL", context.skill or "No stage-specific skill supplied."),
            ("KNOWLEDGE", context.knowledge or "No additional knowledge supplied."),
            ("VALIDATED HISTORY", "\n".join(f"- {x}" for x in context.history) or "No validated history."),
            ("OPERATOR COMMENTS — MANDATORY", "\n".join(f"- {x}" for x in context.comments) or "No operator comments."),
            ("MASTER CANVAS", "Keep exactly the original width, height, aspect ratio and framing. Never crop or downscale production output."),
            ("OUTPAINT", "Treat transparent areas and border-connected black regions as masks. Replace all of them with continuous photorealistic surroundings. No black wedges or empty pixels may remain."),
        ]
        prompt = "\n\n".join(f"{title}\n{body.strip()}" for title, body in sections)
        folder = project_dir / "prompts" / context.stage
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = folder / f"compiled_{stamp}.txt"
        path.write_text(prompt + "\n", "utf-8")
        return {"prompt": prompt, "file": str(path.relative_to(project_dir))}
