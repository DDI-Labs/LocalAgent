"""Browser adapter — structured interaction with the frontmost browser.

Uses AppleScript to query and control Safari/Chrome without screenshots.
Provides URL, title, navigation, and search actions.
"""

from __future__ import annotations

import asyncio
import logging
import re
import shlex

from app_core.adapters.base import (
    AdapterAction,
    AdapterResult,
    AdapterState,
    BaseAdapter,
)

logger = logging.getLogger(__name__)

_URL_PATTERN = re.compile(
    r"(?:go to|open|navigate to|visit|browse to)\s+(https?://\S+|[\w.-]+\.\w{2,}(?:/\S*)?)",
    re.IGNORECASE,
)
_SEARCH_PATTERN = re.compile(
    r"(?:search|google|look up|find)\s+(?:for\s+)?(.+?)(?:\s+on\s+(?:google|the web|the internet))?$",
    re.IGNORECASE,
)

_SUPPORTED_BROWSERS = {"safari", "google chrome", "chrome", "arc", "firefox"}


class BrowserAdapter(BaseAdapter):
    """Adapter for browser navigation and search."""

    @property
    def name(self) -> str:
        return "browser"

    async def get_state(self) -> AdapterState:
        """Get current browser URL and title via AppleScript."""
        state = AdapterState(adapter_name=self.name)
        for browser in ("Google Chrome", "Safari"):
            info = await _get_browser_info(browser)
            if info:
                state.available = True
                state.app_name = browser
                state.url = info.get("url")
                state.title = info.get("title")
                return state
        return state

    def can_handle(self, prompt: str) -> bool:
        return bool(_URL_PATTERN.search(prompt) or _SEARCH_PATTERN.search(prompt))

    async def execute(self, prompt: str) -> AdapterResult:
        url_match = _URL_PATTERN.search(prompt)
        if url_match:
            url = url_match.group(1)
            if not url.startswith("http"):
                url = f"https://{url}"
            return await self._navigate(url)

        search_match = _SEARCH_PATTERN.search(prompt)
        if search_match:
            query = search_match.group(1).strip()
            return await self._search(query)

        return AdapterResult(success=False, message="Could not parse browser action.")

    def available_actions(self) -> list[AdapterAction]:
        return [
            AdapterAction("navigate", "Open a URL in the browser", {"url": "string"}),
            AdapterAction("search", "Search the web", {"query": "string"}),
        ]

    async def _navigate(self, url: str) -> AdapterResult:
        safe_url = shlex.quote(url)
        script = f'tell application "Google Chrome" to set URL of active tab of front window to {safe_url}'
        ok = await _run_applescript(script)
        if not ok:
            script = f'tell application "Safari" to set URL of front document to {safe_url}'
            ok = await _run_applescript(script)
        if ok:
            return AdapterResult(success=True, message=f"Navigated to {url}")
        return AdapterResult(success=False, message=f"Failed to navigate to {url}")

    async def _search(self, query: str) -> AdapterResult:
        url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
        return await self._navigate(url)


async def _run_applescript(script: str) -> bool:
    try:
        proc = await asyncio.create_subprocess_exec(
            "osascript", "-e", script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=5)
        if proc.returncode != 0:
            logger.debug("AppleScript failed: %s", stderr.decode().strip())
            return False
        return True
    except Exception as e:
        logger.debug("AppleScript error: %s", e)
        return False


async def _get_browser_info(browser: str) -> dict | None:
    try:
        url_script = f'tell application "{browser}" to get URL of active tab of front window'
        title_script = f'tell application "{browser}" to get title of active tab of front window'
        if browser == "Safari":
            url_script = f'tell application "Safari" to get URL of front document'
            title_script = f'tell application "Safari" to get name of front document'

        url_proc = await asyncio.create_subprocess_exec(
            "osascript", "-e", url_script,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        url_out, _ = await asyncio.wait_for(url_proc.communicate(), timeout=3)

        title_proc = await asyncio.create_subprocess_exec(
            "osascript", "-e", title_script,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        title_out, _ = await asyncio.wait_for(title_proc.communicate(), timeout=3)

        if url_proc.returncode == 0:
            return {
                "url": url_out.decode().strip(),
                "title": title_out.decode().strip() if title_proc.returncode == 0 else "",
            }
    except Exception:
        pass
    return None
