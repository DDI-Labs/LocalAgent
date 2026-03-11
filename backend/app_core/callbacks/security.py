"""Security interception callback for ComputerAgent.

Intercepts agent actions *before* they execute on the machine to prevent:
- Clicks/typing into sensitive applications (Terminal, System Preferences, etc.)
- Actions targeting coordinates outside the visible screen bounds
- Potentially destructive keyboard shortcuts (e.g. Cmd+Q on Finder, Cmd+Shift+Delete)

Uses the on_computer_call_start hook so every action is evaluated before execution.
If a violation is detected the callback raises SecurityBlockedError which the
caller in agent.py catches separately from infrastructure errors.
"""

import logging
from typing import Any, Dict, List, Set

from agent.callbacks.base import AsyncCallbackHandler

logger = logging.getLogger(__name__)


class SecurityBlockedError(RuntimeError):
    """Raised when the security callback blocks an agent action."""


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Apps the agent must never interact with.  Matched case-insensitively against
# the frontmost application name reported by the computer server.
BLOCKED_APPS: Set[str] = {
    "terminal",
    "iterm2",
    "warp",
    "system preferences",
    "system settings",
    "keychain access",
    "disk utility",
    "activity monitor",
    "console",
}

# Keyboard shortcuts that are always blocked regardless of context.
# Each entry is a frozenset of key names (lowercased).
BLOCKED_SHORTCUTS: List[frozenset] = [
    frozenset({"command", "shift", "delete"}),   # Empty Trash
    frozenset({"cmd", "shift", "delete"}),
    frozenset({"command", "option", "escape"}),   # Force Quit
    frozenset({"cmd", "alt", "escape"}),
    frozenset({"command", "option", "shift", "escape"}),  # Force Quit variant
]

# Maximum screen bounds (will be updated dynamically if screen size is known).
# These are generous defaults for a standard MacBook display.
DEFAULT_SCREEN_WIDTH = 3456   # Retina 16" max
DEFAULT_SCREEN_HEIGHT = 2234


class SecurityInterceptionCallback(AsyncCallbackHandler):
    """Evaluates every computer action before execution and blocks unsafe ones."""

    def __init__(
        self,
        blocked_apps: Set[str] | None = None,
        screen_width: int = DEFAULT_SCREEN_WIDTH,
        screen_height: int = DEFAULT_SCREEN_HEIGHT,
    ):
        self.blocked_apps = {a.lower() for a in (blocked_apps or BLOCKED_APPS)}
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.blocked_count = 0

    async def on_computer_call_start(self, item: Dict[str, Any]) -> None:
        """Inspect the action the agent is about to perform.

        Raises SecurityBlockedError to abort the run if the action is unsafe.
        """
        action = item.get("action", {})
        action_type = action.get("type", "")

        # --- 1. Block dangerous keyboard shortcuts ---
        if action_type in ("keypress", "hotkey"):
            keys = {k.lower() for k in action.get("keys", [])}
            for blocked in BLOCKED_SHORTCUTS:
                if blocked.issubset(keys):
                    self.blocked_count += 1
                    msg = f"SECURITY: Blocked dangerous shortcut {keys}"
                    logger.warning(msg)
                    raise SecurityBlockedError(msg)

        # --- 2. Validate click coordinates are within screen bounds ---
        if "x" in action and "y" in action:
            x, y = int(action["x"]), int(action["y"])
            if x < 0 or y < 0 or x > self.screen_width or y > self.screen_height:
                self.blocked_count += 1
                msg = (
                    f"SECURITY: Blocked out-of-bounds action at ({x}, {y}) — "
                    f"screen is {self.screen_width}x{self.screen_height}"
                )
                logger.warning(msg)
                raise SecurityBlockedError(msg)

        # --- 3. Block interactions with sensitive applications ---
        # The computer_call item may include metadata about the current app.
        # We also check the action's "app" or "application" field if present.
        current_app = (
            action.get("app", "")
            or action.get("application", "")
            or item.get("current_application", "")
        ).lower()

        if current_app and current_app in self.blocked_apps:
            self.blocked_count += 1
            msg = f"SECURITY: Blocked action on restricted app '{current_app}'"
            logger.warning(msg)
            raise SecurityBlockedError(msg)

    async def on_run_end(
        self,
        kwargs: Dict[str, Any],
        old_items: List[Dict[str, Any]],
        new_items: List[Dict[str, Any]],
    ) -> None:
        if self.blocked_count > 0:
            logger.info(
                f"Security callback blocked {self.blocked_count} action(s) this run."
            )
            self.blocked_count = 0
