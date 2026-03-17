"""macOS state adapter — structured access to OS-level information.

Uses AppleScript and system commands to inspect the frontmost app,
window title, and basic system state without taking screenshots.
"""

from __future__ import annotations

import asyncio
import logging
import re

from app_core.adapters.base import (
    AdapterAction,
    AdapterResult,
    AdapterState,
    BaseAdapter,
)

logger = logging.getLogger(__name__)

_FRONTMOST_PATTERN = re.compile(
    r"(?:what|which)\s+(?:app|application|window)\s+is\s+(?:open|active|focused|in front|frontmost)",
    re.IGNORECASE,
)
_WINDOW_PATTERN = re.compile(
    r"(?:what is the|show me the|get the)\s+(?:window|page)\s+title",
    re.IGNORECASE,
)


class MacOSStateAdapter(BaseAdapter):
    """Adapter for querying macOS desktop state."""

    @property
    def name(self) -> str:
        return "macos_state"

    async def get_state(self) -> AdapterState:
        state = AdapterState(adapter_name=self.name, available=True)
        info = await _get_frontmost_app()
        if info:
            state.app_name = info.get("app")
            state.title = info.get("title")
        return state

    def can_handle(self, prompt: str) -> bool:
        return bool(_FRONTMOST_PATTERN.search(prompt) or _WINDOW_PATTERN.search(prompt))

    async def execute(self, prompt: str) -> AdapterResult:
        info = await _get_frontmost_app()
        if not info:
            return AdapterResult(success=False, message="Could not determine frontmost app.")

        app = info.get("app", "Unknown")
        title = info.get("title", "")
        msg = f"Frontmost app: {app}"
        if title:
            msg += f" — window: {title}"
        return AdapterResult(success=True, message=msg)

    def available_actions(self) -> list[AdapterAction]:
        return [
            AdapterAction("frontmost_app", "Get the currently active application"),
            AdapterAction("window_title", "Get the title of the frontmost window"),
        ]


async def _get_frontmost_app() -> dict | None:
    try:
        app_script = (
            'tell application "System Events" to get name of first application process '
            'whose frontmost is true'
        )
        title_script = (
            'tell application "System Events"\n'
            '  set fp to first application process whose frontmost is true\n'
            '  tell fp\n'
            '    if (count of windows) > 0 then\n'
            '      return name of front window\n'
            '    else\n'
            '      return ""\n'
            '    end if\n'
            '  end tell\n'
            'end tell'
        )
        app_proc = await asyncio.create_subprocess_exec(
            "osascript", "-e", app_script,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        app_out, _ = await asyncio.wait_for(app_proc.communicate(), timeout=3)

        title_proc = await asyncio.create_subprocess_exec(
            "osascript", "-e", title_script,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        title_out, _ = await asyncio.wait_for(title_proc.communicate(), timeout=3)

        if app_proc.returncode == 0:
            return {
                "app": app_out.decode().strip(),
                "title": title_out.decode().strip() if title_proc.returncode == 0 else "",
            }
    except Exception as e:
        logger.debug("Failed to get frontmost app: %s", e)
    return None
