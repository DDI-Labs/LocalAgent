"""Unit tests for Skill data model and SKILL.md parser."""

import pytest
from pathlib import Path

from app_core.skills.skill import Skill, SkillStep


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_SKILL_MD = """\
---
name: youtube-play-song
description: Open Chrome, navigate to YouTube, and play a song
trigger_phrases:
  - play a song on youtube
  - open youtube and play
approval_required: false
---
# youtube-play-song

Open Chrome, navigate to YouTube, and play a song.

## Steps

### Step 1: Click YouTube bookmark
**Context:** Chrome is open with bookmarks visible.
**Action:** click
**Element:** youtube bookmark in the bookmarks bar
**Intent:** Navigate to YouTube

### Step 2: Click search bar
**Action:** click
**Element:** Search bar with placeholder text "Search"
**Intent:** Focus the search input

### Step 3: Type the song name
**Action:** type
**Text:** {song_name}
**Intent:** Enter the search query
"""

MINIMAL_SKILL_MD = """\
---
name: simple-task
description: A minimal skill
trigger_phrases:
  - do the thing
approval_required: false
---
# simple-task

## Steps

### Step 1: Click button
**Action:** click
"""

MISSING_OPTIONAL_FIELDS_MD = """\
---
name: partial-skill
description: Some steps have missing optional fields
trigger_phrases:
  - partial task
approval_required: true
---
# partial-skill

## Steps

### Step 1: Do something
**Action:** click

### Step 2: Type text
**Action:** type
**Text:** hello world
"""


# ---------------------------------------------------------------------------
# Parse valid SKILL.md
# ---------------------------------------------------------------------------

class TestParseValid:
    def test_frontmatter_fields(self):
        skill = Skill.from_markdown(VALID_SKILL_MD)
        assert skill.name == "youtube-play-song"
        assert skill.description == "Open Chrome, navigate to YouTube, and play a song"
        assert skill.trigger_phrases == ["play a song on youtube", "open youtube and play"]
        assert skill.approval_required is False

    def test_step_count(self):
        skill = Skill.from_markdown(VALID_SKILL_MD)
        assert len(skill.steps) == 3

    def test_step_fields(self):
        skill = Skill.from_markdown(VALID_SKILL_MD)
        s1 = skill.steps[0]
        assert s1.index == 1
        assert s1.description == "Click YouTube bookmark"
        assert s1.action_type == "click"
        assert s1.element_description == "youtube bookmark in the bookmarks bar"
        assert s1.context == "Chrome is open with bookmarks visible."
        assert s1.intent == "Navigate to YouTube"
        assert s1.text_content is None

    def test_type_step_has_text_content(self):
        skill = Skill.from_markdown(VALID_SKILL_MD)
        s3 = skill.steps[2]
        assert s3.action_type == "type"
        assert s3.text_content == "{song_name}"

    def test_raw_markdown_preserved(self):
        skill = Skill.from_markdown(VALID_SKILL_MD)
        assert skill.raw_markdown == VALID_SKILL_MD

    def test_file_path_default(self):
        skill = Skill.from_markdown(VALID_SKILL_MD)
        assert skill.file_path == Path(".")

    def test_file_path_set(self):
        p = Path("/tmp/test.md")
        skill = Skill.from_markdown(VALID_SKILL_MD, file_path=p)
        assert skill.file_path == p


# ---------------------------------------------------------------------------
# Parse missing optional step fields
# ---------------------------------------------------------------------------

class TestMissingOptionalFields:
    def test_missing_element_defaults_to_none(self):
        skill = Skill.from_markdown(MISSING_OPTIONAL_FIELDS_MD)
        s1 = skill.steps[0]
        assert s1.element_description is None
        assert s1.context is None
        assert s1.text_content is None
        assert s1.intent is None

    def test_type_step_has_text(self):
        skill = Skill.from_markdown(MISSING_OPTIONAL_FIELDS_MD)
        s2 = skill.steps[1]
        assert s2.text_content == "hello world"
        assert s2.element_description is None

    def test_approval_required_true(self):
        skill = Skill.from_markdown(MISSING_OPTIONAL_FIELDS_MD)
        assert skill.approval_required is True


# ---------------------------------------------------------------------------
# Malformed frontmatter
# ---------------------------------------------------------------------------

class TestMalformedFrontmatter:
    def test_no_frontmatter_delimiters(self):
        with pytest.raises(ValueError, match="YAML frontmatter"):
            Skill.from_markdown("# No frontmatter\nJust body text.")

    def test_missing_name_field(self):
        md = "---\ndescription: no name\ntrigger_phrases: []\n---\n# body\n"
        with pytest.raises(ValueError, match="name"):
            Skill.from_markdown(md)

    def test_invalid_yaml(self):
        md = "---\n: invalid: yaml: [[\n---\n# body\n"
        with pytest.raises(ValueError, match="Malformed YAML"):
            Skill.from_markdown(md)

    def test_non_mapping_frontmatter(self):
        md = "---\n- just a list\n- not a mapping\n---\n# body\n"
        with pytest.raises(ValueError, match="mapping"):
            Skill.from_markdown(md)


# ---------------------------------------------------------------------------
# Round-trip: parse → serialize → parse
# ---------------------------------------------------------------------------

class TestRoundTrip:
    def test_round_trip_preserves_values(self):
        original = Skill.from_markdown(VALID_SKILL_MD)
        serialized = original.to_markdown()
        reparsed = Skill.from_markdown(serialized)

        assert reparsed.name == original.name
        assert reparsed.description == original.description
        assert reparsed.trigger_phrases == original.trigger_phrases
        assert reparsed.approval_required == original.approval_required
        assert len(reparsed.steps) == len(original.steps)

        for orig_step, new_step in zip(original.steps, reparsed.steps):
            assert new_step.index == orig_step.index
            assert new_step.description == orig_step.description
            assert new_step.action_type == orig_step.action_type
            assert new_step.element_description == orig_step.element_description
            assert new_step.context == orig_step.context
            assert new_step.text_content == orig_step.text_content
            assert new_step.intent == orig_step.intent


# ---------------------------------------------------------------------------
# Minimal / edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_minimal_skill(self):
        skill = Skill.from_markdown(MINIMAL_SKILL_MD)
        assert skill.name == "simple-task"
        assert len(skill.steps) == 1
        assert skill.steps[0].action_type == "click"

    def test_single_trigger_phrase_as_string(self):
        md = "---\nname: test\ntrigger_phrases: single phrase\n---\n# test\n"
        skill = Skill.from_markdown(md)
        assert skill.trigger_phrases == ["single phrase"]

    def test_empty_steps_section(self):
        md = "---\nname: empty\ntrigger_phrases: []\n---\n# empty\nNo steps here.\n"
        skill = Skill.from_markdown(md)
        assert skill.steps == []
