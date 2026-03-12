"""LocalAgent Linux backend — entry point.

Provides:
- WebSocket endpoint for real-time agent interaction
- REST endpoints for status and manual task submission
- CLI mode for quick testing without the frontend
"""

import asyncio
import json
import logging
import sys
import threading

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from agent.loop import AgentLoop
from model.client import check_model_available
from config import HOST, PORT, OLLAMA_MODEL, DEBUG_DIR
from sites import get_site, list_sites

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)

app = FastAPI(title="LocalAgent Linux")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- State ---

_agent: AgentLoop | None = None
_agent_lock = threading.Lock()


# --- REST endpoints ---

@app.get("/health")
async def health():
    model_ok = check_model_available()
    return {
        "status": "ok",
        "model": OLLAMA_MODEL,
        "model_available": model_ok,
    }


@app.get("/sites")
async def sites():
    """Return all configured sites (credentials redacted)."""
    safe = []
    for s in list_sites():
        entry = {k: v for k, v in s.items() if k not in ("password",)}
        safe.append(entry)
    return safe


@app.post("/run")
async def run_task(body: dict):
    """Submit a task via REST (for testing without the frontend).

    Body example:
    {
        "site": "tower-a",
        "details": {
            "building": "Tower A",
            "license_plate": "ABC-1234",
            "reason": "lost parking ticket"
        }
    }
    """
    global _agent

    with _agent_lock:
        if _agent and not _agent._stopped:
            return {"error": "Agent is already running a task."}

    task_details = body.get("details", body)
    site = None
    site_id = body.get("site") or task_details.get("site")
    if site_id:
        try:
            site = get_site(site_id)
        except KeyError as e:
            return {"error": str(e)}

    def on_status(status: str, msg: str):
        log.info("[%s] %s", status, msg)

    _agent = AgentLoop(task_details, on_status=on_status, site=site)
    result = _agent.run()
    _agent = None
    return result


# --- WebSocket endpoint ---

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    global _agent
    await ws.accept()
    log.info("WebSocket client connected")

    async def send_status(status: str, msg: str):
        try:
            await ws.send_json({"status": status, "msg": msg})
        except Exception:
            pass

    try:
        while True:
            data = await ws.receive_json()

            if data.get("type") == "reset":
                if _agent:
                    _agent.stop()
                    _agent = None
                await send_status("done", "Agent reset.")
                continue

            if data.get("type") == "prompt":
                task_details = data.get("details", {})

                site = None
                site_id = data.get("site") or task_details.get("site")
                if site_id:
                    try:
                        site = get_site(site_id)
                    except KeyError as e:
                        await send_status("error", str(e))
                        continue

                with _agent_lock:
                    if _agent and not _agent._stopped:
                        await send_status("error", "Agent is already running.")
                        continue

                loop = asyncio.get_event_loop()

                def on_status_sync(status: str, msg: str):
                    asyncio.run_coroutine_threadsafe(send_status(status, msg), loop)

                _agent = AgentLoop(task_details, on_status=on_status_sync, site=site)

                def run_agent():
                    global _agent
                    try:
                        result = _agent.run()
                        asyncio.run_coroutine_threadsafe(
                            send_status("result", json.dumps(result)), loop
                        )
                    except Exception as e:
                        asyncio.run_coroutine_threadsafe(
                            send_status("error", str(e)), loop
                        )
                    finally:
                        _agent = None

                thread = threading.Thread(target=run_agent, daemon=True)
                thread.start()

    except WebSocketDisconnect:
        log.info("WebSocket client disconnected")
        if _agent:
            _agent.stop()


# --- CLI mode ---

def run_cli(task_details: dict, site: dict | None = None):
    """Run a task directly from the command line (no server)."""
    print(f"\n--- LocalAgent CLI ---")
    print(f"Model: {OLLAMA_MODEL}")
    print(f"Task: {json.dumps(task_details, indent=2)}")
    if site:
        print(f"Site: {site['name']} (via {site['app']})")
    print(f"\nDebug screenshots: {DEBUG_DIR}/")
    print(f"   Watch live: eog {DEBUG_DIR}/latest.png")
    print(f"   Or browse:  nautilus {DEBUG_DIR}/\n")

    if not check_model_available():
        print(f"ERROR: Model '{OLLAMA_MODEL}' not found in Ollama.")
        print(f"Pull it with: ollama pull {OLLAMA_MODEL}")
        sys.exit(1)

    def on_status(status: str, msg: str):
        prefix = {"thinking": "🤔", "action": "⚡", "done": "✅", "error": "❌"}.get(status, "•")
        print(f"  {prefix} [{status}] {msg}")

    agent = AgentLoop(task_details, on_status=on_status, site=site)
    result = agent.run()

    print(f"\n--- Result ---")
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    if "--cli" in sys.argv:
        # Example: python main.py --cli
        #          python main.py --cli --site google-test
        mock_task = {
            "building": "Tower A",
            "license_plate": "XYZ-5678",
            "booking_bay": "B12",
            "reason": "Employee, lost parking ticket",
            "raw_transcript": (
                "Hi, I'm an employee of Tower A. I lost my parking ticket. "
                "My licence plate is XYZ-5678. Can you patch me through?"
            ),
        }
        site = None
        if "--site" in sys.argv:
            idx = sys.argv.index("--site")
            site_id = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else None
            if site_id:
                site = get_site(site_id)
                print(f"Site: {site['name']} ({site['app']})")
        run_cli(mock_task, site=site)
    else:
        log.info("Starting LocalAgent Linux backend on %s:%d", HOST, PORT)
        uvicorn.run(app, host=HOST, port=PORT)
