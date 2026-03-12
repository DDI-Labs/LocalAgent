"""Parse vision model output into executable actions.

Supports UI-TARS, Qwen2.5-VL, and generic model output formats.
Handles multi-action responses (e.g. "hotkey(super), type('Firefox'), hotkey('Return')").

Coordinates from UI-TARS are normalized to 0-1000 range and must be
converted to absolute pixel coordinates. Generic models also use 0-1000.
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
# Two-point bounding box: <|box_start|>(x1,y1),(x2,y2)<|box_end|>
_BOX_PATTERN_2PT = re.compile(
    r"<\|box_start\|>\((\d+),\s*(\d+)\),\s*\((\d+),\s*(\d+)\)<\|box_end\|>"
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
    r"(?<!double_)(?<!right_)click\s*\(\s*(?:x\s*=\s*)?(\d+)\s*,\s*(?:y\s*=\s*)?(\d+)\s*\)"
)
_GENERIC_DOUBLE_CLICK = re.compile(
    r"double_click\s*\(\s*(?:x\s*=\s*)?(\d+)\s*,\s*(?:y\s*=\s*)?(\d+)\s*\)"
)
_GENERIC_RIGHT_CLICK = re.compile(
    r"right_click\s*\(\s*(?:x\s*=\s*)?(\d+)\s*,\s*(?:y\s*=\s*)?(\d+)\s*\)"
)
_GENERIC_SCROLL = re.compile(
    r"scroll\s*\(\s*(?:x\s*=\s*)?(\d+)\s*,\s*(?:y\s*=\s*)?(\d+)\s*,\s*(?:direction\s*=\s*)?['\"](\w+)['\"]"
)
_GENERIC_DONE = re.compile(r"\bdone\s*\(\s*\)")
_GENERIC_TYPE = re.compile(r"type\s*\(\s*['\"]([^'\"]*)['\"]|content\s*=\s*['\"]([^'\"]*)['\"]")
_GENERIC_HOTKEY = re.compile(r"(?:hotkey|key|press)\s*\(\s*['\"]([^'\"]*)['\"]")

_BRACKET_BOX_4 = re.compile(r"\[(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\]")
_BRACKET_BOX_2 = re.compile(r"\[(\d+),\s*(\d+)\]")

# Matches the start of any action-like function call
_ACTION_CALL = re.compile(
    r"\b(click|left_double|right_single|double_click|right_click"
    r"|type|hotkey|key|press|scroll|drag|wait|done)\s*\("
)


def _extract_box_coords(box_str: str) -> tuple[int, int]:
    """Extract (x, y) from a UI-TARS box string or bracket format.

    Supports:
      <|box_start|>(x1,y1),(x2,y2)<|box_end|> -> center of bounding box
      <|box_start|>(x,y)<|box_end|>            -> (x, y)
      [x1, y1, x2, y2]                        -> center of bounding box
      [x, y]                                   -> (x, y)
    """
    # Two-point bounding box (must check before single-point)
    m = _BOX_PATTERN_2PT.search(box_str)
    if m:
        x1, y1, x2, y2 = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
        return (x1 + x2) // 2, (y1 + y2) // 2
    m = _BOX_PATTERN.search(box_str)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = _BRACKET_BOX_4.search(box_str)
    if m:
        x1, y1, x2, y2 = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
        return (x1 + x2) // 2, (y1 + y2) // 2
    m = _BRACKET_BOX_2.search(box_str)
    if m:
        return int(m.group(1)), int(m.group(2))
    raise ValueError(f"Cannot parse box coordinates from: {box_str}")


def _normalized_to_absolute(
    nx: int, ny: int, screen_w: int, screen_h: int
) -> tuple[int, int]:
    """Convert normalized coords (0-1000) to screen pixels."""
    return (
        round(screen_w * nx / 1000),
        round(screen_h * ny / 1000),
    )


def _resolve_coords(nx: int, ny: int, screen_w: int, screen_h: int) -> tuple[int, int]:
    """Convert coordinates to absolute pixels. Heuristic: >1000 = already absolute."""
    if nx > 1000 or ny > 1000:
        return nx, ny
    return _normalized_to_absolute(nx, ny, screen_w, screen_h)


def _match_action(
    action_str: str,
    screen_width: int,
    screen_height: int,
) -> Optional[Action]:
    """Try to match a single action string against all known patterns.

    Returns an Action or None if nothing matches.
    """
    # --- Check for done ---
    lower = action_str.lower().strip()
    if lower in ("done", "done()", "finished", "completed", "task complete"):
        return Action(type="done")
    m = _GENERIC_DONE.search(action_str)
    if m:
        return Action(type="done")

    # --- UI-TARS patterns (try/except so unknown coords fall through) ---

    m = _ACTION_PATTERNS["click"].search(action_str)
    if m:
        try:
            nx, ny = _extract_box_coords(m.group(1))
            x, y = _normalized_to_absolute(nx, ny, screen_width, screen_height)
            return Action(type="click", x=x, y=y)
        except ValueError:
            log.debug("UI-TARS click coords failed: %s", m.group(1))

    m = _ACTION_PATTERNS["left_double"].search(action_str)
    if m:
        try:
            nx, ny = _extract_box_coords(m.group(1))
            x, y = _normalized_to_absolute(nx, ny, screen_width, screen_height)
            return Action(type="double_click", x=x, y=y)
        except ValueError:
            pass

    m = _ACTION_PATTERNS["right_single"].search(action_str)
    if m:
        try:
            nx, ny = _extract_box_coords(m.group(1))
            x, y = _normalized_to_absolute(nx, ny, screen_width, screen_height)
            return Action(type="right_click", x=x, y=y)
        except ValueError:
            pass

    m = _ACTION_PATTERNS["type"].search(action_str)
    if m:
        return Action(type="type", text=m.group(1))

    m = _ACTION_PATTERNS["hotkey"].search(action_str)
    if m:
        return Action(type="hotkey", text=m.group(1))

    m = _ACTION_PATTERNS["scroll"].search(action_str)
    if m:
        try:
            nx, ny = _extract_box_coords(m.group(1))
            x, y = _normalized_to_absolute(nx, ny, screen_width, screen_height)
            return Action(type="scroll", x=x, y=y, direction=m.group(2))
        except ValueError:
            pass

    m = _ACTION_PATTERNS["drag"].search(action_str)
    if m:
        try:
            nx1, ny1 = _extract_box_coords(m.group(1))
            nx2, ny2 = _extract_box_coords(m.group(2))
            x1, y1 = _normalized_to_absolute(nx1, ny1, screen_width, screen_height)
            x2, y2 = _normalized_to_absolute(nx2, ny2, screen_width, screen_height)
            return Action(type="drag", x=x1, y=y1, x2=x2, y2=y2)
        except ValueError:
            pass

    m = _ACTION_PATTERNS["wait"].search(action_str)
    if m:
        return Action(type="wait")

    # --- Generic patterns ---

    m = _GENERIC_CLICK.search(action_str)
    if m:
        x, y = _resolve_coords(int(m.group(1)), int(m.group(2)), screen_width, screen_height)
        return Action(type="click", x=x, y=y)

    m = _GENERIC_DOUBLE_CLICK.search(action_str)
    if m:
        x, y = _resolve_coords(int(m.group(1)), int(m.group(2)), screen_width, screen_height)
        return Action(type="double_click", x=x, y=y)

    m = _GENERIC_RIGHT_CLICK.search(action_str)
    if m:
        x, y = _resolve_coords(int(m.group(1)), int(m.group(2)), screen_width, screen_height)
        return Action(type="right_click", x=x, y=y)

    m = _GENERIC_SCROLL.search(action_str)
    if m:
        x, y = _resolve_coords(int(m.group(1)), int(m.group(2)), screen_width, screen_height)
        return Action(type="scroll", x=x, y=y, direction=m.group(3))

    m = _GENERIC_TYPE.search(action_str)
    if m:
        return Action(type="type", text=m.group(1) or m.group(2))

    m = _GENERIC_HOTKEY.search(action_str)
    if m:
        return Action(type="hotkey", text=m.group(1))

    # --- Handle bare "type X" / "press Enter" without parens (common in chained output) ---
    m = re.search(r'\btype\s+"([^"]+)"', action_str)
    if m:
        return Action(type="type", text=m.group(1))
    m = re.search(r"\btype\s+'([^']+)'", action_str)
    if m:
        return Action(type="type", text=m.group(1))
    m = re.search(r"\bpress\s+(\w+)", action_str)
    if m:
        return Action(type="hotkey", text=m.group(1))

    return None


def _extract_thought_and_action(text: str) -> tuple[Optional[str], str]:
    """Extract thought and action string from model output."""
    thought = None
    thought_match = re.search(r"Thought:\s*(.+?)(?:\n|Action:)", text, re.DOTALL)
    if thought_match:
        thought = thought_match.group(1).strip()

    action_match = re.search(r"Action:\s*(.+)", text, re.DOTALL)
    action_str = action_match.group(1).strip() if action_match else text

    return thought, action_str


def parse(
    model_output: str,
    screen_width: int,
    screen_height: int,
) -> Action:
    """Parse model output into a single Action (first action if multiple).

    Backward-compatible interface. Use parse_all() for multi-action support.
    """
    actions = parse_all(model_output, screen_width, screen_height)
    return actions[0]


def parse_all(
    model_output: str,
    screen_width: int,
    screen_height: int,
) -> list[Action]:
    """Parse model output into a list of Actions.

    Handles multi-action responses like:
        Action: hotkey(key='super'), type("Firefox"), hotkey(key='Return')
    """
    text = model_output.strip()
    thought, action_str = _extract_thought_and_action(text)

    # Find all action-like function calls in the action string
    calls = list(_ACTION_CALL.finditer(action_str))

    if len(calls) > 1:
        # Multi-action: split into segments and parse each
        actions = []
        for i, call_match in enumerate(calls):
            start = call_match.start()
            end = calls[i + 1].start() if i + 1 < len(calls) else len(action_str)
            segment = action_str[start:end].strip().rstrip(",").strip()

            action = _match_action(segment, screen_width, screen_height)
            if action:
                if not actions:
                    action.thought = thought
                actions.append(action)

        if actions:
            log.info("Parsed %d actions from multi-action response", len(actions))
            return actions

    # Single action (or multi-action parsing failed): try the full string
    action = _match_action(action_str, screen_width, screen_height)
    if action:
        action.thought = thought
        return [action]

    log.warning("Could not parse action from model output: %s", action_str[:200])
    return [Action(type="wait", thought=thought or f"Unparseable: {action_str[:100]}")]
