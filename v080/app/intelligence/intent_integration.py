from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

from ..prompt_engine import (
    FINAL_COMMAND_MARKER,
    MODE_COMMENT_PREFIX,
    PromptContext,
    PromptEngine,
)
from .intent_router import IntentSkillRouter


if not hasattr(PromptEngine, "_system1_intent_original_compile"):
    PromptEngine._system1_intent_original_compile = PromptEngine.compile


def _inject_router_section(prompt: str, route: dict) -> str:
    if not route.get("auto_routed"):
        return prompt
    section = (
        "INTENT → SKILL ROUTER\n"
        f"Requested skill: {str(route.get('requested_mode') or '').upper()}\n"
        f"Effective skill: {str(route.get('effective_mode') or '').upper()}\n"
        "Auto-routed: YES\n"
        f"Signals: {', '.join(route.get('signals') or []) or 'none'}\n"
        f"Reason: {route.get('reason') or ''}\n"
        "Execution authority: use the EFFECTIVE skill. The complete operator prompt remains mandatory."
    )
    marker = f"\n\n{FINAL_COMMAND_MARKER}\n"
    if marker in prompt:
        return prompt.replace(marker, f"\n\n{section}{marker}", 1)
    return f"{prompt}\n\n{section}"


def routed_compile(self: PromptEngine, context: PromptContext, project_dir: Path) -> dict:
    original = self._system1_intent_original_compile
    if str(context.stage or "").lower() != "environment":
        return original(context, project_dir)

    requested_mode = self._mode_from_comments(context.comments, context.generation_mode)
    operator_comments = self._operator_comments(context.comments)
    route = IntentSkillRouter.route(requested_mode, operator_comments)

    routed_comments = list(context.comments)
    if route["auto_routed"]:
        routed_comments = [
            item for item in routed_comments
            if not str(item or "").strip().lower().startswith(MODE_COMMENT_PREFIX.lower())
        ]
        routed_comments.append(f"{MODE_COMMENT_PREFIX}{route['effective_mode']}")

    routed_context = replace(
        context,
        comments=routed_comments,
        generation_mode=route["effective_mode"],
    )
    result = original(routed_context, project_dir)

    prompt = _inject_router_section(str(result.get("prompt") or ""), route)
    if prompt != result.get("prompt"):
        result["prompt"] = prompt
        result["prompt_sha256"] = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        result["prompt_length"] = len(prompt)
        path = project_dir / str(result["path"])
        path.write_text(prompt + "\n", "utf-8")

    result["requested_generation_mode"] = route["requested_mode"]
    result["effective_generation_mode"] = route["effective_mode"]
    result["generation_mode"] = route["effective_mode"]
    result["intent_router"] = route
    return result


PromptEngine.compile = routed_compile
