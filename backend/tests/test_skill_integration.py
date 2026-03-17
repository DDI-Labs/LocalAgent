"""Integration tests for the skill system within the agent orchestrator.

These tests exercise the skill matching, prompt injection, and history
isolation logic WITHOUT requiring the full ComputerAgent / Computer Server
stack.  They patch the heavy dependencies (Computer, ComputerAgent) and
test the orchestrator control flow directly.
"""

import asyncio
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from app_core.skills.skill import Skill, SkillStep
from app_core.skills.library import SkillLibrary
from app_core.runtime.task_state import TaskState
from app_core.runtime.prompt_builder import PromptBuilder
from app_core.runtime.metrics import RunMetrics, StepTimer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_skill(name: str, triggers: list[str], approval: bool = False) -> Skill:
    return Skill(
        name=name,
        description=f"Test: {name}",
        trigger_phrases=triggers,
        approval_required=approval,
        steps=[
            SkillStep(index=1, description="Click button", action_type="click",
                      element_description="the button"),
        ],
        raw_markdown=f"# {name}\nTest skill content.",
        file_path=Path("."),
    )


def _lib_with_skills(*skills: Skill) -> SkillLibrary:
    lib = SkillLibrary(skills_dir=Path("/nonexistent"), match_threshold=0.55)
    lib.skills = list(skills)
    return lib


# ---------------------------------------------------------------------------
# Skill matching on effective prompt
# ---------------------------------------------------------------------------

class TestSkillMatching:
    """Verify that the SkillLibrary matches correctly in the patterns
    that run_agent_task would use."""

    def test_direct_prompt_matches(self):
        skill = _make_skill("play-youtube", ["play music on youtube"])
        lib = _lib_with_skills(skill)
        result = lib.match("play music on youtube")
        assert result is not None
        assert result[0].name == "play-youtube"

    def test_macro_fallthrough_prompt_matches(self):
        """After macro opens app, the remaining task should match a skill."""
        skill = _make_skill("search-spotify", [
            "search for a song",
            "play a song",
        ])
        lib = _lib_with_skills(skill)
        # This simulates the rewritten prompt after macro opens Spotify
        fallthrough = (
            "Spotify is already open and in the foreground. "
            "Task: play a song by Queen"
        )
        # The effective prompt includes "play a song" which should match
        result = lib.match("play a song by Queen")
        assert result is not None
        assert result[0].name == "search-spotify"

    def test_no_match_falls_through(self):
        skill = _make_skill("play-youtube", ["play music on youtube"])
        lib = _lib_with_skills(skill)
        result = lib.match("check the weather today")
        assert result is None


# ---------------------------------------------------------------------------
# History isolation
# ---------------------------------------------------------------------------

