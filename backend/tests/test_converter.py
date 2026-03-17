"""Unit tests for the trajectory-to-SKILL.md converter."""

import json
import pytest
from pathlib import Path

from app_core.skills.converter import (
    convert_trajectory_to_skill,
    _discover_turns,
    _extract_from_api_result,
    _extract_from_agent_response,
    _extract_steps,
)
from app_core.skills.skill import Skill


# ---------------------------------------------------------------------------
# Fixtures — synthetic trajectory data
# ---------------------------------------------------------------------------

def _make_api_result(reasoning: str, action: str, element: str | None = None, text: str | None = None) -> dict:
    """Build a synthetic api_result.json payload."""
    args = {"action": action}
    if element:
        args["element_description"] = element
    if text:
        args["text"] = text
    return {
        "result": {
            "choices": [{
                "message": {
                    "content": reasoning,
                    "role": "assistant",
                    "tool_calls": [{
                        "function": {
                            "arguments": json.dumps(args),
                            "name": "computer",
                        },
                        "id": "test_id",
                        "type": "function",
                    }],
                },
            }],
        },
    }


def _make_agent_response(reasoning: str, action_type: str, x: int = 100, y: int = 200) -> dict:
    """Build a synthetic agent_response.json payload."""
    return {
        "response": {
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": reasoning}],
                },
                {
                    "type": "computer_call",
                    "action": {"type": action_type, "x": x, "y": y},
                    "status": "completed",
                },
            ],
        },
    }


def _make_computer_call_result(action_type: str = "click", x: int = 100, y: int = 200) -> dict:
    """Build a synthetic computer_call_result.json payload."""
    return {
        "item": {
            "type": "computer_call",
            "action": {"type": action_type, "x": x, "y": y},
            "status": "completed",
        },
        "result": [{"type": "computer_call_output", "output": {"type": "input_image", "image_url": "[omitted]"}}],
    }


def _write_turn(base: Path, turn_idx: int, files: dict[str, dict]) -> None:
    """Write JSON files into a turn directory."""
    turn_dir = base / f"turn_{turn_idx:03d}"
    turn_dir.mkdir(parents=True, exist_ok=True)
    artifact = 0
    for suffix, data in files.items():
        filename = f"{artifact:04d}_{suffix}.json"
        (turn_dir / filename).write_text(json.dumps(data, indent=2))
        artifact += 1


# ---------------------------------------------------------------------------
# Full conversion with api_result + agent_response
# ---------------------------------------------------------------------------

class TestFullConversion:
    def test_produces_valid_skill_md(self, tmp_path):
        traj = tmp_path / "trajectory"
        traj.mkdir()
        # API turn
        _write_turn(traj, 0, {
            "api_result": _make_api_result(
                "I can see the YouTube bookmark in the bookmarks bar.",
                "click",
                element="youtube bookmark in the bookmarks bar",
            ),
            "agent_response": _make_agent_response(
                "I can see the YouTube bookmark.", "click",
            ),
        })
        # Execution turn
        _write_turn(traj, 1, {
            "computer_call_result": _make_computer_call_result("click", 412, 119),
        })
        # Second API turn
        _write_turn(traj, 2, {
            "api_result": _make_api_result(
                "Now I'll type the search query.",
                "type",
                text="bohemian rhapsody",
            ),
        })

        out = tmp_path / "skills"
        result = convert_trajectory_to_skill(
            trajectory_dir=traj,
            skill_name="test-skill",
            description="Test skill description",
            trigger_phrases=["test trigger"],
            output_dir=out,
        )

        assert result.exists()
        skill = Skill.from_file(result)
        assert skill.name == "test-skill"
        assert len(skill.steps) == 2
        assert skill.steps[0].action_type == "click"
        assert skill.steps[0].element_description == "youtube bookmark in the bookmarks bar"
        assert skill.steps[1].action_type == "type"
        assert skill.steps[1].text_content == "bohemian rhapsody"

    def test_trigger_phrases_in_output(self, tmp_path):
        traj = tmp_path / "trajectory"
        traj.mkdir()
        _write_turn(traj, 0, {
            "api_result": _make_api_result("Click button.", "click", element="button"),
        })
        out = tmp_path / "skills"
        result = convert_trajectory_to_skill(
            trajectory_dir=traj,
            skill_name="phrases-test",
            description="Test",
            trigger_phrases=["phrase one", "phrase two"],
            output_dir=out,
        )
        skill = Skill.from_file(result)
        assert skill.trigger_phrases == ["phrase one", "phrase two"]


# ---------------------------------------------------------------------------
# Works when agent_response.json is missing
# ---------------------------------------------------------------------------

class TestMissingAgentResponse:
    def test_api_result_only(self, tmp_path):
        traj = tmp_path / "trajectory"
        traj.mkdir()
        _write_turn(traj, 0, {
            "api_result": _make_api_result(
                "I see a search bar at the top.",
                "click",
                element="search bar at top",
            ),
        })
        out = tmp_path / "skills"
        result = convert_trajectory_to_skill(
            trajectory_dir=traj,
            skill_name="no-agent-resp",
            description="Test",
            trigger_phrases=["test"],
            output_dir=out,
        )
        skill = Skill.from_file(result)
        assert len(skill.steps) == 1
        assert skill.steps[0].element_description == "search bar at top"


# ---------------------------------------------------------------------------
# Falls back to agent_response when api_result is missing
# ---------------------------------------------------------------------------

