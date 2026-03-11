"""Parse vision model output into executable actions.

Supports UI-TARS and Qwen2.5-VL output formats.

UI-TARS format:
    Thought: I need to click the search bar.
    Action: click(start_box='<|box_start|>(500,234)<|box_end|>')

Qwen2.5-VL format:
    Action: click(x=500, y=234)
    or similar structured output depending on prompting.

Coordinates from UI-TARS are normalized to 0-1000 range and must be
converted to absolute pixel coordinates.
"""

import re
import logging
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class Action:
    """A parsed action to execute."""

    type: str  # click, double_click, right_click, type, hotkey, scroll, drag, wait, done
    x: Optional[int] = None
    y: Optional[int] = None
    x2: Optional[int] = None
    y2: Optional[int] = None
    text: Optional[str] = None
    direction: Optional[str] = None
    thought: Optional[str] = None


# --- UI-TARS patterns ---

_BOX_PATTERN = re.compile(
    r"<\|box_start\|>\((\d+),\s*(\d+)\)<\|box_end\|>"
)

_ACTION_PATTERNS = {
    "click": re.compile(r"click\(start_box='([^']+)'\)"),
    "left_double": re.compile(r"left_double\(start_box='([^']+)'\)"),
    "right_single": re.compile(r"right_single\(start_box='([^']+)'\)"),
    "type": re.compile(r"type\(content='([^']*)'\)"),
    "hotkey": re.compile(r"hotkey\(key='([^']*)'\)"),
    "scroll": re.compile(
        r"scroll\(start_box='([^']+)',\s*direction='([^']*)'\)"
    ),
    "drag": re.compile(
        r"drag\(start_box='([^']+)',\s*end_box='([^']+)'\)"
    ),
    "wait": re.compile(r"wait\(\)"),
}

# --- Generic patterns (works with Qwen and flexible outputs) ---

_GENERIC_CLICK = re.compile(
    r"click\s*\(\s*(?:x\s*=\s*)?(\d+)\s*,\s*(?:y\s*=\s*)?(\d+)\s*\)"
)
_GENERIC_TYPE = re.compile(r"type\s*\(\s*['\"]([^'\"]*)['\"]|content\s*=\s*['\"]([^'\"]*)['\"]")
_GENERIC_HOTKEY = re.compile(r"(?:hotkey|key|press)\s*\(\s*['\"]([^'\"]*)['\"]")


def _extract_box_coords(box_str: str) -> tuple[int, int]:
    """Extract (x, y) from a UI-TARS box string."""
    m = _BOX_PATTERN.search(box_str)
    if m:
        return int(m.group(1)), int(m.group(2))
    raise ValueError(f"Cannot parse box coordinates from: {box_str}")


def _normalized_to_absolute(
    nx: int, ny: int, screen_w: int, screen_h: int
) -> tuple[int, int]:
    """Convert UI-TARS normalized coords (0-1000) to screen pixels."""
    return (
        round(screen_w * nx / 1000),
        round(screen_h * ny / 1000),
    )


def parse(
    model_output: str,
    screen_width: int,
    screen_height: int,
) -> Action:
    """Parse model output into an Action.

    Tries UI-TARS format first, then generic patterns.
    Returns Action with absolute pixel coordinates.
    """
    text = model_output.strip()

    # Extract thought if present
    thought = None
    thought_match = re.search(r"Thought:\s*(.+?)(?:\n|Action:)", text, re.DOTALL)
    if thought_match:
        thought = thought_match.group(1).strip()

    # Look for Action: line
    action_match = re.search(r"Action:\s*(.+)", text, re.DOTALL)
    action_str = action_match.group(1).strip() if action_match else text

    # Check for task completion signals
    lower = action_str.lower()
    if any(kw in lower for kw in ["finished", "completed", "done", "task complete"]):
        return Action(type="done", thought=thought)

    # --- Try UI-TARS patterns ---

    # click
    m = _ACTION_PATTERNS["click"].search(action_str)
    if m:
        nx, ny = _extract_box_coords(m.group(1))
        x, y = _normalized_to_absolute(nx, ny, screen_width, screen_height)
        return Action(type="click", x=x, y=y, thought=thought)

    # double click
    m = _ACTION_PATTERNS["left_double"].search(action_str)
    if m:
        nx, ny = _extract_box_coords(m.group(1))
        x, y = _normalized_to_absolute(nx, ny, screen_width, screen_height)
        return Action(type="double_click", x=x, y=y, thought=thought)

    # right click
    m = _ACTION_PATTERNS["right_single"].search(action_str)
    if m:
        nx, ny = _extract_box_coords(m.group(1))
        x, y = _normalized_to_absolute(nx, ny, screen_width, screen_height)
        return Action(type="right_click", x=x, y=y, thought=thought)

    # type
    m = _ACTION_PATTERNS["type"].search(action_str)
    if m:
        return Action(type="type", text=m.group(1), thought=thought)

    # hotkey
    m = _ACTION_PATTERNS["hotkey"].search(action_str)
    if m:
        return Action(type="hotkey", text=m.group(1), thought=thought)

    # scroll
    m = _ACTION_PATTERNS["scroll"].search(action_str)
    if m:
        nx, ny = _extract_box_coords(m.group(1))
        x, y = _normalized_to_absolute(nx, ny, screen_width, screen_height)
        return Action(type="scroll", x=x, y=y, direction=m.group(2), thought=thought)

    # drag
    m = _ACTION_PATTERNS["drag"].search(action_str)
    if m:
        nx1, ny1 = _extract_box_coords(m.group(1))
        nx2, ny2 = _extract_box_coords(m.group(2))
        x1, y1 = _normalized_to_absolute(nx1, ny1, screen_width, screen_height)
        x2, y2 = _normalized_to_absolute(nx2, ny2, screen_width, screen_height)
        return Action(type="drag", x=x1, y=y1, x2=x2, y2=y2, thought=thought)

    # wait
    m = _ACTION_PATTERNS["wait"].search(action_str)
    if m:
        return Action(type="wait", thought=thought)

    # --- Try generic patterns ---

    m = _GENERIC_CLICK.search(action_str)
    if m:
        nx, ny = int(m.group(1)), int(m.group(2))
        # Heuristic: if coords > 1000, treat as absolute pixels
        if nx > 1000 or ny > 1000:
            return Action(type="click", x=nx, y=ny, thought=thought)
        x, y = _normalized_to_absolute(nx, ny, screen_width, screen_height)
        return Action(type="click", x=x, y=y, thought=thought)

    m = _GENERIC_TYPE.search(action_str)
    if m:
        content = m.group(1) or m.group(2)
        return Action(type="type", text=content, thought=thought)

    m = _GENERIC_HOTKEY.search(action_str)
    if m:
        return Action(type="hotkey", text=m.group(1), thought=thought)

    log.warning("Could not parse action from model output: %s", action_str[:200])
    return Action(type="wait", thought=thought or f"Unparseable: {action_str[:100]}")
