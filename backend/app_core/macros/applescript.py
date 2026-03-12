"""AppleScript automation — app launching and macro actions.

Provides fast-path app control via osascript, bypassing the vision loop
for actions the model struggles with (clicking Play, navigating Finder, etc.).
"""

import asyncio
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


async def run_osascript(script: str) -> tuple[bool, str]:
    """Run an AppleScript snippet and return (success, output/error)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "osascript", "-e", script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5)
        if proc.returncode == 0:
            return True, stdout.decode().strip()
        return False, stderr.decode().strip()
    except Exception as e:
        return False, str(e)


async def _get_frontmost_app() -> str:
    """Return the name of the currently frontmost application."""
    ok, name = await run_osascript(
        'tell application "System Events" to get name of first application process '
        'whose frontmost is true'
    )
    return name.lower().strip() if ok else ""


async def _raise_app_window(name: str) -> None:
    """Force an app's window to the front AND onto the main display.

    Three problems this solves:
    1. `activate` makes the *process* frontmost but may not raise the *window*.
    2. Process name lookup via `tell process "X"` is case-sensitive — we use
       `whose name is` for case-insensitive matching.
    3. On multi-monitor setups, the computer server captures the main display
       only (PIL ImageGrab).  If the app window is on a secondary display,
       the screenshot won't show it.  We move the window to (0, 25) which
       places it on the main display.
    """
    script = (
        'tell application "System Events"\n'
        '  try\n'
        f'    set appProc to first application process whose name is "{name}"\n'
        '    tell appProc\n'
        '      perform action "AXRaise" of window 1\n'
        '      set frontmost to true\n'
        # Move window to main display (top-left, below menu bar).
        # This ensures the computer server's screenshot captures it.
        '      set position of window 1 to {0, 25}\n'
        '    end tell\n'
        '  end try\n'
        'end tell'
    )
    ok, err = await run_osascript(script)
    if ok:
        logger.debug(f"_raise_app_window('{name}'): raised and moved to main display")
    else:
        logger.debug(f"_raise_app_window('{name}') failed: {err}")


async def open_app(name: str) -> bool:
    """Open a macOS app, raise its window, and verify it's visible.

    Three-phase approach:
    1. `activate` — makes the process frontmost.
    2. `AXRaise` + `set frontmost` — ensures the window is actually on top.
    3. Verify via System Events and wait for the window to render.

    Retries up to 3 times with increasing delays because heavy apps
    (Slack, Chrome, etc.) can take several seconds to surface their window.
    """
    # Phase 1: activate the app (reopen first to ensure a window exists)
    await run_osascript(f'tell application "{name}" to reopen')
    ok, err = await run_osascript(f'tell application "{name}" to activate')
    if not ok:
        logger.warning(f"open_app('{name}') failed: {err}")
        return False

    # Phase 2: explicitly raise the window on top of all others
    await _raise_app_window(name)

    # Phase 3: verify frontmost with retries
    target = name.lower().strip()
    for attempt in range(3):
        wait = 1.0 + attempt * 1.0  # 1s, 2s, 3s
        await asyncio.sleep(wait)

        frontmost = await _get_frontmost_app()
        if target in frontmost or frontmost in target:
            logger.info(f"Opened app '{name}' via osascript (verified frontmost)")
            # Settle time for macOS to finish rendering the window.
            await asyncio.sleep(2.0)
            return True

        # Re-activate AND re-raise — the first attempt may have been swallowed
        logger.info(
            f"App '{name}' not yet frontmost (got '{frontmost}'), "
            f"retrying activate+raise (attempt {attempt + 2})"
        )
        await run_osascript(f'tell application "{name}" to activate')
        await _raise_app_window(name)

    # Final check
    frontmost = await _get_frontmost_app()
    if target in frontmost or frontmost in target:
        logger.info(f"Opened app '{name}' via osascript (verified after retries)")
        await asyncio.sleep(2.0)
        return True

    logger.warning(
        f"open_app('{name}') activated but '{frontmost}' is still frontmost"
    )
    return False


# ---------------------------------------------------------------------------
# App-action macros: map (app, action_keyword) → AppleScript commands.
# These let us handle common tasks entirely via osascript, bypassing the
# vision loop for actions the 7B model struggles with (clicking Play, etc.).
# ---------------------------------------------------------------------------
_APP_ACTIONS: dict[str, list[tuple[re.Pattern, str, str]]] = {
    # Each entry: (regex matching the remaining_task, applescript command, human description)
    "spotify": [
        (re.compile(r"^(?:play|resume|start playing|start music|start playback)$", re.I),
         'tell application "Spotify" to play', "Started playback"),
        (re.compile(r"pause|stop", re.I),
         'tell application "Spotify" to pause', "Paused playback"),
        (re.compile(r"next|skip", re.I),
         'tell application "Spotify" to next track', "Skipped to next track"),
        (re.compile(r"prev(?:ious)?|go\s*back", re.I),
         'tell application "Spotify" to previous track', "Went to previous track"),
        (re.compile(r"shuffle", re.I),
         'tell application "Spotify" to set shuffling to (not shuffling)', "Toggled shuffle"),
    ],
    "music": [  # Apple Music
        (re.compile(r"^(?:play|resume|start playing|start music|start playback)$", re.I),
         'tell application "Music" to play', "Started playback"),
        (re.compile(r"pause|stop", re.I),
         'tell application "Music" to pause', "Paused playback"),
        (re.compile(r"next|skip", re.I),
         'tell application "Music" to next track', "Skipped to next track"),
        (re.compile(r"prev(?:ious)?|go\s*back", re.I),
         'tell application "Music" to previous track', "Went to previous track"),
    ],
    "safari": [
        (re.compile(r"go\s+to\s+(.+)", re.I),
         'tell application "Safari" to set URL of front document to "{0}"',
         "Navigated to URL"),
        (re.compile(r"new\s+(?:tab|window)", re.I),
         'tell application "Safari" to make new document', "Opened new tab"),
    ],
    "finder": [
        (re.compile(r"new\s+(?:window|folder)", re.I),
         'tell application "Finder" to make new Finder window', "Opened new Finder window"),
        (re.compile(r"(?:go\s+to\s+)?desktop", re.I),
         'tell application "Finder" to set target of front Finder window to (path to desktop)',
         "Navigated to Desktop"),
        (re.compile(r"(?:go\s+to\s+)?documents", re.I),
         'tell application "Finder" to set target of front Finder window to (path to documents folder)',
         "Navigated to Documents"),
        (re.compile(r"(?:go\s+to\s+)?downloads", re.I),
         'tell application "Finder" to set target of front Finder window to folder "Downloads" of (path to home folder)',
         "Navigated to Downloads"),
    ],
    "notes": [
        (re.compile(r"new\s+note|create\s+(?:a\s+)?note", re.I),
         'tell application "Notes" to make new note at folder "Notes"', "Created new note"),
    ],
    "messages": [
        (re.compile(r"new\s+(?:message|conversation)", re.I),
         'tell application "Messages" to activate', "Opened Messages"),
    ],
    "terminal": [
        (re.compile(r"new\s+(?:window|tab)", re.I),
         'tell application "Terminal" to do script ""', "Opened new Terminal window"),
    ],
    "system preferences": [
        (re.compile(r"display|screen|brightness", re.I),
         'tell application "System Preferences" to reveal pane id "com.apple.preference.displays"',
         "Opened Display settings"),
        (re.compile(r"sound|volume|audio", re.I),
         'tell application "System Preferences" to reveal pane id "com.apple.preference.sound"',
         "Opened Sound settings"),
        (re.compile(r"network|wifi|internet", re.I),
         'tell application "System Preferences" to reveal pane id "com.apple.preference.network"',
         "Opened Network settings"),
    ],
    "system settings": [
        (re.compile(r"display|screen|brightness", re.I),
         'tell application "System Settings" to activate', "Opened System Settings"),
        (re.compile(r"sound|volume|audio", re.I),
         'tell application "System Settings" to activate', "Opened System Settings"),
        (re.compile(r"network|wifi|internet", re.I),
         'tell application "System Settings" to activate', "Opened System Settings"),
    ],
}


async def try_app_action(app_name: str, task: str) -> str | None:
    """Try to handle a task for an app via AppleScript macros.

    Returns a human-readable description on success, or None if no macro matched.
    """
    actions = _APP_ACTIONS.get(app_name.lower())
    if not actions:
        return None
    for pattern, script, description in actions:
        match = pattern.search(task)
        if match:
            captured = match.group(1).strip() if match.groups() else ""
            if captured and "{0}" in script:
                script = script.format(captured)
            if captured and "{0}" in description:
                description = description.format(captured)
            ok, err = await run_osascript(script)
            if ok:
                logger.info(f"App-action macro: {description} ({app_name})")
                return description
            logger.warning(f"App-action macro failed for '{app_name}': {err}")
            return None
    return None