class TestHistoryIsolation:
    """Verify that skill preamble does not leak into persistent _history."""

    def test_skill_preamble_not_in_stable_history(self):
        """Simulate run_agent_task's flow using TaskState and PromptBuilder."""
        _history: list[dict] = []
        skill = _make_skill("play-youtube", ["play music on youtube"])

        state = TaskState(
            original_prompt="play music on youtube",
            effective_prompt="play music on youtube",
            matched_skill=skill,
        )

        # 1. Build enhanced prompt via PromptBuilder
        enhanced_prompt = PromptBuilder.build(state)
        state.run_history = list(_history)
        state.run_history.append({"role": "user", "content": enhanced_prompt})

        # 2. Agent runs, adds intermediate items to run_history
        state.run_history.append({"role": "assistant", "content": "I see YouTube..."})
        state.run_history.append({"role": "assistant", "content": "Clicking search bar"})
        state.final_outcome = "Task complete."

        # 3. Persist only stable summary
        _history.append(state.history_summary())
        _history.append(state.outcome_summary())

        # The persistent history must NOT contain skill content
        history_text = " ".join(item["content"] for item in _history)
        assert "demonstration" not in history_text
        assert skill.raw_markdown not in history_text
        assert "play-youtube" not in history_text
        assert "MACOS" not in history_text

        # But the run_history should have had the guided prompt
        run_text = " ".join(item["content"] for item in state.run_history)
        assert "demonstration" in run_text

    def test_next_task_has_clean_history(self):
        """Two sequential tasks: first matches a skill, second does not.
        The second task's history should be free of skill content."""
        _history: list[dict] = []
        skill = _make_skill("play-youtube", ["play music on youtube"])

        # --- Task 1: skill-matched ---
        state1 = TaskState(
            original_prompt="play music on youtube",
            effective_prompt="play music on youtube",
            matched_skill=skill,
        )
        state1.final_outcome = "Task complete."
        _history.append(state1.history_summary())
        _history.append(state1.outcome_summary())

        # --- Task 2: no skill match ---
        state2 = TaskState(
            original_prompt="check the weather",
            effective_prompt="check the weather",
        )
        enhanced_2 = PromptBuilder.build(state2)
        run_history_2 = list(_history)
        run_history_2.append({"role": "user", "content": enhanced_2})

        full_text = " ".join(item["content"] for item in run_history_2)
        assert "demonstration" not in full_text
        assert "play-youtube" not in full_text


# ---------------------------------------------------------------------------
# Skill-guided prompt content
# ---------------------------------------------------------------------------

class TestGuidedPrompt:
    """Verify PromptBuilder output when a skill matches."""

    def test_skill_guided_prompt_uses_compact_summary(self):
        skill = _make_skill("play-youtube", ["play music on youtube"])
        state = TaskState(
            original_prompt="play music on youtube",
            effective_prompt="play music on youtube",
            matched_skill=skill,
        )
        prompt = PromptBuilder.build(state)

        assert "demonstration" in prompt
        assert skill.name in prompt
        # Compact summary should include step info
        assert "[click]" in prompt
        assert "the button" in prompt
        assert "play music on youtube" in prompt
        # Raw markdown should NOT be in the prompt (compact summary instead)
        assert skill.raw_markdown not in prompt

    def test_no_skill_normal_prompt(self):
        state = TaskState(
            original_prompt="check the weather",
            effective_prompt="check the weather",
        )
        prompt = PromptBuilder.build(state)

        assert "demonstration" not in prompt
        assert "check the weather" in prompt


# ---------------------------------------------------------------------------
# Preflight approval flow
# ---------------------------------------------------------------------------

class TestPreflightApproval:
    """Test the skill_approval event state machine."""

    def test_approval_event_lifecycle(self):
        """Simulate the approval flow used by _preflight_skill_approval."""
        import app_core.agent as agent_mod

        # Reset state
        agent_mod._skill_approval_event.clear()
        agent_mod._skill_approval_response = None
        agent_mod._skill_approval_active = False

        # Simulate preflight start
        agent_mod._skill_approval_active = True
        assert agent_mod.is_hitl_waiting() is True
        assert agent_mod.get_hitl_state() == {"mode": "skill_approval"}

        # Simulate user approval via submit_hitl_response
        agent_mod.submit_hitl_response({"mode": "skill_approval", "approved": True})
        assert agent_mod._skill_approval_response == {"mode": "skill_approval", "approved": True}
        assert agent_mod._skill_approval_event.is_set()

        # Cleanup
        agent_mod._skill_approval_active = False

    def test_cancel_clears_skill_approval(self):
        import app_core.agent as agent_mod

        agent_mod._skill_approval_active = True
        agent_mod._skill_approval_response = None
        agent_mod._skill_approval_event.clear()

        agent_mod.submit_hitl_response({"mode": "cancel"})
        assert agent_mod._skill_approval_event.is_set()
        assert agent_mod._skill_approval_response["approved"] is False

        # Cleanup
        agent_mod._skill_approval_active = False


