"""Convert trajectory demonstrations into SKILL.md files.

Reads the structured JSON output saved by TrajectorySaverCallback during
training-mode runs and transforms it into the SKILL.md format consumed
by the skill library.

Primary semantic source: ``api_result.json`` (planning model response)
Optional supplement:     ``agent_response.json`` (CUA agent-level wrapper)
Execution metadata:      ``computer_call_result.json`` (resolved coordinates)
"""

import json
import logging
import re
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


def convert_trajectory_to_skill(
    trajectory_dir: Path,
    skill_name: str,
    description: str,
    trigger_phrases: list[str],
    output_dir: Path,
    approval_required: bool = False,
) -> Path:
    """Convert a demonstration trajectory directory into a SKILL.md file.

    Args:
        trajectory_dir: Path to a trajectory directory (e.g. ``demonstrations/2026-03-16_..._11dc/``)
        skill_name: Identifier for the skill (e.g. ``youtube-play-song``)
        description: Human-readable description
        trigger_phrases: Phrases that should activate this skill
        output_dir: Directory to write the SKILL.md into
        approval_required: Whether this skill requires human approval before execution

    Returns:
        Path to the written SKILL.md file.

    Raises:
        FileNotFoundError: If ``trajectory_dir`` does not exist.
        ValueError: If no usable turns are found.
    """
    if not trajectory_dir.is_dir():
        raise FileNotFoundError(f"Trajectory directory not found: {trajectory_dir}")

    turns = _discover_turns(trajectory_dir)
    steps = _extract_steps(turns)

    if not steps:
        raise ValueError(
            f"No usable steps found in trajectory: {trajectory_dir}. "
            "Ensure the trajectory has api_result.json or agent_response.json files."
        )

    markdown = _build_skill_markdown(
        skill_name=skill_name,
        description=description,
        trigger_phrases=trigger_phrases,
        approval_required=approval_required,
        steps=steps,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{skill_name}.md"
    output_path.write_text(markdown, encoding="utf-8")
    logger.info("Wrote skill %s to %s (%d steps)", skill_name, output_path, len(steps))
    return output_path


# ---------------------------------------------------------------------------
# Internal: discover and classify turn directories
# ---------------------------------------------------------------------------

_TURN_DIR_RE = re.compile(r"^turn_(\d+)$")


def _discover_turns(trajectory_dir: Path) -> list[dict]:
    """Walk turn directories and classify each by file presence.

    Returns a list of dicts, one per turn, sorted by turn index:
    ``{"index": int, "path": Path, "api_result": Path|None,
       "agent_response": Path|None, "computer_call_result": Path|None}``
    """
    turns: list[dict] = []
    for entry in sorted(trajectory_dir.iterdir()):
        if not entry.is_dir():
            continue
        m = _TURN_DIR_RE.match(entry.name)
        if not m:
            continue
        turn = {
            "index": int(m.group(1)),
            "path": entry,
            "api_result": None,
            "agent_response": None,
            "computer_call_result": None,
        }
        # Scan files by suffix — don't assume artifact numbering
        for f in entry.iterdir():
            if f.name.endswith("_api_result.json"):
                turn["api_result"] = f
            elif f.name.endswith("_agent_response.json"):
                turn["agent_response"] = f
            elif f.name.endswith("_computer_call_result.json"):
                turn["computer_call_result"] = f
        turns.append(turn)

    return turns


def _extract_steps(turns: list[dict]) -> list[dict]:
    """Build skill steps from turn data.

    A step is produced from each turn that contains planning data
    (``api_result.json`` or ``agent_response.json``).  Execution metadata
    from nearby ``computer_call_result.json`` turns is associated when
    possible.
    """
    steps: list[dict] = []
    step_index = 1

    # Build a lookup of computer_call_result turns for association
    execution_data: dict[int, dict] = {}
    for turn in turns:
        if turn["computer_call_result"]:
            data = _load_json(turn["computer_call_result"])
            if data:
                execution_data[turn["index"]] = data

    for turn in turns:
        # Try primary source: api_result.json
        planning = None
        if turn["api_result"]:
            planning = _extract_from_api_result(turn["api_result"])

        # Fallback: agent_response.json
        if planning is None and turn["agent_response"]:
            planning = _extract_from_agent_response(turn["agent_response"])

        if planning is None:
            continue

        # Try to associate execution data from the next turn
        exec_info = execution_data.get(turn["index"] + 1, {})
        coordinates = _extract_coordinates(exec_info)

        steps.append({
            "index": step_index,
            "reasoning": planning.get("reasoning", ""),
            "action_type": planning.get("action_type", "unknown"),
            "element_description": planning.get("element_description"),
            "text_content": planning.get("text_content"),
            "coordinates": coordinates,
        })
        step_index += 1

    return steps


# ---------------------------------------------------------------------------
# Extract from api_result.json (primary)
# ---------------------------------------------------------------------------

def _extract_from_api_result(path: Path) -> dict | None:
    """Extract reasoning, action type, and element description from api_result.json.

    Expected structure:
    ```json
    {
      "result": {
        "choices": [{
          "message": {
            "content": "reasoning text...",
            "tool_calls": [{
              "function": {
                "arguments": "{\"action\": \"click\", \"element_description\": \"...\", ...}"
              }
            }]
          }
        }]
      }
    }
    ```
    """
    data = _load_json(path)
    if not data:
        return None

    result = data.get("result", {})
    choices = result.get("choices", [])
    if not choices:
        return None

    message = choices[0].get("message", {})
    reasoning = message.get("content", "")

    # Parse tool_calls for semantic action info
    action_type = "unknown"
    element_description = None
    text_content = None

    tool_calls = message.get("tool_calls", [])
    if tool_calls:
        try:
            args_str = tool_calls[0].get("function", {}).get("arguments", "{}")
            args = json.loads(args_str)
            action_type = args.get("action", "unknown")
            element_description = args.get("element_description")
            text_content = args.get("text")
        except (json.JSONDecodeError, KeyError, IndexError):
            logger.debug("Failed to parse tool_call arguments from %s", path)

    if not reasoning and action_type == "unknown":
        return None

    return {
        "reasoning": reasoning,
        "action_type": action_type,
        "element_description": element_description,
        "text_content": text_content,
    }


# ---------------------------------------------------------------------------
# Extract from agent_response.json (fallback)
# ---------------------------------------------------------------------------

def _extract_from_agent_response(path: Path) -> dict | None:
    """Extract from agent_response.json (CUA agent-level wrapper).

    Expected structure:
    ```json
    {
      "response": {
        "output": [
          {"type": "message", "content": [{"type": "output_text", "text": "..."}]},
          {"type": "computer_call", "action": {"type": "click", "x": ..., "y": ...}}
        ]
      }
    }
    ```
    """
    data = _load_json(path)
    if not data:
        return None

    response = data.get("response", {})
    output = response.get("output", [])

    reasoning = ""
    action_type = "unknown"
    element_description = None
    text_content = None

    for item in output:
        item_type = item.get("type", "")

        if item_type == "message":
            for block in item.get("content", []):
                if isinstance(block, dict) and block.get("type") == "output_text":
                    reasoning = block.get("text", "")

        elif item_type == "computer_call":
            action = item.get("action", {})
            action_type = action.get("type", "unknown")
            text_content = action.get("text") or action.get("content")
            # agent_response doesn't have element_description (that's planning-model only)

    if not reasoning and action_type == "unknown":
        return None

    return {
        "reasoning": reasoning,
        "action_type": action_type,
        "element_description": element_description,
        "text_content": text_content,
    }


# ---------------------------------------------------------------------------
# Extract coordinates from computer_call_result.json
# ---------------------------------------------------------------------------

def _extract_coordinates(exec_data: dict) -> dict | None:
    """Pull resolved x/y from computer_call_result data."""
    item = exec_data.get("item", {})
    action = item.get("action", {})
    x, y = action.get("x"), action.get("y")
    if x is not None and y is not None:
        return {"x": x, "y": y}
    return None


# ---------------------------------------------------------------------------
# Build SKILL.md markdown
# ---------------------------------------------------------------------------

def _build_skill_markdown(
    skill_name: str,
    description: str,
    trigger_phrases: list[str],
    approval_required: bool,
    steps: list[dict],
) -> str:
    """Assemble the SKILL.md content from extracted step data."""
    meta = {
        "name": skill_name,
        "description": description,
        "trigger_phrases": trigger_phrases,
        "approval_required": approval_required,
    }
    frontmatter = yaml.dump(meta, default_flow_style=False, sort_keys=False).strip()

    lines = [
        f"---\n{frontmatter}\n---\n",
        f"# {skill_name}\n",
        f"{description}\n",
        "## Steps\n",
    ]

    for step in steps:
        # Derive a short heading from the reasoning
        heading = _summarise_reasoning(step["reasoning"], step["action_type"])
        lines.append(f"### Step {step['index']}: {heading}")

        if step["reasoning"]:
            # Use first sentence as context
            context = step["reasoning"].split(".")[0].strip()
            if context:
                lines.append(f"**Context:** {context}.")

        lines.append(f"**Action:** {step['action_type']}")

        if step.get("element_description"):
            lines.append(f"**Element:** {step['element_description']}")

        if step.get("text_content"):
            lines.append(f"**Text:** {step['text_content']}")

        # Intent derived from reasoning
        if step["reasoning"]:
            intent = _derive_intent(step["reasoning"])
            if intent:
                lines.append(f"**Intent:** {intent}")

        lines.append("")  # blank separator

    return "\n".join(lines)


def _summarise_reasoning(reasoning: str, action_type: str) -> str:
    """Create a short step heading from the model's reasoning text."""
    if not reasoning:
        return f"Perform {action_type}"

    # Take the first meaningful sentence fragment
    first = reasoning.split(".")[0].strip()
    # Trim to ~80 chars
    if len(first) > 80:
        first = first[:77] + "..."
    # Remove "I can see" / "I'll" prefixes for cleaner headings
    for prefix in ("I can see ", "I'll ", "I will ", "Let me ", "Now I'll "):
        if first.startswith(prefix):
            first = first[len(prefix):]
            break
    return first.strip() or f"Perform {action_type}"


def _derive_intent(reasoning: str) -> str:
    """Extract a concise intent from the reasoning.

    Uses the last sentence as it often describes the purpose.
    """
    sentences = [s.strip() for s in reasoning.split(".") if s.strip()]
    if len(sentences) >= 2:
        return sentences[-1]
    return ""


# ---------------------------------------------------------------------------
# Build skill from teach-mode recorded steps
# ---------------------------------------------------------------------------

def build_skill_from_teach_steps(
    steps: list[dict],
    skill_name: str,
    description: str,
    trigger_phrases: list[str],
    output_dir: Path,
    approval_required: bool = False,
) -> Path:
    """Create a SKILL.md directly from teach-mode recorded actions.

    Each step is a dict like ``{"type": "click", "x": 412, "y": 119}``
    or ``{"type": "type", "text": "bohemian rhapsody"}``.  No trajectory
    files or model reasoning involved.

    Returns:
        Path to the written SKILL.md file.
    """
    if not steps:
        raise ValueError("No steps recorded — cannot create an empty skill.")

    meta = {
        "name": skill_name,
        "description": description,
        "trigger_phrases": trigger_phrases,
        "approval_required": approval_required,
    }
    frontmatter = yaml.dump(meta, default_flow_style=False, sort_keys=False).strip()

    lines = [
        f"---\n{frontmatter}\n---\n",
        f"# {skill_name}\n",
        f"{description}\n",
        "## Steps\n",
    ]

    for i, step in enumerate(steps, 1):
        action_type = step.get("type", "unknown")
        heading = _teach_step_heading(step)
        lines.append(f"### Step {i}: {heading}")
        lines.append(f"**Action:** {action_type}")

        if action_type == "click":
            x, y = step.get("x", "?"), step.get("y", "?")
            lines.append(f"**Element:** Screen position ({x}, {y})")
        elif action_type == "type":
            lines.append(f"**Text:** {step.get('text', '')}")
        elif action_type == "keypress":
            keys = step.get("keys", [])
            lines.append(f"**Element:** Keyboard shortcut {' + '.join(keys)}")

        lines.append("")  # blank separator

    markdown = "\n".join(lines)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{skill_name}.md"
    output_path.write_text(markdown, encoding="utf-8")
    logger.info("Wrote teach skill %s to %s (%d steps)", skill_name, output_path, len(steps))
    return output_path


def _teach_step_heading(step: dict) -> str:
    """Generate a heading for a teach-mode step."""
    t = step.get("type", "unknown")
    if t == "click":
        return f"Click at ({step.get('x', '?')}, {step.get('y', '?')})"
    if t == "type":
        text = step.get("text", "")
        preview = text[:40] + "..." if len(text) > 40 else text
        return f'Type "{preview}"'
    if t == "keypress":
        keys = step.get("keys", [])
        return f"Press {' + '.join(keys)}"
    if t == "wait":
        return "Wait for screen update"
    return f"Perform {t}"


# ---------------------------------------------------------------------------
# JSON loading helper
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> dict | None:
    """Load a JSON file, returning None on failure."""
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load %s: %s", path, e)
        return None
