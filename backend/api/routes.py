"""HTTP API endpoints for the LocalAgent backend."""

import asyncio
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from api.websocket import manager
from app_core import agent
from app_core.config import SKILL_LIBRARY_DIR, TRAINING_TRAJECTORY_DIR
from app_core.skills.converter import convert_trajectory_to_skill

router = APIRouter()


class PromptRequest(BaseModel):
    prompt: str


class CreateSkillRequest(BaseModel):
    trajectory_id: str
    name: str
    description: str
    trigger_phrases: list[str]
    approval_required: bool = False


@router.get("/agent/status")
async def agent_status():
    """Return agent readiness and service health."""
    services = await agent.check_services()
    return {
        "ready": agent.is_ready(),
        "busy": agent.is_busy(),
        **services,
    }


@router.post("/agent/run")
async def agent_run(req: PromptRequest):
    """Run a natural language task through the ComputerAgent."""
    if not agent.is_ready():
        return {"result": "error", "msg": "Agent not initialized."}

    if agent.is_busy():
        return {"result": "error", "msg": "Agent is already processing a task."}

    def make_broadcast(status: str, msg: str):
        asyncio.ensure_future(manager.broadcast(status, msg))

    # Run in background so the HTTP response returns immediately
    asyncio.ensure_future(agent.run_agent_task(req.prompt, broadcast=make_broadcast))

    return {"result": "ok", "msg": f"Task started: {req.prompt[:80]}"}


@router.post("/agent/reset")
async def agent_reset():
    """Clear agent conversation history."""
    agent.reset_history()
    await manager.broadcast("info", "Conversation history cleared.")
    return {"result": "ok", "msg": "History reset."}


# ---------------------------------------------------------------------------
# Skill management endpoints
# ---------------------------------------------------------------------------

@router.get("/skills")
async def list_skills():
    """List all loaded skills with metadata."""
    return {"skills": agent.get_skills_info()}


@router.post("/skills/create")
async def create_skill(req: CreateSkillRequest):
    """Convert a trajectory into a SKILL.md and reload the library."""
    trajectory_dir = Path(TRAINING_TRAJECTORY_DIR) / req.trajectory_id
    if not trajectory_dir.is_dir():
        return {"result": "error", "msg": f"Trajectory not found: {req.trajectory_id}"}

    try:
        output_path = convert_trajectory_to_skill(
            trajectory_dir=trajectory_dir,
            skill_name=req.name,
            description=req.description,
            trigger_phrases=req.trigger_phrases,
            output_dir=Path(SKILL_LIBRARY_DIR),
            approval_required=req.approval_required,
        )
        count = agent.reload_skills()
        return {
            "result": "ok",
            "msg": f"Skill '{req.name}' created at {output_path}",
            "skills_loaded": count,
        }
    except (FileNotFoundError, ValueError) as e:
        return {"result": "error", "msg": str(e)}


@router.post("/skills/reload")
async def reload_skills():
    """Hot-reload the skill library from disk."""
    count = agent.reload_skills()
    return {"result": "ok", "skills_loaded": count}