# ---------------------------------------------------------------------------
# Converter + library end-to-end
# ---------------------------------------------------------------------------

REAL_DEMO_DIR = Path(__file__).parent.parent / "demonstrations" / "2026-03-16_mlx_claudesonnet4_042356_11dc"


@pytest.mark.skipif(not REAL_DEMO_DIR.exists(), reason="Real demo data not available")
class TestConverterToLibraryFlow:
    """Convert a real demo, load it into the library, and verify matching."""

    def test_converted_skill_matches_prompt(self, tmp_path):
        from app_core.skills.converter import convert_trajectory_to_skill

        skills_dir = tmp_path / "skills"
        convert_trajectory_to_skill(
            trajectory_dir=REAL_DEMO_DIR,
            skill_name="chrome-youtube",
            description="Open Chrome and access YouTube",
            trigger_phrases=[
                "play a song on youtube",
                "access youtube",
                "open chrome and youtube",
            ],
            output_dir=skills_dir,
        )

        lib = SkillLibrary(skills_dir)
        lib.load()
        assert len(lib.skills) == 1

        result = lib.match("play a song on youtube")
        assert result is not None
        assert result[0].name == "chrome-youtube"

        # Should not match unrelated prompts
        assert lib.match("send an email") is None


# ---------------------------------------------------------------------------
# Teach mode
# ---------------------------------------------------------------------------

class TestTeachMode:
    """Test teach mode state machine and build_skill_from_teach_steps."""

    def test_teach_lifecycle(self):
        import app_core.agent as agent_mod

        assert agent_mod.is_teaching() is False

        agent_mod.start_teach("open spotify and play music")
        assert agent_mod.is_teaching() is True
        assert agent_mod.get_teach_prompt() == "open spotify and play music"
        assert agent_mod.get_teach_steps() == []

        agent_mod.cancel_teach()
        assert agent_mod.is_teaching() is False
        assert agent_mod.get_teach_steps() == []
        assert agent_mod.get_teach_prompt() == ""

    def test_build_skill_from_teach_steps(self, tmp_path):
        from app_core.skills.converter import build_skill_from_teach_steps

        steps = [
            {"type": "click", "x": 100, "y": 200},
            {"type": "type", "text": "bohemian rhapsody"},
            {"type": "keypress", "keys": ["Return"]},
            {"type": "click", "x": 300, "y": 400},
        ]

        out = tmp_path / "skills"
        path = build_skill_from_teach_steps(
            steps=steps,
            skill_name="test-teach",
            description="Test teach skill",
            trigger_phrases=["play bohemian rhapsody"],
            output_dir=out,
        )

        assert path.exists()
        skill = Skill.from_file(path)
        assert skill.name == "test-teach"
        assert skill.trigger_phrases == ["play bohemian rhapsody"]
        assert len(skill.steps) == 4
        assert skill.steps[0].action_type == "click"
        assert skill.steps[1].action_type == "type"
        assert skill.steps[1].text_content == "bohemian rhapsody"
        assert skill.steps[2].action_type == "keypress"
        assert skill.steps[3].action_type == "click"

    def test_build_empty_steps_raises(self, tmp_path):
        from app_core.skills.converter import build_skill_from_teach_steps

        with pytest.raises(ValueError, match="No steps recorded"):
            build_skill_from_teach_steps(
                steps=[],
                skill_name="empty",
                description="Test",
                trigger_phrases=["test"],
                output_dir=tmp_path / "skills",
            )

    def test_teach_skill_matches_in_library(self, tmp_path):
        from app_core.skills.converter import build_skill_from_teach_steps

        steps = [
            {"type": "click", "x": 100, "y": 200},
            {"type": "type", "text": "hello"},
        ]

        out = tmp_path / "skills"
        build_skill_from_teach_steps(
            steps=steps,
            skill_name="greet-task",
            description="Say hello",
            trigger_phrases=["say hello", "greet someone"],
            output_dir=out,
        )

        lib = SkillLibrary(out)
        lib.load()
        assert len(lib.skills) == 1

        result = lib.match("say hello")
        assert result is not None
        assert result[0].name == "greet-task"

        assert lib.match("completely unrelated task") is None


