"""HTTP API endpoints for the LocalAgent backend."""

import asyncio

from fastapi import APIRouter
from pydantic import BaseModel

from api.websocket import manager
from app_core import agent

router = APIRouter()


class PromptRequest(BaseModel):
    prompt: str


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
