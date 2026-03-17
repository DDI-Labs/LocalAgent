"""Centralized prompt construction — keeps prompt content measurable and compact.

All prompt text that goes to the planning model is built here so we have
one place to control token budget, measure size, and swap strategies.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app_core.runtime.task_state import TaskState

from app_core.macros.patterns import MACOS_INSTRUCTIONS

logger = logging.getLogger(__name__)


class PromptBuilder:
    """Builds the prompt string that gets appended to run_history."""

    @staticmethod
    def build(state: TaskState) -> str:
        """Return the enhanced prompt for the composed agent loop.

        When a skill is matched, a *compact* summary is prepended instead
        of the full raw markdown.  This keeps the prompt within a
        reasonable token budget while still giving the planner guidance.
        """
        if state.matched_skill:
            return PromptBuilder._build_skill_guided(state)
        return PromptBuilder._build_standard(state)

    @staticmethod
    def _build_standard(state: TaskState) -> str:
        prompt = f"{MACOS_INSTRUCTIONS}\n\nTask: {state.effective_prompt}"
        logger.debug("Standard prompt built (%d chars)", len(prompt))
        return prompt

    @staticmethod
    def _build_skill_guided(state: TaskState) -> str:
        skill = state.matched_skill
        compiled = getattr(state, "compiled_skill", None)
        if compiled is not None:
            summary = compiled.compact_summary()
        else:
            summary = _compact_skill_summary(skill)
        preamble = (
            "You have a demonstration for this task. "
            "Follow these steps, adapting values to the current request.\n\n"
            f"{summary}\n\n"
            f"Now execute: {state.effective_prompt}"
        )
        prompt = f"{MACOS_INSTRUCTIONS}\n\n{preamble}"
        logger.debug(
            "Skill-guided prompt built (%d chars, skill=%s)",
            len(prompt), skill.name,
        )
        return prompt

    @staticmethod
    def history_user_entry(original_prompt: str) -> dict:
        """The concise user message persisted to long-lived _history."""
        return {"role": "user", "content": original_prompt}

    @staticmethod
    def history_assistant_entry(outcome: str) -> dict:
        """The concise assistant message persisted to long-lived _history."""
        return {"role": "assistant", "content": outcome}


def _compact_skill_summary(skill) -> str:
    """Generate a token-efficient skill summary instead of raw markdown.

    Includes only the essential step sequence — no YAML frontmatter, no
    full reasoning text, no raw coordinates.
    """
    lines = [f"Skill: {skill.name}", f"Goal: {skill.description}", "Steps:"]
    for step in skill.steps:
        parts = [f"{step.index}. [{step.action_type}]"]
        if step.element_description:
            parts.append(step.element_description)
        elif step.text_content:
            parts.append(f'type "{step.text_content}"')
        else:
            parts.append(step.description)
        lines.append(" ".join(parts))
    return "\n".join(lines)
