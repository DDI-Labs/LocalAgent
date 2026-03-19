import asyncio
import json
import os

import websockets
from dotenv import load_dotenv
from computer import Computer
from agent import ComputerAgent

load_dotenv()

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

with open(CONFIG_PATH) as f:
    CONFIG = json.load(f)

agent_cfg = CONFIG["agent"]
server_cfg = CONFIG["server"]

computer = Computer(use_host_computer_server=True)
cua_agent = ComputerAgent(
    model=agent_cfg["model"],
    tools=[computer],
    only_n_most_recent_images=agent_cfg.get("only_n_most_recent_images", 3),
    max_retries=agent_cfg.get("max_retries", 3),
    screenshot_delay=agent_cfg.get("screenshot_delay", 0.5),
)

task_running = False
cancel_requested = False


def build_task_prompt(task_text: str) -> str:
    """Enrich the raw task text with connection details from config if referenced."""
    connections = CONFIG.get("connections", {})
    context_lines = []

    for app_name, hosts in connections.items():
        for host_key, details in hosts.items():
            name = details.get("name", host_key)
            if name.lower() in task_text.lower():
                context_lines.append(f"Connection info for {name} ({app_name}):")
                for k, v in details.items():
                    if k != "name" and v:
                        context_lines.append(f"  {k}: {v}")

    if context_lines:
        return task_text + "\n\n" + "\n".join(context_lines)
    return task_text


def serialize_safe(obj):
    """Make an object JSON-serializable."""
    try:
        json.dumps(obj)
        return obj
    except (TypeError, ValueError):
        if isinstance(obj, dict):
            return {k: str(v) for k, v in obj.items()}
        return str(obj)


async def run_task(ws, task_text: str):
    global task_running, cancel_requested
    task_running = True
    cancel_requested = False

    try:
        prompt = build_task_prompt(task_text)
        messages = [{"role": "user", "content": prompt}]

        async for result in cua_agent.run(messages):
            if cancel_requested:
                await ws.send(json.dumps({
                    "type": "cancelled",
                    "message": "Task cancelled by client.",
                }))
                return

            for item in result.get("output", []):
                item_type = item.get("type")

                if item_type == "message":
                    for content in item.get("content", []):
                        if isinstance(content, dict) and content.get("text"):
                            await ws.send(json.dumps({
                                "type": "message",
                                "text": content["text"],
                            }))
                elif item_type == "action":
                    await ws.send(json.dumps({
                        "type": "action",
                        "detail": serialize_safe(item),
                    }))

        await ws.send(json.dumps({
            "type": "done",
            "summary": "Task completed.",
        }))

    except websockets.ConnectionClosed:
        pass
    except Exception as e:
        try:
            await ws.send(json.dumps({
                "type": "error",
                "message": str(e),
            }))
        except websockets.ConnectionClosed:
            pass
    finally:
        task_running = False
        cancel_requested = False


async def handle_client(ws):
    global cancel_requested
    await ws.send(json.dumps({"type": "ready"}))
    print(f"Client connected: {ws.remote_address}")

    current_task = None
    try:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send(json.dumps({
                    "type": "error",
                    "message": "Invalid JSON.",
                }))
                continue

            msg_type = msg.get("type")

            if msg_type == "task":
                if task_running:
                    await ws.send(json.dumps({
                        "type": "error",
                        "message": "A task is already running. Send {\"type\":\"cancel\"} first.",
                    }))
                else:
                    content = msg.get("content", "").strip()
                    if not content:
                        await ws.send(json.dumps({
                            "type": "error",
                            "message": "Empty task content.",
                        }))
                    else:
                        current_task = asyncio.create_task(run_task(ws, content))

            elif msg_type == "cancel":
                if task_running:
                    cancel_requested = True
                else:
                    await ws.send(json.dumps({
                        "type": "error",
                        "message": "No task is running.",
                    }))
            else:
                await ws.send(json.dumps({
                    "type": "error",
                    "message": f"Unknown message type: {msg_type}",
                }))

    except websockets.ConnectionClosed:
        pass
    finally:
        if current_task and not current_task.done():
            cancel_requested = True
            current_task.cancel()
        print(f"Client disconnected: {ws.remote_address}")


async def main():
    print("Initializing computer connection...")
    await computer.run()
    print("Computer connected.")

    host = server_cfg.get("host", "localhost")
    port = server_cfg.get("port", 8765)

    try:
        async with websockets.serve(handle_client, host, port):
            print(f"WebSocket server running on ws://{host}:{port}")
            print("Waiting for client connections...")
            await asyncio.Future()  # run forever
    finally:
        await computer.disconnect()
        print("Computer disconnected.")


if __name__ == "__main__":
    asyncio.run(main())
