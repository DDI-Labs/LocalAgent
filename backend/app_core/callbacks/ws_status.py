"""WebSocket status callback — broadcasts detailed agent lifecycle events to the frontend.

Hooks into on_computer_call_start, on_computer_call_end, on_run_start, and
on_run_end to push granular status updates through the existing WebSocket
broadcast mechanism.
"""

import logging
from typing import Any, Callable, Dict, List

from agent.callbacks.base import AsyncCallbackHandler

logger = logging.getLogger(__name__)

StatusCallback = Callable[[str, str], None]


class WebSocketStatusCallback(AsyncCallbackHandler):
    """Broadcasts agent action details to connected WebSocket clients."""

    def __init__(self, broadcast: StatusCallback | None = None):
        self.broadcast = broadcast

    def set_broadcast(self, broadcast: StatusCallback | None) -> None:
        """Update the broadcast function (called per-task from run_agent_task)."""
        self.broadcast = broadcast

    def _send(self, status: str, msg: str) -> None:
        if self.broadcast:
            self.broadcast(status, msg)

    async def on_computer_call_start(self, item: Dict[str, Any]) -> None:
        action = item.get("action", {})
        action_type = action.get("type", "unknown")

        if action_type == "click":
            x, y = action.get("x", "?"), action.get("y", "?")
            btn = action.get("button", "left")
            self._send("action", f"Clicking ({x}, {y}) [{btn}]")
        elif action_type == "type":
            text = action.get("text", "")
            preview = text[:40] + "..." if len(text) > 40 else text
            self._send("action", f"Typing: {preview}")
        elif action_type == "keypress":
            keys = action.get("keys", [])
            self._send("action", f"Pressing: {' + '.join(keys)}")
        elif action_type == "scroll":
            self._send("action", "Scrolling")
        elif action_type == "wait":
            self._send("action", "Waiting for screen update...")
        elif action_type == "screenshot":
            self._send("action", "Taking screenshot")
        else:
            self._send("action", f"Performing: {action_type}")

    async def on_computer_call_end(
        self, item: Dict[str, Any], result: List[Dict[str, Any]]
    ) -> None:
        action = item.get("action", {})
        action_type = action.get("type", "unknown")

        if action_type == "click":
            x, y = action.get("x", "?"), action.get("y", "?")
            self._send("action", f"Click at ({x}, {y}) completed")
        elif action_type == "type":
            self._send("action", "Typing completed")
