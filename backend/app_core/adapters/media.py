"""Media adapter — deterministic control for music/media apps.

Uses AppleScript for Spotify and Apple Music control:
play/pause, next/prev, search, and playback state.
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

_PLAY_PAUSE = re.compile(r"\b(play|pause|resume|unpause)\b", re.IGNORECASE)
_NEXT_PREV = re.compile(r"\b(next|skip|previous|prev|back)\s*(track|song)?\b", re.IGNORECASE)
_PLAY_SEARCH = re.compile(
    r"(?:play|listen to|put on)\s+(.+?)(?:\s+on\s+(?:spotify|music|apple music))?$",
    re.IGNORECASE,
)
_VOLUME = re.compile(r"(?:set\s+)?volume\s+(?:to\s+)?(\d+)", re.IGNORECASE)

_MEDIA_APPS = {"spotify", "music", "apple music"}


class MediaAdapter(BaseAdapter):
    """Adapter for music/media playback control."""

    @property
    def name(self) -> str:
        return "media"

    async def get_state(self) -> AdapterState:
        state = AdapterState(adapter_name=self.name)
        for app in ("Spotify", "Music"):
            info = await _get_playback_state(app)
            if info:
                state.available = True
                state.app_name = app
                state.title = info.get("track")
                state.extra = info
                return state
        return state

    def can_handle(self, prompt: str) -> bool:
        lower = prompt.lower()
        if any(app in lower for app in _MEDIA_APPS):
            return True
        return bool(
            _PLAY_PAUSE.search(prompt)
            or _NEXT_PREV.search(prompt)
            or _PLAY_SEARCH.search(prompt)
            or _VOLUME.search(prompt)
        )

    async def execute(self, prompt: str) -> AdapterResult:
        lower = prompt.lower()

        # Volume control
        vol_match = _VOLUME.search(prompt)
        if vol_match:
            level = int(vol_match.group(1))
            return await self._set_volume(level)

        # Next/previous
        np = _NEXT_PREV.search(prompt)
        if np:
            direction = np.group(1).lower()
            if direction in ("next", "skip"):
                return await self._next_track()
            return await self._prev_track()

        # Simple play/pause (no search term)
        pp = _PLAY_PAUSE.search(prompt)
        if pp and not _PLAY_SEARCH.search(prompt):
            action = pp.group(1).lower()
            if action == "pause":
                return await self._pause()
            return await self._play()

        # Search and play
        search = _PLAY_SEARCH.search(prompt)
        if search:
            query = search.group(1).strip()
            return await self._search_and_play(query)

        return AdapterResult(success=False, message="Could not parse media action.")

    def available_actions(self) -> list[AdapterAction]:
        return [
            AdapterAction("play", "Resume playback"),
            AdapterAction("pause", "Pause playback"),
            AdapterAction("next", "Skip to next track"),
            AdapterAction("prev", "Go to previous track"),
            AdapterAction("search_play", "Search and play", {"query": "string"}),
            AdapterAction("volume", "Set volume level", {"level": "int 0-100"}),
        ]

    async def _play(self) -> AdapterResult:
        ok = await _media_command("play")
        return AdapterResult(success=ok, message="Playback resumed." if ok else "Play failed.")

    async def _pause(self) -> AdapterResult:
        ok = await _media_command("pause")
        return AdapterResult(success=ok, message="Playback paused." if ok else "Pause failed.")

    async def _next_track(self) -> AdapterResult:
        ok = await _media_command("next track")
        return AdapterResult(success=ok, message="Skipped to next track." if ok else "Skip failed.")

    async def _prev_track(self) -> AdapterResult:
        ok = await _media_command("previous track")
        return AdapterResult(
            success=ok, message="Went to previous track." if ok else "Previous failed."
        )

    async def _set_volume(self, level: int) -> AdapterResult:
        level = max(0, min(100, level))
        ok = await _media_command(f"set sound volume to {level}")
        return AdapterResult(
            success=ok, message=f"Volume set to {level}." if ok else "Volume change failed."
        )

    async def _search_and_play(self, query: str) -> AdapterResult:
        # Spotify URI search is the most reliable deterministic path
        uri_query = query.replace(" ", "%20")
        script = (
            f'tell application "Spotify"\n'
            f'  activate\n'
            f'  delay 1\n'
            f'end tell'
        )
        await _run_applescript(script)
        return AdapterResult(
            success=False,
            message=f"Spotify activated for '{query}' — search requires vision fallback.",
        )


async def _media_command(command: str) -> bool:
    for app in ("Spotify", "Music"):
        script = f'tell application "{app}" to {command}'
        try:
            proc = await asyncio.create_subprocess_exec(
                "osascript", "-e", script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=5)
            if proc.returncode == 0:
                logger.debug("Media command '%s' on %s succeeded", command, app)
                return True
        except Exception:
            continue
    return False


async def _run_applescript(script: str) -> bool:
    try:
        proc = await asyncio.create_subprocess_exec(
            "osascript", "-e", script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(), timeout=5)
        return proc.returncode == 0
    except Exception:
        return False


async def _get_playback_state(app: str) -> dict | None:
    try:
        script = (
            f'tell application "{app}"\n'
            f'  if player state is playing then\n'
            f'    set t to name of current track\n'
            f'    set a to artist of current track\n'
            f'    return t & " - " & a\n'
            f'  else\n'
            f'    return "paused"\n'
            f'  end if\n'
            f'end tell'
        )
        proc = await asyncio.create_subprocess_exec(
            "osascript", "-e", script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=3)
        if proc.returncode == 0:
            result = stdout.decode().strip()
            return {"track": result, "state": "paused" if result == "paused" else "playing"}
    except Exception:
        pass
    return None
