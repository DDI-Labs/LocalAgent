"""Compile parsed Skills into structured runtime plans.

A CompiledSkill replaces raw-markdown prompt injection with typed step
objects the executor can process deterministically where possible.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app_core.skills.skill import Skill, SkillStep

logger = logging.getLogger(__name__)


@dataclass
class CompiledStep:
    """One executable step in a compiled skill plan."""

    index: int
    action_type: str  # click, type, keypress, scroll, wait, screenshot
    description: str

    # Action parameters resolved from the skill step
    params: dict[str, Any] = field(default_factory=dict)

    # Semantic anchor used by the VLM to locate the click target
    element: str | None = None

    # Describes what the screen should look like before this step
    precondition: str | None = None

    # Hint text for the planner if this step fails
    fallback_hint: str | None = None

    @property
    def is_deterministic(self) -> bool:
        """True when this step can execute without visual grounding."""
        return self.action_type in ("type", "keypress", "wait", "screenshot")


@dataclass
class CompiledSkill:
    """A skill compiled into an executable plan."""

    name: str
    description: str
    steps: list[CompiledStep]
    variables: dict[str, str] = field(default_factory=dict)
    source: Skill | None = None

    def deterministic_prefix(self) -> list[CompiledStep]:
        """Return the longest prefix of steps that can run without vision."""
        prefix = []
        for step in self.steps:
            if step.is_deterministic:
                prefix.append(step)
            else:
                break
        return prefix

    def compact_summary(self) -> str:
        """Token-efficient summary for planner context."""
        lines = [f"Skill: {self.name}", f"Goal: {self.description}", "Steps:"]
        for step in self.steps:
            parts = [f"{step.index}. [{step.action_type}]"]
            if step.element:
                parts.append(step.element)
            elif step.params.get("text"):
                parts.append(f'type "{step.params["text"]}"')
            elif step.params.get("keys"):
                parts.append(f'press {" + ".join(step.params["keys"])}')
            else:
                parts.append(step.description)
            lines.append(" ".join(parts))
        return "\n".join(lines)


def compile_skill(skill: Skill) -> CompiledSkill:
    """Transform a parsed Skill into a CompiledSkill.

    Maps each SkillStep into a CompiledStep with typed parameters
    extracted from the step fields.
    """
    compiled_steps = []
    for step in skill.steps:
        params = _build_params(step)
        compiled_steps.append(
            CompiledStep(
                index=step.index,
                action_type=step.action_type,
                description=step.description,
                params=params,
                element=step.element_description,
                precondition=step.context,
                fallback_hint=step.intent,
            )
        )

    compiled = CompiledSkill(
        name=skill.name,
        description=skill.description,
        steps=compiled_steps,
        source=skill,
    )
    logger.debug(
        "Compiled skill '%s': %d steps (%d deterministic)",
        skill.name, len(compiled_steps),
        len(compiled.deterministic_prefix()),
    )
    return compiled


def _build_params(step: SkillStep) -> dict[str, Any]:
    """Extract typed action parameters from a SkillStep."""
    params: dict[str, Any] = {}

    if step.action_type == "type" and step.text_content:
        params["text"] = step.text_content

    elif step.action_type == "keypress" and step.element_description:
        # Teach-mode stores keys in element_description as
        # "Keyboard shortcut Return" or "Keyboard shortcut cmd + space"
        raw = step.element_description
        if raw.startswith("Keyboard shortcut "):
            raw = raw[len("Keyboard shortcut "):]
        params["keys"] = [k.strip() for k in raw.split("+")]

    elif step.action_type == "click" and step.element_description:
        # Teach-mode stores "Screen position (100, 200)" — extract coords
        import re
        coord_match = re.search(r"\((\d+),\s*(\d+)\)", step.element_description or "")
        if coord_match:
            params["x"] = int(coord_match.group(1))
            params["y"] = int(coord_match.group(2))

    return params
