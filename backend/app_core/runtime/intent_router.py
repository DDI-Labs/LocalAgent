"""Intent router — dispatches tasks to the best execution strategy.

Routes incoming prompts through an ordered chain:
  1. Macro layer (AppleScript fast-path)
  2. Adapter layer (structured app APIs)
  3. Compiled skill engine
  4. Vision/planner fallback

Each strategy returns a ``RouteResult`` indicating whether it handled
the task or wants to pass to the next layer.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from app_core.runtime.task_state import TaskState

logger = logging.getLogger(__name__)


@dataclass
class RouteResult:
    """Outcome of a routing attempt."""

    handled: bool = False
    execution_layer: str = "none"
    final_outcome: str | None = None
    remaining_prompt: str | None = None


class IntentRouter:
    """Ordered chain of routing strategies.

    Each strategy is a callable ``(TaskState) -> RouteResult``.
    The router tries them in order and returns the first one that
    sets ``handled=True`` or falls through to the last (vision).
    """

    def __init__(self) -> None:
        self._strategies: list[tuple[str, Any]] = []

    def register(self, name: str, strategy: Any) -> None:
        """Append a strategy to the chain."""
        self._strategies.append((name, strategy))
        logger.debug("Registered routing strategy: %s", name)

    async def route(self, state: TaskState) -> RouteResult:
        """Try each strategy in order. Return the first match."""
        for name, strategy in self._strategies:
            try:
                result = await strategy(state)
                if result.handled:
                    logger.info(
                        "Route resolved by '%s' layer (outcome=%s)",
                        name, (result.final_outcome or "")[:60],
                    )
                    return result
            except Exception as e:
                logger.warning("Strategy '%s' raised: %s", name, e)
                continue

        return RouteResult(
            handled=False,
            execution_layer="vision",
            remaining_prompt=state.effective_prompt,
        )

    @property
    def strategy_names(self) -> list[str]:
        return [name for name, _ in self._strategies]
