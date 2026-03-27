import asyncio
import json
import os
import signal
import sys
from pathlib import Path

import websockets
from dotenv import load_dotenv
from computer import Computer
from agent import ComputerAgent

try:
    from .prompt_builder import build_task_prompt
except ImportError:
    from prompt_builder import build_task_prompt

load_dotenv()

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "config.json"
CONFIG_PATH = Path(os.getenv("CUA_RUNTIME_CONFIG", str(DEFAULT_CONFIG_PATH)))

with CONFIG_PATH.open("r", encoding="utf-8") as f:
    CONFIG = json.load(f)

agent_cfg = CONFIG["agent"]
server_cfg = CONFIG["server"]

computer = Computer(use_host_computer_server=True)
_agents_by_model = {}

task_running = False
cancel_requested = False
stop_event: asyncio.Event | None = None


def _build_agent(model_name: str) -> ComputerAgent:
    return ComputerAgent(
        model=model_name,
        tools=[computer],
        only_n_most_recent_images=agent_cfg.get("only_n_most_recent_images", 3),
        max_retries=agent_cfg.get("max_retries", 3),
        screenshot_delay=agent_cfg.get("screenshot_delay", 0.5),
        instructions=agent_cfg.get("instructions"),
    )


def _resolve_agent(model_override: str | None) -> tuple[ComputerAgent, str]:
    selected_model = str(model_override or agent_cfg["model"]).strip()
    if selected_model not in _agents_by_model:
        _agents_by_model[selected_model] = _build_agent(selected_model)
    return _agents_by_model[selected_model], selected_model


def serialize_safe(obj):
    try:
        json.dumps(obj)
        return obj
    except (TypeError, ValueError):
        if isinstance(obj, dict):
            return {k: str(v) for k, v in obj.items()}
        return str(obj)


async def run_task(
    ws,
    task_text: str,
    model_override: str | None = None,
    connection_ref: str | None = None,
):
    global task_running, cancel_requested
    task_running = True
    cancel_requested = False

    try:
        agent, selected_model = _resolve_agent(model_override)
        await ws.send(
            json.dumps(
                {
                    "type": "message",
                    "text": f"[server] Running task with model: {selected_model}",
                }
            )
        )

        prompt = build_task_prompt(
            task_text=task_text,
            connections=CONFIG.get("connections", {}),
            connection_ref=connection_ref,
        )
        messages = [{"role": "user", "content": prompt}]

        async for result in agent.run(messages):
            if cancel_requested or (stop_event is not None and stop_event.is_set()):
                await ws.send(
                    json.dumps(
                        {
                            "type": "cancelled",
                            "message": "Task cancelled by client.",
                        }
                    )
                )
                return

            for item in result.get("output", []):
                item_type = item.get("type")

                if item_type == "message":
                    for content in item.get("content", []):
                        if isinstance(content, dict) and content.get("text"):
                            await ws.send(
                                json.dumps(
                                    {
                                        "type": "message",
                                        "text": content["text"],
                                    }
                                )
                            )
                elif item_type == "action":
                    await ws.send(
                        json.dumps(
                            {
                                "type": "action",
                                "detail": serialize_safe(item),
                            }
                        )
                    )

        await ws.send(
            json.dumps(
                {
                    "type": "done",
                    "summary": "Task completed.",
                }
            )
        )
    except websockets.ConnectionClosed:
        pass
    except Exception as exc:
        try:
            await ws.send(
                json.dumps(
                    {
                        "type": "error",
                        "message": str(exc),
                    }
                )
            )
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
                await ws.send(
                    json.dumps(
                        {
                            "type": "error",
                            "message": "Invalid JSON.",
                        }
                    )
                )
                continue

            msg_type = msg.get("type")
            if msg_type == "task":
                if stop_event is not None and stop_event.is_set():
                    await ws.send(
                        json.dumps(
                            {
                                "type": "error",
                                "message": "Server is shutting down.",
                            }
                        )
                    )
                    continue

                if task_running:
                    await ws.send(
                        json.dumps(
                            {
                                "type": "error",
                                "message": "A task is already running. Send {\"type\":\"cancel\"} first.",
                            }
                        )
                    )
                    continue

                content = msg.get("content", "").strip()
                if not content:
                    await ws.send(
                        json.dumps(
                            {
                                "type": "error",
                                "message": "Empty task content.",
                            }
                        )
                    )
                    continue

                model_override = msg.get("model")
                connection_ref = msg.get("connection_ref")
                current_task = asyncio.create_task(
                    run_task(
                        ws=ws,
                        task_text=content,
                        model_override=model_override,
                        connection_ref=connection_ref,
                    )
                )
            elif msg_type == "cancel":
                if task_running:
                    cancel_requested = True
                else:
                    await ws.send(
                        json.dumps(
                            {
                                "type": "error",
                                "message": "No task is running.",
                            }
                        )
                    )
            else:
                await ws.send(
                    json.dumps(
                        {
                            "type": "error",
                            "message": f"Unknown message type: {msg_type}",
                        }
                    )
                )
    except websockets.ConnectionClosed:
        pass
    finally:
        if current_task and not current_task.done():
            cancel_requested = True
            current_task.cancel()
        print(f"Client disconnected: {ws.remote_address}")