# ---------------------------------------------------------------------------
# TaskState unit tests
# ---------------------------------------------------------------------------

class TestTaskState:
    """Verify TaskState fields and summary methods."""

    def test_history_summary_is_concise(self):
        state = TaskState(original_prompt="open spotify and play music")
        s = state.history_summary()
        assert s["role"] == "user"
        assert s["content"] == "open spotify and play music"
        assert "MACOS" not in s["content"]

    def test_outcome_summary(self):
        state = TaskState(original_prompt="test")
        state.final_outcome = "Opened Spotify."
        assert state.outcome_summary() == {"role": "assistant", "content": "Opened Spotify."}

    def test_to_log_dict_includes_all_fields(self):
        skill = _make_skill("test-skill", ["trigger"])
        state = TaskState(
            original_prompt="trigger task",
            execution_layer="skill",
            matched_skill=skill,
            skill_score=0.82,
            action_count=5,
            human_intervened=True,
        )
        d = state.to_log_dict()
        assert d["execution_layer"] == "skill"
        assert d["matched_skill"] == "test-skill"
        assert d["skill_score"] == 0.82
        assert d["action_count"] == 5
        assert d["human_intervened"] is True


# ---------------------------------------------------------------------------
# PromptBuilder unit tests
# ---------------------------------------------------------------------------

class TestPromptBuilder:
    """Verify prompt construction produces correct and compact output."""

    def test_standard_prompt_includes_task(self):
        state = TaskState(original_prompt="check weather", effective_prompt="check weather")
        prompt = PromptBuilder.build(state)
        assert "Task: check weather" in prompt

    def test_skill_guided_prompt_is_compact(self):
        skill = _make_skill("demo-skill", ["do the thing"])
        state = TaskState(
            original_prompt="do the thing",
            effective_prompt="do the thing",
            matched_skill=skill,
        )
        prompt = PromptBuilder.build(state)
        # Should NOT contain full raw markdown
        assert "# demo-skill\nTest skill content." not in prompt
        # Should contain compact summary
        assert "demo-skill" in prompt
        assert "[click]" in prompt
        assert "the button" in prompt

    def test_prompt_smaller_than_raw_markdown_injection(self):
        long_steps = [
            SkillStep(index=i, description=f"Long step {i} description text", action_type="click",
                      element_description=f"Element {i} with lots of detail")
            for i in range(1, 11)
        ]
        skill = Skill(
            name="big-skill",
            description="A skill with many steps",
            trigger_phrases=["big task"],
            approval_required=False,
            steps=long_steps,
            raw_markdown="# big-skill\n" + "\n".join(f"### Step {i}: long text" for i in range(1, 11)) * 5,
            file_path=Path("."),
        )
        state = TaskState(
            original_prompt="big task",
            effective_prompt="big task",
            matched_skill=skill,
        )
        prompt = PromptBuilder.build(state)
        assert len(prompt) < len(skill.raw_markdown) + 500


# ---------------------------------------------------------------------------
# RunMetrics unit tests
# ---------------------------------------------------------------------------

class TestRunMetrics:
    """Verify timing instrumentation."""

    def test_step_timer_accumulates(self):
        t = StepTimer(name="test")
        with t.measure():
            pass
        assert t.call_count == 1
        assert t.total_ms >= 0

        with t.measure():
            pass
        assert t.call_count == 2

    def test_run_metrics_summary(self):
        m = RunMetrics()
        with m.macro.measure():
            pass
        m.step_count = 3
        s = m.summary()
        assert "macro" in s["timings"]
        assert s["steps"] == 3
        assert s["timings"]["macro"]["calls"] == 1
