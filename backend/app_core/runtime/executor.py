"""Deterministic executor — runs macro, adapter, and compiled-skill actions.

Handles execution for tasks that don't need the full vision/planner loop.
If execution cannot complete deterministically, returns the remaining work
for the vision fallback.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from computer import Computer

from app_core.runtime.task_state import TaskState
from app_core.runtime.intent_router import RouteResult
from app_core.skills.compiler import CompiledSkill
from app_core.skills.executor import SkillExecutor

logger = logging.getLogger(__name__)

StatusCallback = Callable[..., None]


@dataclass
class ExecutionOutcome:
    """Result from the deterministic executor."""

    fully_completed: bool = False
    final_outcome: str = ""
    remaining_steps_summary: str | None = None
    steps_completed: int = 0
    steps_remaining: int = 0


class DeterministicExecutor:
    """Execute deterministic actions from compiled skills.

    Returns partial results when non-deterministic steps are encountered
    so the caller can hand off to the vision fallback.
    """

    def __init__(self, computer: "Computer"):
        self._computer = computer
        self._skill_executor = SkillExecutor(computer)

    async def execute_skill(
        self,
        compiled: CompiledSkill,
        state: TaskState,
        broadcast: StatusCallback | None = None,
    ) -> ExecutionOutcome:
        """Run as many compiled steps as possible deterministically."""
        def _send(status: str, msg: str, **extra):
            if broadcast:
                broadcast(status, msg, **extra)

        result = await self._skill_executor.execute(compiled)

        for step in result.completed_steps:
            _send("action", f"[{step.action_type}] {step.description}")

        outcome = ExecutionOutcome(
            fully_completed=result.fully_completed,
            steps_completed=len(result.completed_steps),
            steps_remaining=len(result.remaining_steps),
        )

        if result.fully_completed:
            outcome.final_outcome = f"Skill '{compiled.name}' completed ({len(result.completed_steps)} steps)."
        elif result.remaining_steps:
            remaining_desc = "; ".join(
                f"[{s.action_type}] {s.description}" for s in result.remaining_steps[:3]
            )
            outcome.remaining_steps_summary = remaining_desc
            outcome.final_outcome = (
                f"Skill '{compiled.name}': completed {len(result.completed_steps)} deterministic steps, "
                f"{len(result.remaining_steps)} remaining for vision."
            )

        return outcome