def _install_signal_handlers(shutdown_event: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()

    def _request_shutdown() -> None:
        if not shutdown_event.is_set():
            print("Shutdown signal received. Stopping services...")
            shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_shutdown)
        except NotImplementedError:
            # Fallback platforms may rely on KeyboardInterrupt from asyncio.run.
            pass


async def _start_computer_server() -> asyncio.subprocess.Process | None:
    runtime_cfg = CONFIG.get("computer_server", {})
    auto_start = bool(runtime_cfg.get("auto_start", True))
    if not auto_start:
        print("computer_server auto-start disabled by config.")
        return None

    custom_command = runtime_cfg.get("command")
    if isinstance(custom_command, list) and custom_command:
        command = [str(part) for part in custom_command]
    else:
        command = [
            sys.executable,
            "-m",
            "computer_server",
            "--log-level",
            str(runtime_cfg.get("log_level", "debug")),
        ]

    env = os.environ.copy()
    display = runtime_cfg.get("display")
    if display:
        env["DISPLAY"] = str(display)
    elif "DISPLAY" not in env:
        env["DISPLAY"] = ":0"

    print(f"Starting computer_server: {' '.join(command)}")
    process = await asyncio.create_subprocess_exec(*command, env=env)

    startup_delay = float(runtime_cfg.get("startup_delay_seconds", 1.5))
    if startup_delay > 0:
        await asyncio.sleep(startup_delay)

    if process.returncode is not None:
        raise RuntimeError(f"computer_server exited early with code {process.returncode}.")

    return process


async def _stop_computer_server(process: asyncio.subprocess.Process | None) -> None:
    if process is None or process.returncode is not None:
        return

    process.terminate()
    try:
        await asyncio.wait_for(process.wait(), timeout=8)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()


async def _connect_computer_with_retries() -> None:
    runtime_cfg = CONFIG.get("computer_server", {})
    retries = int(runtime_cfg.get("connect_retries", 10))
    retry_delay = float(runtime_cfg.get("connect_retry_delay_seconds", 0.7))
    last_error: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            await computer.run()
            return
        except Exception as exc:
            last_error = exc
            if attempt == retries:
                break
            print(f"computer.connect attempt {attempt}/{retries} failed: {exc}")
            await asyncio.sleep(retry_delay)

    raise RuntimeError(f"Unable to connect computer after {retries} attempts: {last_error}")


async def main():
    global cancel_requested, stop_event
    stop_event = asyncio.Event()
    _install_signal_handlers(stop_event)

    print(f"Using runtime config: {CONFIG_PATH}")
    computer_server_proc: asyncio.subprocess.Process | None = None
    try:
        computer_server_proc = await _start_computer_server()
        print("Initializing computer connection...")
        await _connect_computer_with_retries()
        print("Computer connected.")

        host = server_cfg.get("host", "localhost")
        port = server_cfg.get("port", 8765)

        async with websockets.serve(handle_client, host, port):
            print(f"WebSocket server running on ws://{host}:{port}")
            print("Waiting for client connections...")
            await stop_event.wait()
    finally:
        cancel_requested = True
        try:
            await computer.disconnect()
            print("Computer disconnected.")
        finally:
            await _stop_computer_server(computer_server_proc)
            print("computer_server stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # In environments where asyncio signal handlers are unavailable.
        pass
