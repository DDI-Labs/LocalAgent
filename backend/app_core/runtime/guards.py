"""Confidence guards — evaluate observations to decide next action.

Guards check postconditions after action chunks and decide whether to:
- Continue executing deterministically (high confidence)
- Fall back to the vision/planner loop (uncertain)
- Escalate to HITL (needs human)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app_core.runtime.observation import Observation

logger = logging.getLogger(__name__)


class Confidence(Enum):
    HIGH = "high"
    UNCERTAIN = "uncertain"
    STUCK = "stuck"
    NEEDS_HUMAN = "needs_human"


@dataclass
class GuardVerdict:
    """Result of evaluating guards against an observation."""

    confidence: Confidence
    reason: str = ""
    should_replan: bool = False
    should_escalate: bool = False


class ConfidenceGuard:
    """Evaluates observations against configurable thresholds."""

    def __init__(
        self,
        max_repeats: int = 3,
        max_actions_without_progress: int = 8,
    ):
        self._max_repeats = max_repeats
        self._max_actions = max_actions_without_progress
        self._action_count = 0

    def evaluate(self, obs: "Observation") -> GuardVerdict:
        """Check the observation and return a verdict."""
        self._action_count += 1

        # Stuck: same action repeated too many times
        if obs.repeat_count >= self._max_repeats:
            logger.info(
                "Guard: stuck detected — action '%s' repeated %d times",
                obs.last_action_type, obs.repeat_count,
            )
            return GuardVerdict(
                confidence=Confidence.STUCK,
                reason=f"Action '{obs.last_action_type}' repeated {obs.repeat_count} times",
                should_replan=True,
                should_escalate=obs.repeat_count >= self._max_repeats + 2,
            )

        # Last action failed
        if not obs.last_action_succeeded:
            logger.info("Guard: last action failed — suggesting replan")
            return GuardVerdict(
                confidence=Confidence.UNCERTAIN,
                reason="Last action failed",
                should_replan=True,
            )

        # Too many actions without completion
        if self._action_count >= self._max_actions:
            logger.info(
                "Guard: %d actions without completion — suggesting replan",
                self._action_count,
            )
            return GuardVerdict(
                confidence=Confidence.UNCERTAIN,
                reason=f"{self._action_count} actions without progress",
                should_replan=True,
            )

        # Everything looks fine
        return GuardVerdict(confidence=Confidence.HIGH)

    def reset(self) -> None:
        """Reset counters between tasks."""
        self._action_count = 0
