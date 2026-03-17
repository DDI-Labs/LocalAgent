"""Unit tests for SkillLibrary fuzzy matching."""

import pytest
from pathlib import Path

from app_core.skills.skill import Skill
from app_core.skills.library import SkillLibrary, _score_match, _normalise, _token_set


# ---------------------------------------------------------------------------
# Helpers — build skills without touching disk
# ---------------------------------------------------------------------------

def _make_skill(name: str, triggers: list[str], approval: bool = False) -> Skill:
    """Create a Skill object directly (no SKILL.md file needed)."""
    return Skill(
        name=name,
        description=f"Test skill: {name}",
        trigger_phrases=triggers,
        approval_required=approval,
        steps=[],
        raw_markdown=f"# {name}\nTest.",
        file_path=Path("."),
    )


def _lib_with_skills(*skills: Skill) -> SkillLibrary:
    """Build a SkillLibrary pre-populated with the given skills."""
    lib = SkillLibrary(skills_dir=Path("/nonexistent"), match_threshold=0.55)
    lib.skills = list(skills)
    return lib


# ---------------------------------------------------------------------------
# Exact match
# ---------------------------------------------------------------------------

class TestExactMatch:
    def test_exact_trigger_phrase(self):
        skill = _make_skill("play-spotify", ["play a song on spotify"])
        lib = _lib_with_skills(skill)
        result = lib.match("play a song on spotify")
        assert result is not None
        matched, score = result
        assert matched.name == "play-spotify"
        assert score >= 0.55

    def test_exact_match_high_score(self):
        skill = _make_skill("test", ["open the settings page"])
        lib = _lib_with_skills(skill)
        result = lib.match("open the settings page")
        assert result is not None
        _, score = result
        assert score >= 0.75  # exact should be very high


# ---------------------------------------------------------------------------
# Fuzzy match
# ---------------------------------------------------------------------------

class TestFuzzyMatch:
    def test_close_variation(self):
        skill = _make_skill("play-spotify", ["play a song on spotify"])
        lib = _lib_with_skills(skill)
        result = lib.match("play song spotify")
        assert result is not None
        matched, score = result
        assert matched.name == "play-spotify"

    def test_reworded_prompt(self):
        skill = _make_skill("play-youtube", ["play music on youtube"])
        lib = _lib_with_skills(skill)
        result = lib.match("play some music on youtube please")
        assert result is not None
        assert result[0].name == "play-youtube"

    def test_typo_still_matches(self):
        skill = _make_skill("open-mail", ["open the mail app"])
        lib = _lib_with_skills(skill)
        result = lib.match("opne the mail app")
        assert result is not None
        assert result[0].name == "open-mail"


# ---------------------------------------------------------------------------
# Substring match
# ---------------------------------------------------------------------------

class TestSubstringMatch:
    def test_prompt_contains_trigger(self):
        skill = _make_skill("play-spotify", ["play music on spotify"])
        lib = _lib_with_skills(skill)
        result = lib.match("open spotify and play music on spotify right now")
        assert result is not None
        assert result[0].name == "play-spotify"

    def test_trigger_contains_prompt(self):
        skill = _make_skill("search-web", ["search the web for information"])
        lib = _lib_with_skills(skill)
        result = lib.match("search the web")
        assert result is not None
        assert result[0].name == "search-web"


# ---------------------------------------------------------------------------
# Overlapping skills — highest score wins
# ---------------------------------------------------------------------------

class TestOverlappingSkills:
    def test_more_specific_wins(self):
        generic = _make_skill("play-music", ["play music"])
        specific = _make_skill("play-spotify", ["play music on spotify"])
        lib = _lib_with_skills(generic, specific)
        result = lib.match("play music on spotify")
        assert result is not None
        assert result[0].name == "play-spotify"

    def test_multiple_triggers_best_used(self):
        skill = _make_skill("email", [
            "check email",
            "open the email application",
            "read my mail",
        ])
        lib = _lib_with_skills(skill)
        result = lib.match("read my mail")
        assert result is not None
        assert result[0].name == "email"


# ---------------------------------------------------------------------------
# No match / empty library
# ---------------------------------------------------------------------------

class TestNoMatch:
    def test_empty_library_returns_none(self):
        lib = SkillLibrary(Path("/nonexistent"), match_threshold=0.55)
        assert lib.match("anything") is None

    def test_unrelated_prompt_returns_none(self):
        skill = _make_skill("play-spotify", ["play a song on spotify"])
        lib = _lib_with_skills(skill)
        result = lib.match("what is the weather today")
        assert result is None

    def test_below_threshold_returns_none(self):
        skill = _make_skill("play-spotify", ["play a song on spotify"])
        lib = _lib_with_skills(skill)
        # Very high threshold — only an imperfect match should fail
        lib.match_threshold = 0.99
        result = lib.match("play some tunes on spotify app")
        assert result is None


# ---------------------------------------------------------------------------
# Load from directory
# ---------------------------------------------------------------------------

class TestLoadFromDirectory:
    def test_load_nonexistent_dir(self):
        lib = SkillLibrary(Path("/does/not/exist"))
        lib.load()  # should not raise
        assert lib.skills == []

    def test_load_empty_dir(self, tmp_path):
        lib = SkillLibrary(tmp_path)
        lib.load()
        assert lib.skills == []

    def test_load_valid_skill_file(self, tmp_path):
        md = (
            "---\nname: test-skill\ndescription: test\n"
            "trigger_phrases:\n  - do test\napproval_required: false\n"
            "---\n# test-skill\n## Steps\n### Step 1: Click\n**Action:** click\n"
        )
        (tmp_path / "test-skill.md").write_text(md)
        lib = SkillLibrary(tmp_path)
        lib.load()
        assert len(lib.skills) == 1
        assert lib.skills[0].name == "test-skill"

    def test_load_skips_invalid_files(self, tmp_path):
        (tmp_path / "bad.md").write_text("not valid frontmatter")
        (tmp_path / "good.md").write_text(
            "---\nname: good\ntrigger_phrases: []\n---\n# good\n"
        )
        lib = SkillLibrary(tmp_path)
        lib.load()
        assert len(lib.skills) == 1
        assert lib.skills[0].name == "good"

    def test_reload_picks_up_new_files(self, tmp_path):
        lib = SkillLibrary(tmp_path)
        lib.load()
        assert len(lib.skills) == 0

        (tmp_path / "new.md").write_text(
            "---\nname: new\ntrigger_phrases:\n  - new thing\n---\n# new\n"
        )
        lib.reload()
        assert len(lib.skills) == 1


# ---------------------------------------------------------------------------
# Score internals
# ---------------------------------------------------------------------------

class TestScoreInternals:
    def test_normalise_strips_punct(self):
        assert _normalise("Hello, World!") == "hello world"

    def test_token_set(self):
        assert _token_set("play music on spotify") == {"play", "music", "on", "spotify"}

    def test_identical_strings_high_score(self):
        s = "play music on spotify"
        score = _score_match(_normalise(s), _token_set(s), s)
        assert score >= 0.75

    def test_completely_different_low_score(self):
        score = _score_match(
            _normalise("check the weather forecast"),
            _token_set("check the weather forecast"),
            "play music on spotify",
        )
        assert score < 0.55
