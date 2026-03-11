"""Run-guard callback — prevents runaway agent loops.

Replaces the ad-hoc consecutive-wait counter that was previously inlined in
run_agent_task.  Uses the on_run_continue hook so the agent framework itself
stops the loop cleanly rather than requiring manual break logic.

Two guards:
1. Consecutive wait() detection — if the model emits N wait() actions in a
   row it is stuck and the run is halted.
2. Wall-clock timeout — if a single run exceeds a time limit the run is halted.
"""

import logging
import time
from typing import Any, Dict, List

from agent.callbacks.base import AsyncCallbackHandler

logger = logging.getLogger(__name__)

DEFAULT_MAX_CONSECUTIVE_WAITS = 3
DEFAULT_TIMEOUT_SECONDS = 120  # 2 minutes per run


class RunGuardCallback(AsyncCallbackHandler):
    """Halts the agent run on stuck-loops or wall-clock timeout."""

    def __init__(
        self,
        max_consecutive_waits: int = DEFAULT_MAX_CONSECUTIVE_WAITS,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ):
        self.max_consecutive_waits = max_consecutive_waits
        self.timeout_seconds = timeout_seconds

        # Per-run state
        self._consecutive_waits = 0
        self._run_start_time: float = 0.0
        self.halt_reason: str | None = None

    async def on_run_start(
        self, kwargs: Dict[str, Any], old_items: List[Dict[str, Any]]
    ) -> None:
        self._consecutive_waits = 0
        self._run_start_time = time.monotonic()
        self.halt_reason = None

    async def on_computer_call_end(
        self, item: Dict[str, Any], result: List[Dict[str, Any]]
    ) -> None:
        """Track consecutive wait() actions."""
        action = item.get("action", {})
        if action.get("type") == "wait":
            self._consecutive_waits += 1
        else:
            self._consecutive_waits = 0

    async def on_run_continue(
        self,
        kwargs: Dict[str, Any],
        old_items: List[Dict[str, Any]],
        new_items: List[Dict[str, Any]],
    ) -> bool:
        """Return False to stop the agent loop."""
        # Guard 1: consecutive waits
        if self._consecutive_waits >= self.max_consecutive_waits:
            self.halt_reason = (
                f"Agent stuck: {self._consecutive_waits} consecutive wait() actions"
            )
            logger.warning(self.halt_reason)
            return False

        # Guard 2: wall-clock timeout
        elapsed = time.monotonic() - self._run_start_time
        if elapsed > self.timeout_seconds:
            self.halt_reason = (
                f"Agent timed out after {elapsed:.0f}s "
                f"(limit: {self.timeout_seconds}s)"
            )
            logger.warning(self.halt_reason)
            return False

        return True
