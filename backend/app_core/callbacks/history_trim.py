"""History trim callback — prevents unbounded memory growth.

The agent's _history list grows with every task but is never trimmed (only
fully reset via reset_history).  This callback caps the history to a maximum
number of entries at the end of each run, keeping the most recent messages.
"""

import logging
from typing import Any, Dict, List

from agent.callbacks.base import AsyncCallbackHandler

logger = logging.getLogger(__name__)

DEFAULT_MAX_HISTORY = 50


class HistoryTrimCallback(AsyncCallbackHandler):
    """Trims conversation history to a bounded size after each run."""

    def __init__(
        self,
        history: list[dict],
        max_entries: int = DEFAULT_MAX_HISTORY,
    ):
        self._history = history
        self.max_entries = max_entries

    async def on_run_end(
        self,
        kwargs: Dict[str, Any],
        old_items: List[Dict[str, Any]],
        new_items: List[Dict[str, Any]],
    ) -> None:
        if len(self._history) > self.max_entries:
            trimmed = len(self._history) - self.max_entries
            del self._history[: trimmed]
            logger.info(
                f"History trimmed: removed {trimmed} oldest entries, "
                f"{len(self._history)} remaining"
            )
