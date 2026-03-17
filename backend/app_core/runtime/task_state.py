"""Run-scoped task state — replaces ad-hoc variable passing in the agent loop.

A single TaskState instance is created per ``run_agent_task()`` call and
carries all mutable context that was previously spread across local
variables, module-level flags, and in-line history manipulation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TaskState:
    """Encapsulates the mutable state of a single agent task execution."""

    original_prompt: str
    effective_prompt: str = ""
    skill_query: str = ""

    # Which execution layer handled (or is handling) the task
    execution_layer: str = "pending"  # macro | skill | vision | error

    # App context populated by the macro fast-path
    current_app: str | None = None
    app_opened_by_macro: bool = False
    remaining_task: str | None = None

    # Skill context
    matched_skill: Any = None
    compiled_skill: Any = None
    skill_score: float = 0.0

    # Run-local conversation fed to the composed agent loop.
    # Never written back to the persistent _history.
    run_history: list[dict] = field(default_factory=list)
    seed_items: list[dict] = field(default_factory=list)

    # Action tracking
    last_action: dict = field(default_factory=dict)
    action_count: int = 0
    takeover_attempts: int = 0
    human_intervened: bool = False
    spotlight_open: bool = False

    final_outcome: str = "Task complete."

    def history_summary(self) -> dict:
        """Return the concise user entry to persist in _history.

        Excludes verbose model instructions, skill markdown, and seed
        screenshots so persistent history stays small across turns.
        """
        return {"role": "user", "content": self.original_prompt}

    def outcome_summary(self) -> dict:
        """Return the concise assistant entry to persist in _history."""
        return {"role": "assistant", "content": self.final_outcome}

    def to_log_dict(self) -> dict:
        """Compact representation for structured logging / metrics."""
        return {
            "original_prompt": self.original_prompt[:120],
            "execution_layer": self.execution_layer,
            "current_app": self.current_app,
            "matched_skill": self.matched_skill.name if self.matched_skill else None,
            "skill_score": round(self.skill_score, 3) if self.skill_score else None,
            "action_count": self.action_count,
            "takeover_attempts": self.takeover_attempts,
            "human_intervened": self.human_intervened,
            "final_outcome": self.final_outcome[:120],
        }
