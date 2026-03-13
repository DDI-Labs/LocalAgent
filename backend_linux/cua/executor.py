"""Action execution using xdotool (X11).

All coordinates are relative to the primary monitor. They are converted
to absolute X11 screen coordinates by adding the monitor's offset.
"""

import subprocess
import time
import logging

from cua.screenshot import _get_primary_geometry

log = logging.getLogger(__name__)


def _offset(x: int, y: int) -> tuple[int, int]:
    """Convert primary-monitor-relative coords to absolute X11 coords."""
    x_off, y_off, _, _ = _get_primary_geometry()
    return x + x_off, y + y_off


def _run(cmd: list[str]) -> None:
    """Run a shell command, raising on failure."""
    log.debug("exec: %s", " ".join(cmd))
    subprocess.run(cmd, check=True, capture_output=True)


def minimize_active_window() -> None:
    """Minimize ALL windows to give the agent a clean desktop.

    Uses Super+D (show desktop) to ensure no windows — including the terminal
    running the agent — appear in screenshots and distract the model.
    """
    try:
        _run(["xdotool", "key", "super+d"])
        log.info("Minimized all windows (Super+D — clean desktop)")
        time.sleep(1.5)  # GNOME animation
    except Exception as e:
        log.warning("Could not minimize windows: %s", e)


def click(x: int, y: int) -> None:
    """Move mouse to (x, y) on primary monitor and left-click."""
    ax, ay = _offset(x, y)
    log.info("click(%d, %d) -> absolute(%d, %d)", x, y, ax, ay)
    _run(["xdotool", "mousemove", str(ax), str(ay)])
    _run(["xdotool", "click", "1"])


def double_click(x: int, y: int) -> None:
    """Move mouse to (x, y) on primary monitor and double-click."""
    ax, ay = _offset(x, y)
    log.info("double_click(%d, %d) -> absolute(%d, %d)", x, y, ax, ay)
    _run(["xdotool", "mousemove", str(ax), str(ay)])
    _run(["xdotool", "click", "--repeat", "2", "--delay", "100", "1"])


def right_click(x: int, y: int) -> None:
    """Move mouse to (x, y) on primary monitor and right-click."""
    ax, ay = _offset(x, y)
    log.info("right_click(%d, %d) -> absolute(%d, %d)", x, y, ax, ay)
    _run(["xdotool", "mousemove", str(ax), str(ay)])
    _run(["xdotool", "click", "3"])


def type_text(text: str, delay_ms: int = 50) -> None:
    """Type a string using xdotool.

    Uses --clearmodifiers to avoid interference from held keys.
    """
    log.info("type_text(%r)", text[:50])
    _run(["xdotool", "type", "--clearmodifiers", "--delay", str(delay_ms), text])


_BLOCKED_HOTKEYS = frozenset({
    "ctrl+c", "ctrl+z", "ctrl+d", "ctrl+\\",
    "ctrl+q",  # would quit the terminal emulator
    "alt+f4",  # would close the terminal window
})


def hotkey(keys: str) -> None:
    """Press a key combination, e.g. 'ctrl+a', 'alt+Tab', 'Return'.

    Blocks key combos that would kill the agent process or close its terminal.
    """
    if keys.lower() in _BLOCKED_HOTKEYS:
        log.warning("BLOCKED dangerous hotkey: %s (would kill agent)", keys)
        return
    log.info("hotkey(%s)", keys)
    _run(["xdotool", "key", "--clearmodifiers", keys])
    # Give the UI time to respond — launchers/Activities need longer
    if keys.lower() in ("super", "super_l", "super_r"):
        time.sleep(1.5)
    else:
        time.sleep(0.6)


def scroll(x: int, y: int, direction: str, clicks: int = 3) -> None:
    """Scroll at position (x, y) on primary monitor. Direction: 'up' or 'down'."""
    ax, ay = _offset(x, y)
    log.info("scroll(%d, %d, %s) -> absolute(%d, %d)", x, y, direction, ax, ay)
    _run(["xdotool", "mousemove", str(ax), str(ay)])
    button = "4" if direction == "up" else "5"
    _run(["xdotool", "click", "--repeat", str(clicks), button])


def drag(x1: int, y1: int, x2: int, y2: int) -> None:
    """Drag from (x1, y1) to (x2, y2) on primary monitor."""
    ax1, ay1 = _offset(x1, y1)
    ax2, ay2 = _offset(x2, y2)
    log.info("drag(%d,%d -> %d,%d) -> absolute(%d,%d -> %d,%d)", x1, y1, x2, y2, ax1, ay1, ax2, ay2)
    _run(["xdotool", "mousemove", str(ax1), str(ay1)])
    _run(["xdotool", "mousedown", "1"])
    time.sleep(0.1)
    _run(["xdotool", "mousemove", str(ax2), str(ay2)])
    _run(["xdotool", "mouseup", "1"])


def wait(seconds: float = 1.0) -> None:
    """Pause execution."""
    log.info("wait(%.1fs)", seconds)
    time.sleep(seconds)
