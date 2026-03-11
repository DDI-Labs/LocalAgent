"""Entry point — FastAPI application with WebSocket and ComputerAgent."""

import asyncio
import json
import logging

from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router
from api.websocket import manager
from app_core import agent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: initialize ComputerAgent. Shutdown: disconnect."""
    try:
        await agent.initialize()
        logger.info("ComputerAgent ready.")
        # Eagerly load the vision model so the first prompt is instant.
        await agent.preload_model()
    except Exception as e:
        logger.warning(f"ComputerAgent failed to initialize: {e}")
        logger.warning("The agent won't work until services are available. Check:")
        logger.warning("  1. Cua computer server: python -m computer_server")
        logger.warning("  2. Ollama: ollama serve")
    yield
    await agent.shutdown()


app = FastAPI(
    title="LocalAgent Backend",
    description="Local AI Agent — natural language desktop control via Cua",
    version="0.2.0",
    lifespan=lifespan,
)

# CORS: allow the Vite/React frontend during development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount HTTP routes
app.include_router(router)


# ---------------------------------------------------------------------------
# WebSocket endpoint — natural language prompts
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                await websocket.send_text(
                    json.dumps({"status": "error", "msg": "Invalid JSON"})
                )
                continue

            msg_type = payload.get("type", "")

            if msg_type == "prompt":
                content = payload.get("content", "").strip()
                if not content:
                    await websocket.send_text(
                        json.dumps({"status": "error", "msg": "Empty prompt"})
                    )
                    continue

                if not agent.is_ready():
                    await websocket.send_text(
                        json.dumps({"status": "error", "msg": "Agent not initialized. Check services."})
                    )
                    continue

                if agent.is_busy():
                    await websocket.send_text(
                        json.dumps({"status": "error", "msg": "Agent is busy. Wait for current task to finish."})
                    )
                    continue

                def make_broadcast(status: str, msg: str):
                    asyncio.ensure_future(
                        manager.broadcast(status, msg)
                    )

                asyncio.ensure_future(
                    agent.run_agent_task(content, broadcast=make_broadcast)
                )

            elif msg_type == "reset":
                agent.reset_history()
                await manager.broadcast("info", "Conversation history cleared.")

            else:
                await websocket.send_text(
                    json.dumps({"status": "error", "msg": f"Unknown message type: {msg_type}"})
                )

    except WebSocketDisconnect:
        manager.disconnect(websocket)


# ---------------------------------------------------------------------------
# Run with: uvicorn main:app --reload
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
