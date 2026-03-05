"""Cua ComputerAgent — controls the host desktop via vision-language model."""

import asyncio
import logging
import re
import socket
from typing import Callable

from computer import Computer
from agent import ComputerAgent

from app_core.config import CUA_MODEL, CUA_COMPUTER_SERVER_HOST, CUA_COMPUTER_SERVER_PORT
from app_core.image_optimizer import ImageOptimizerCallback

logger = logging.getLogger(__name__)

StatusCallback = Callable[[str, str], None]

# Module-level state
_computer: Computer | None = None
_agent: ComputerAgent | None = None
_history: list[dict] = []
_running = False
# Track last action to auto-inject Enter after typing in Spotlight
_last_action_was_type = False
_spotlight_open = False
# Maximum consecutive wait() actions before we force-break the loop.
# The 7B model tends to get stuck in wait() spirals when it can't see progress.
MAX_CONSECUTIVE_WAITS = 3

# System instructions for the model. Kept short to minimise prefill tokens.
_MACOS_INSTRUCTIONS = (
    "You are controlling a macOS desktop. "
    "CRITICAL RULES:\n"
    "- To open apps: hotkey(key='command space'), then type(content='AppName'). "
    "Enter will be pressed automatically after typing.\n"
    "- Do NOT press enter yourself after typing in Spotlight. It is handled automatically.\n"
    "- Do NOT look for taskbar/dock icons. Use Spotlight only.\n"
    "- After typing an app name, wait() for the app to load.\n"
)

# Regex to detect simple "open <app>" tasks (no further instructions).
_OPEN_APP_PATTERN = re.compile(
    r"^(?:open|launch|start|run)\s+(.+?)(?:\s+app(?:lication)?)?$",
    re.IGNORECASE,
)

# Regex to detect compound tasks that START with opening an app, e.g.
# "open Spotify and play some music", "launch Safari and go to google.com".
# Group 1 = app name, Group 2 = the rest of the task after "and"/"then"/",".
_OPEN_APP_THEN_PATTERN = re.compile(
    r"^(?:open|launch|start|run)\s+(.+?)\s+(?:and|then|,)\s+(.+)$",
    re.IGNORECASE,
)


async def initialize():
    """Connect to the Cua computer server and create the agent."""
    global _computer, _agent

    _computer = Computer(
        use_host_computer_server=True,
        api_host=CUA_COMPUTER_SERVER_HOST,
        api_port=CUA_COMPUTER_SERVER_PORT,
    )
    await _computer.run()

    _agent = ComputerAgent(
        model=CUA_MODEL,
        tools=[_computer],
        only_n_most_recent_images=1,
        max_trajectory_budget=50.0,
        callbacks=[ImageOptimizerCallback()],
        instructions=_MACOS_INSTRUCTIONS,
        use_prompt_caching=True,
    )
    logger.info(f"ComputerAgent initialized with model={CUA_MODEL}")


async def shutdown():
    """Disconnect from the computer server."""
    global _computer
    if _computer:
        await _computer.disconnect()
        _computer = None
    logger.info("ComputerAgent shut down.")


def is_ready() -> bool:
    """Check if the agent is initialized and ready."""
    return _computer is not None and _agent is not None


def is_busy() -> bool:
    """Check if the agent is currently processing a task."""
    return _running


