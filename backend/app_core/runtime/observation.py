"""Observation fusion — merges multiple signal sources into a unified view.

Combines screenshot analysis, adapter state, execution feedback, and
task-state history into a single observation that downstream guards
and the planner can consume.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from app_core.adapters.base import BaseAdapter, AdapterState

logger = logging.getLogger(__name__)


@dataclass
class Observation:
    """Fused observation from multiple sources."""

    # The adapter that provided structured state (if any)
    adapter_state: Any = None

    # Frontmost app as detected by macOS state
    frontmost_app: str | None = None
    window_title: str | None = None

    # Recent action outcome
    last_action_type: str | None = None
    last_action_succeeded: bool = True

    # Screenshot available (not the data, just a flag)
    has_screenshot: bool = False

    # Consecutive identical actions (used by stuck detection)
    repeat_count: int = 0

    # Free-form context from adapters
    signals: dict[str, Any] = field(default_factory=dict)


class ObservationFusion:
    """Collects observations from adapters and execution state.

    Call ``observe()`` after each action chunk to build an
    ``Observation`` that guards can evaluate.
    """

    def __init__(self, adapters: list["BaseAdapter"] | None = None):
        self._adapters = adapters or []
        self._last_action: str | None = None
        self._repeat_count = 0

    async def observe(
        self,
        last_action: dict | None = None,
        action_succeeded: bool = True,
    ) -> Observation:
        """Build a fused observation from available sources."""
        obs = Observation()
        obs.last_action_succeeded = action_succeeded

        if last_action:
            action_type = last_action.get("type", "")
            obs.last_action_type = action_type
            if action_type == self._last_action:
                self._repeat_count += 1
            else:
                self._repeat_count = 0
            self._last_action = action_type
            obs.repeat_count = self._repeat_count

        for adapter in self._adapters:
            try:
                state = await adapter.get_state()
                if state.available:
                    obs.adapter_state = state
                    obs.frontmost_app = state.app_name
                    obs.window_title = state.title
                    obs.signals[adapter.name] = {
                        "app": state.app_name,
                        "title": state.title,
                        "extra": state.extra,
                    }
                    break
            except Exception as e:
                logger.debug("Adapter '%s' observation failed: %s", adapter.name, e)

        return obs

    def reset(self) -> None:
        """Reset repeat tracking between tasks."""
        self._last_action = None
        self._repeat_count = 0
