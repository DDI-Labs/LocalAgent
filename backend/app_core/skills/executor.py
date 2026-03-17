"""Execute compiled skill steps — deterministic where possible.

The SkillExecutor runs through CompiledSteps in order:
- Deterministic steps (type, keypress, wait) execute directly via Computer
- Vision-dependent steps (click with element description) are deferred to
  the planner/VLM fallback by returning a remaining-steps list
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from computer import Computer

from app_core.skills.compiler import CompiledSkill, CompiledStep

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """Outcome of a skill execution attempt."""

    completed_steps: list[CompiledStep] = field(default_factory=list)
    remaining_steps: list[CompiledStep] = field(default_factory=list)
    fully_completed: bool = False
    error: str | None = None


class SkillExecutor:
    """Execute compiled skill steps against a Computer interface."""

    def __init__(self, computer: "Computer"):
        self._computer = computer

    async def execute(self, skill: CompiledSkill) -> ExecutionResult:
        """Run as many steps as possible deterministically.

        Returns an ExecutionResult indicating which steps completed and
        which remain for the vision fallback.
        """
        result = ExecutionResult()

        for step in skill.steps:
            if step.is_deterministic:
                try:
                    await self._execute_step(step)
                    result.completed_steps.append(step)
                    logger.info(
                        "Skill '%s' step %d executed: [%s] %s",
                        skill.name, step.index, step.action_type, step.description,
                    )
                except Exception as e:
                    logger.warning(
                        "Skill '%s' step %d failed: %s", skill.name, step.index, e
                    )
                    result.remaining_steps.append(step)
                    result.remaining_steps.extend(
                        skill.steps[skill.steps.index(step) + 1:]
                    )
                    result.error = str(e)
                    return result
            else:
                # Non-deterministic — hand off remainder to vision fallback
                result.remaining_steps.append(step)
                result.remaining_steps.extend(
                    skill.steps[skill.steps.index(step) + 1:]
                )
                return result

        result.fully_completed = True
        return result

    async def execute_step(self, step: CompiledStep) -> bool:
        """Execute a single step. Returns True on success."""
        try:
            await self._execute_step(step)
            return True
        except Exception as e:
            logger.warning("Step %d failed: %s", step.index, e)
            return False

    async def _execute_step(self, step: CompiledStep) -> None:
        """Dispatch a deterministic step to the computer interface."""
        iface = self._computer.interface

        if step.action_type == "type":
            text = step.params.get("text", "")
            if text:
                await iface.type_text(text)

        elif step.action_type == "keypress":
            keys = step.params.get("keys", [])
            if len(keys) > 1:
                await iface.hotkey(*keys)
            elif len(keys) == 1:
                await iface.press_key(keys[0])

        elif step.action_type == "wait":
            await asyncio.sleep(1.5)

        elif step.action_type == "screenshot":
            await iface.screenshot()

        elif step.action_type == "click":
            x = step.params.get("x")
            y = step.params.get("y")
            if x is not None and y is not None:
                await iface.left_click(x, y)
            else:
                raise ValueError(
                    f"Click step {step.index} has no coordinates and needs VLM grounding"
                )
        else:
            raise ValueError(f"Unknown action type: {step.action_type}")