async def _run_osascript(script: str) -> tuple[bool, str]:
    """Run an AppleScript snippet and return (success, output/error)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "osascript", "-e", script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5)
        if proc.returncode == 0:
            return True, stdout.decode().strip()
        return False, stderr.decode().strip()
    except Exception as e:
        return False, str(e)


async def open_app(name: str) -> bool:
    """Open a macOS app directly via osascript, bypassing the vision loop."""
    ok, err = await _run_osascript(f'tell application "{name}" to activate')
    if ok:
        logger.info(f"Opened app '{name}' via osascript")
        await asyncio.sleep(1.0)  # Wait for app window to appear
        return True
    logger.warning(f"open_app('{name}') failed: {err}")
    return False


# ---------------------------------------------------------------------------
# App-action macros: map (app, action_keyword) → AppleScript commands.
# These let us handle common tasks entirely via osascript, bypassing the
# vision loop for actions the 7B model struggles with (clicking Play, etc.).
# ---------------------------------------------------------------------------
_APP_ACTIONS: dict[str, list[tuple[re.Pattern, str, str]]] = {
    # Each entry: (regex matching the remaining_task, applescript command, human description)
    "spotify": [
        (re.compile(r"play|start\s+(?:a\s+)?(?:song|music|track|playlist)", re.I),
         'tell application "Spotify" to play', "Started playback"),
        (re.compile(r"pause|stop", re.I),
         'tell application "Spotify" to pause', "Paused playback"),
        (re.compile(r"next|skip", re.I),
         'tell application "Spotify" to next track', "Skipped to next track"),
        (re.compile(r"prev(?:ious)?|go\s*back", re.I),
         'tell application "Spotify" to previous track', "Went to previous track"),
        (re.compile(r"shuffle", re.I),
         'tell application "Spotify" to set shuffling to (not shuffling)', "Toggled shuffle"),
    ],
    "music": [  # Apple Music
        (re.compile(r"play|start", re.I),
         'tell application "Music" to play', "Started playback"),
        (re.compile(r"pause|stop", re.I),
         'tell application "Music" to pause', "Paused playback"),
        (re.compile(r"next|skip", re.I),
         'tell application "Music" to next track', "Skipped to next track"),
        (re.compile(r"prev(?:ious)?|go\s*back", re.I),
         'tell application "Music" to previous track', "Went to previous track"),
    ],
}


async def _try_app_action(app_name: str, task: str) -> str | None:
    """Try to handle a task for an app via AppleScript macros.

    Returns a human-readable description on success, or None if no macro matched.
    """
    actions = _APP_ACTIONS.get(app_name.lower())
    if not actions:
        return None
    for pattern, script, description in actions:
        if pattern.search(task):
            ok, err = await _run_osascript(script)
            if ok:
                logger.info(f"App-action macro: {description} ({app_name})")
                return description
            logger.warning(f"App-action macro failed for '{app_name}': {err}")
            return None
    return None


async def _auto_enter_after_type():
    """Press Enter automatically after typing in Spotlight.

    The 7B model consistently fails to press Enter after typing in Spotlight,
    so we inject it automatically when we detect the pattern:
    hotkey(command space) -> type(text) -> [auto Enter]
    """
    if _computer and _computer.interface:
        logger.info("Auto-injecting Enter keypress after Spotlight type")
        await asyncio.sleep(0.3)  # Brief pause for search results to appear
        await _computer.interface.press_key("enter")
        await asyncio.sleep(1.0)  # Wait for app to launch


async def run_agent_task(prompt: str, broadcast: StatusCallback | None = None):
    """Run a natural language task through the ComputerAgent.

    Maintains conversation history for multi-turn context.
    Streams status updates via the broadcast callback.
    """
    global _running, _last_action_was_type, _spotlight_open

    if not is_ready():
        raise RuntimeError("Agent not initialized. Call initialize() first.")

    if _running:
        raise RuntimeError("Agent is already processing a task.")

    def _send(status: str, msg: str):
        if broadcast:
            broadcast(status, msg)

    _running = True
    _last_action_was_type = False
    _spotlight_open = False
    _consecutive_waits = 0
    try:
        # --- Fast-path: open apps via osascript instead of the vision loop ---
        stripped = prompt.strip()

        # 1) Compound: "open Spotify and play some music"
        compound = _OPEN_APP_THEN_PATTERN.match(stripped)
        if compound:
            app_name = compound.group(1).strip().strip("'\"")
            remaining_task = compound.group(2).strip()
            _send("thinking", f"Opening {app_name} directly...")
            if await open_app(app_name):
                _send("action", f"Opened {app_name} (fast-path)")
                # Try to handle the remaining task via AppleScript macro
                result = await _try_app_action(app_name, remaining_task)
                if result:
                    _send("done", f"Opened {app_name} and {result.lower()}.")
                    _history.append({"role": "user", "content": prompt})
                    _history.append({
                        "role": "assistant",
                        "content": f"Opened {app_name} and {result.lower()}.",
                    })
                    return
                # No macro matched — fall through to agent with rewritten prompt.
                # Tell the model the app is already open so it doesn't re-open it.
                prompt = (
                    f"{app_name} is already open and in the foreground. "
                    f"Do NOT open {app_name} again. Do NOT use Spotlight. "
                    f"Just {remaining_task}"
                )
                logger.info(f"Fast-path opened '{app_name}', agent gets: {prompt}")
            else:
                logger.info(f"Fast-path failed for '{app_name}', agent gets full prompt.")

        # 2) Simple: "open Spotify" (no further instructions)
        elif _OPEN_APP_PATTERN.match(stripped):
            app_name = _OPEN_APP_PATTERN.match(stripped).group(1).strip().strip("'\"")
            _send("thinking", f"Opening {app_name} directly...")
            if await open_app(app_name):
                _send("done", f"Opened {app_name}.")
                _history.append({"role": "user", "content": prompt})
                _history.append({
                    "role": "assistant",
                    "content": f"Opened {app_name} via fast-path.",
                })
                return
            logger.info(f"Fast-path failed for '{app_name}', falling back to agent.")

        # UI-TARS 7B ignores the `instructions` param, so we inline the rules
        # into the user prompt. The `instructions` param is kept on the agent
        # for models that do respect it, and prompt caching helps either way.
        enhanced_prompt = f"{_MACOS_INSTRUCTIONS}\n\nTask: {prompt}"
        _history.append({"role": "user", "content": enhanced_prompt})
        _send("thinking", f"Processing: {prompt[:80]}...")

        async for result in _agent.run(_history):
            for item in result.get("output", []):
                msg_type = item.get("type", "")
                if msg_type == "message":
                    content_blocks = item.get("content", [])
                    for block in content_blocks:
                        if block.get("type") == "text":
                            text = block["text"]
                            _send("action", text)
                            _history.append({"role": "assistant", "content": text})
                elif msg_type == "computer_call":
                    action = item.get("action", {})
                    action_type = action.get("type", "unknown")
                    _send("action", f"Performing: {action_type}")

                    # --- Consecutive wait() loop breaker ---
                    if action_type == "wait":
                        _consecutive_waits += 1
                        if _consecutive_waits >= MAX_CONSECUTIVE_WAITS:
                            logger.warning(
                                f"Breaking out: {_consecutive_waits} consecutive wait() "
                                "actions — model is stuck."
                            )
                            _send("error", "Agent stuck in wait loop, stopping task.")
                            _history.append({
                                "role": "assistant",
                                "content": "I got stuck waiting. Task stopped.",
                            })
                            return
                    else:
                        _consecutive_waits = 0

                    # Track Spotlight flow — try osascript fast-path first,
                    # fall back to auto-Enter injection.
                    if action_type == "keypress":
                        keys = action.get("keys", [])
                        if set(keys) == {"command", "space"} or set(keys) == {"cmd", "space"}:
                            _spotlight_open = True
                            _last_action_was_type = False
                            logger.info("Detected Spotlight open")
                    elif action_type == "type" and _spotlight_open:
                        app_name = action.get("content", "") or action.get("text", "")
                        # Try opening the app directly via osascript (skips vision loop)
                        if app_name and await open_app(app_name):
                            logger.info(f"Fast-path: opened '{app_name}' via osascript")
                            _send("action", f"Opened {app_name} (fast-path)")
                        else:
                            # Fallback: let the type action proceed and auto-press Enter
                            logger.info("Falling back to auto-Enter after Spotlight type")
                            await _auto_enter_after_type()
                        _spotlight_open = False
                        _last_action_was_type = False

        _send("done", "Task complete.")
    except Exception as e:
        logger.exception("Agent task failed")
        _send("error", f"Agent error: {e}")
    finally:
        _running = False


def reset_history():
    """Clear the conversation history for a fresh start."""
    global _history
    _history = []
    logger.info("Agent conversation history reset.")


async def check_services() -> dict:
    """Check if required services (computer server, ollama) are reachable.

    Uses a raw TCP socket connect for localhost instead of a full HTTP request
    to minimise health-check overhead.
    """
    status = {"computer_server": False, "model": CUA_MODEL}

    def _tcp_check(host: str, port: int, timeout: float = 1.0) -> bool:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except (OSError, socket.timeout):
            return False

    # Run the blocking socket check in a thread so we don't stall the event loop.
    status["computer_server"] = await asyncio.get_event_loop().run_in_executor(
        None, _tcp_check, CUA_COMPUTER_SERVER_HOST, CUA_COMPUTER_SERVER_PORT
    )

    return status