class TestFallbackToAgentResponse:
    def test_agent_response_only(self, tmp_path):
        traj = tmp_path / "trajectory"
        traj.mkdir()
        _write_turn(traj, 0, {
            "agent_response": _make_agent_response(
                "I'll click the play button to start the song.", "click", 300, 400,
            ),
        })
        out = tmp_path / "skills"
        result = convert_trajectory_to_skill(
            trajectory_dir=traj,
            skill_name="fallback-test",
            description="Test",
            trigger_phrases=["test"],
            output_dir=out,
        )
        skill = Skill.from_file(result)
        assert len(skill.steps) == 1
        assert skill.steps[0].action_type == "click"
        # agent_response doesn't have element_description
        assert skill.steps[0].element_description is None


# ---------------------------------------------------------------------------
# Skips unusable turns without crash
# ---------------------------------------------------------------------------

class TestSkipsUnusableTurns:
    def test_execution_only_turns_skipped(self, tmp_path):
        traj = tmp_path / "trajectory"
        traj.mkdir()
        # Only has computer_call_result — no planning data
        _write_turn(traj, 0, {
            "computer_call_result": _make_computer_call_result(),
        })
        # Has planning data
        _write_turn(traj, 1, {
            "api_result": _make_api_result("Click the button.", "click", element="button"),
        })
        out = tmp_path / "skills"
        result = convert_trajectory_to_skill(
            trajectory_dir=traj,
            skill_name="skip-test",
            description="Test",
            trigger_phrases=["test"],
            output_dir=out,
        )
        skill = Skill.from_file(result)
        assert len(skill.steps) == 1  # only the turn with api_result

    def test_empty_trajectory_raises(self, tmp_path):
        traj = tmp_path / "trajectory"
        traj.mkdir()
        # Only execution data — no planning turns
        _write_turn(traj, 0, {
            "computer_call_result": _make_computer_call_result(),
        })
        with pytest.raises(ValueError, match="No usable steps"):
            convert_trajectory_to_skill(
                trajectory_dir=traj,
                skill_name="empty",
                description="Test",
                trigger_phrases=["test"],
                output_dir=tmp_path / "skills",
            )


# ---------------------------------------------------------------------------
# Extracts element_description correctly
# ---------------------------------------------------------------------------

class TestElementDescription:
    def test_element_from_api_result(self, tmp_path):
        api_result = _make_api_result(
            "I see the submit button at the bottom.",
            "click",
            element="submit button at the bottom of the form",
        )
        result = _extract_from_api_result(_write_json(tmp_path, "api_result", api_result))
        assert result is not None
        assert result["element_description"] == "submit button at the bottom of the form"

    def test_no_element_in_agent_response(self, tmp_path):
        agent_resp = _make_agent_response("Click the button.", "click")
        result = _extract_from_agent_response(_write_json(tmp_path, "agent_resp", agent_resp))
        assert result is not None
        assert result["element_description"] is None


# ---------------------------------------------------------------------------
# Writes valid markdown output
# ---------------------------------------------------------------------------

class TestOutputFormat:
    def test_output_is_parseable_skill_md(self, tmp_path):
        traj = tmp_path / "trajectory"
        traj.mkdir()
        _write_turn(traj, 0, {
            "api_result": _make_api_result(
                "I see Chrome with a search bar. Let me click it.",
                "click",
                element="search bar in Chrome",
            ),
        })
        _write_turn(traj, 1, {
            "api_result": _make_api_result(
                "Now I'll type the URL.",
                "type",
                text="youtube.com",
            ),
        })
        out = tmp_path / "skills"
        md_path = convert_trajectory_to_skill(
            trajectory_dir=traj,
            skill_name="format-test",
            description="Test output format",
            trigger_phrases=["test format"],
            output_dir=out,
            approval_required=True,
        )
        # Must be parseable
        skill = Skill.from_file(md_path)
        assert skill.approval_required is True
        assert skill.description == "Test output format"
        assert len(skill.steps) == 2

    def test_nonexistent_trajectory_raises(self):
        with pytest.raises(FileNotFoundError):
            convert_trajectory_to_skill(
                trajectory_dir=Path("/does/not/exist"),
                skill_name="bad",
                description="Test",
                trigger_phrases=["test"],
                output_dir=Path("/tmp"),
            )


# ---------------------------------------------------------------------------
# Test against real demonstration data (if available)
# ---------------------------------------------------------------------------

REAL_DEMO_DIR = Path(__file__).parent.parent / "demonstrations" / "2026-03-16_mlx_claudesonnet4_042356_11dc"


@pytest.mark.skipif(not REAL_DEMO_DIR.exists(), reason="Real demo data not available")
class TestRealDemoData:
    def test_convert_real_demo(self, tmp_path):
        out = tmp_path / "skills"
        result = convert_trajectory_to_skill(
            trajectory_dir=REAL_DEMO_DIR,
            skill_name="real-demo",
            description="Converted from real demonstration",
            trigger_phrases=["play song on youtube", "open chrome and youtube"],
            output_dir=out,
        )
        assert result.exists()
        skill = Skill.from_file(result)
        assert skill.name == "real-demo"
        assert len(skill.steps) > 0
        # At least the first step should have element_description from the planning model
        has_element = any(s.element_description for s in skill.steps)
        assert has_element, "Expected at least one step with element_description from api_result.json"

    def test_discover_turns_real(self):
        turns = _discover_turns(REAL_DEMO_DIR)
        assert len(turns) > 0
        # Should find both api_result and computer_call_result turns
        has_api = any(t["api_result"] for t in turns)
        has_exec = any(t["computer_call_result"] for t in turns)
        assert has_api, "Expected api_result.json in at least one turn"
        assert has_exec, "Expected computer_call_result.json in at least one turn"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _write_json(base: Path, name: str, data: dict) -> Path:
    """Write a JSON file and return its path."""
    path = base / f"{name}.json"
    path.write_text(json.dumps(data, indent=2))
    return path
