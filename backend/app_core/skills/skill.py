"""Skill data model and SKILL.md parser.

A Skill represents a recorded human demonstration converted into a structured
format.  Each skill has YAML frontmatter (name, trigger phrases, flags) and
an ordered list of semantic steps that guide the agent during execution.
"""

import re
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Self


@dataclass
class SkillStep:
    """One discrete action in a skill trajectory."""

    index: int
    description: str  # Step heading text
    action_type: str  # click, type, keypress, scroll, screenshot, wait
    element_description: str | None = None  # Semantic anchor for VLM grounding
    context: str | None = None  # Expected screen state
    text_content: str | None = None  # For type actions
    intent: str | None = None  # Why this step exists


@dataclass
class Skill:
    """A demonstration-guided skill parsed from a SKILL.md file."""

    name: str
    description: str
    trigger_phrases: list[str]
    approval_required: bool
    steps: list[SkillStep]
    raw_markdown: str  # Full file content for prompt injection
    file_path: Path = field(default_factory=lambda: Path("."))

    @classmethod
    def from_markdown(cls, text: str, file_path: Path | None = None) -> Self:
        """Parse a SKILL.md string into a Skill instance.

        Raises ``ValueError`` for malformed YAML frontmatter.
        Missing optional step fields default to ``None``.
        """
        frontmatter, body = _split_frontmatter(text)
        meta = _parse_frontmatter(frontmatter)

        name = meta.get("name")
        if not name:
            raise ValueError("SKILL.md frontmatter missing required field: name")

        description = meta.get("description", "")
        trigger_phrases = meta.get("trigger_phrases", [])
        if isinstance(trigger_phrases, str):
            trigger_phrases = [trigger_phrases]
        approval_required = bool(meta.get("approval_required", False))

        steps = _parse_steps(body)

        return cls(
            name=name,
            description=description,
            trigger_phrases=trigger_phrases,
            approval_required=approval_required,
            steps=steps,
            raw_markdown=text,
            file_path=file_path or Path("."),
        )

    @classmethod
    def from_file(cls, path: Path) -> Self:
        """Read and parse a SKILL.md file."""
        text = path.read_text(encoding="utf-8")
        return cls.from_markdown(text, file_path=path)

    def to_markdown(self) -> str:
        """Serialize this skill back to SKILL.md format."""
        meta = {
            "name": self.name,
            "description": self.description,
            "trigger_phrases": self.trigger_phrases,
            "approval_required": self.approval_required,
        }
        frontmatter = yaml.dump(meta, default_flow_style=False, sort_keys=False).strip()

        lines = [
            f"---\n{frontmatter}\n---\n",
            f"# {self.name}\n",
            f"{self.description}\n",
            "## Steps\n",
        ]

        for step in self.steps:
            lines.append(f"### Step {step.index}: {step.description}")
            if step.context:
                lines.append(f"**Context:** {step.context}")
            lines.append(f"**Action:** {step.action_type}")
            if step.element_description:
                lines.append(f"**Element:** {step.element_description}")
            if step.text_content:
                lines.append(f"**Text:** {step.text_content}")
            if step.intent:
                lines.append(f"**Intent:** {step.intent}")
            lines.append("")  # blank line between steps

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal parsing helpers
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_STEP_HEADING_RE = re.compile(r"^###\s+Step\s+(\d+):\s*(.+)", re.IGNORECASE)
_FIELD_RE = re.compile(r"^\*\*(\w+):\*\*\s*(.+)")


def _split_frontmatter(text: str) -> tuple[str, str]:
    """Split YAML frontmatter from the markdown body.

    Returns (frontmatter_yaml, body_markdown).
    Raises ValueError if no valid frontmatter delimiters found.
    """
    m = _FRONTMATTER_RE.match(text)
    if not m:
        raise ValueError(
            "SKILL.md must start with YAML frontmatter enclosed in --- delimiters"
        )
    return m.group(1), text[m.end() :]


def _parse_frontmatter(raw: str) -> dict:
    """Parse YAML frontmatter string into a dict.

    Raises ValueError on malformed YAML.
    """
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        raise ValueError(f"Malformed YAML frontmatter: {e}") from e
    if not isinstance(data, dict):
        raise ValueError("YAML frontmatter must be a mapping (key: value pairs)")
    return data


def _parse_steps(body: str) -> list[SkillStep]:
    """Parse ``### Step N: ...`` blocks from the markdown body."""
    steps: list[SkillStep] = []
    current_index: int | None = None
    current_heading = ""
    current_fields: dict[str, str] = {}

    def _flush():
        if current_index is not None:
            steps.append(
                SkillStep(
                    index=current_index,
                    description=current_heading,
                    action_type=current_fields.get("action", "unknown"),
                    element_description=current_fields.get("element"),
                    context=current_fields.get("context"),
                    text_content=current_fields.get("text"),
                    intent=current_fields.get("intent"),
                )
            )

    for line in body.splitlines():
        step_match = _STEP_HEADING_RE.match(line.strip())
        if step_match:
            _flush()
            current_index = int(step_match.group(1))
            current_heading = step_match.group(2).strip()
            current_fields = {}
            continue

        if current_index is not None:
            field_match = _FIELD_RE.match(line.strip())
            if field_match:
                key = field_match.group(1).lower()
                value = field_match.group(2).strip()
                current_fields[key] = value

    _flush()
    return steps
