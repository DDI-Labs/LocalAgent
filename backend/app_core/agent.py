"""Cua ComputerAgent orchestrator — composed model pipeline.

Architecture:
  1. Local Grounding (UI-TARS 7B MLX) — processes screenshots, identifies UI elements
  2. PII Sanitization — masks personal data before cloud calls
  3. Cloud Planning (Claude Sonnet 4.5 via OpenRouter) — decides actions from sanitized text
  4. Local Execution — re-maps to real data and performs actions via Computer tool
"""

import asyncio
import base64
import gc
import logging
import socket
import uuid
from typing import Callable

from computer import Computer
from agent import ComputerAgent
from agent.callbacks import (
    ImageRetentionCallback,
    LoggingCallback,
    OperatorNormalizerCallback,
    TrajectorySaverCallback,
)

from app_core.config import (
    CUA_MODEL,
    CUA_COMPUTER_SERVER_HOST,
    CUA_COMPUTER_SERVER_PORT,
    IMAGE_RETENTION_COUNT,
    MLX_MEMORY_LIMIT,
    TRAJECTORY_DIR,
    TRAJECTORY_SCREENSHOT_DIR,
    PII_SANITIZATION_ENABLED,
    OPENROUTER_API_KEY,
)
from app_core.callbacks import (
    HistoryTrimCallback,
    ImageOptimizerCallback,
    PIISanitizerCallback,
    RunGuardCallback,
    SecurityBlockedError,
    SecurityInterceptionCallback,
    WebSocketStatusCallback,
)
from app_core.macros import (
    MACOS_INSTRUCTIONS,
    OPEN_APP_PATTERN,
    OPEN_APP_THEN_PATTERN,
    auto_enter_after_type,
    open_app,
    try_app_action,
)

logger = logging.getLogger(__name__)

StatusCallback = Callable[..., None]


async def _take_seeded_screenshot() -> list[dict]:
    """Take a screenshot and return history items the composed loop will recognise.

    When the composed_grounded loop sees a computer_call_output with an image
    in the message history, it skips taking its own screenshot.  By seeding the
    history after fast-path app activation, we guarantee the planning model sees
    the *current* app window — not a stale frame from before the switch.
    """
    if _computer is None:
        return []
    try:
        raw = await _computer.interface.screenshot()
        b64 = base64.b64encode(raw).decode("utf-8")

        # Save to disk for debugging — lets us verify what the model actually sees.
        import os
        debug_dir = os.path.join(os.path.dirname(__file__), "..", TRAJECTORY_DIR, "screenshots")
        os.makedirs(debug_dir, exist_ok=True)
        debug_path = os.path.join(debug_dir, "seeded_screenshot_debug.png")
        with open(debug_path, "wb") as f:
            f.write(raw)
        logger.info(f"Seeded screenshot saved to {debug_path} ({len(raw) // 1024}KB)")
    except Exception as e:
        logger.warning(f"Seeded screenshot failed: {e}")
        return []

    call_id = uuid.uuid4().hex
    return [
        {
            "type": "message",
            "role": "assistant",
            "content": [
                {
                    "type": "output_text",
                    "text": "Taking a screenshot to see the current state.",
                }
            ],
        },
        {
            "action": {"type": "screenshot"},
            "call_id": call_id,
            "status": "completed",
            "type": "computer_call",
        },
        {
            "type": "computer_call_output",
            "call_id": call_id,
            "output": {
                "type": "input_image",
                "image_url": f"data:image/png;base64,{b64}",
            },
        },
    ]


# Module-level state
_computer: Computer | None = None
_agent: ComputerAgent | None = None
_history: list[dict] = []
_running = False
# Track Spotlight flow for auto-Enter injection
_spotlight_open = False
# Callbacks that need per-task updates (set during initialize)
_ws_status_cb: WebSocketStatusCallback | None = None
_run_guard_cb: RunGuardCallback | None = None
_pii_cb: PIISanitizerCallback | None = None


async def initialize():
    """Connect to the Cua computer server and create the composed agent."""
    global _computer, _agent, _ws_status_cb, _run_guard_cb, _pii_cb

    import os

    # Inject OpenRouter API key into environment for LiteLLM
    if OPENROUTER_API_KEY:
        os.environ.setdefault("OPENROUTER_API_KEY", OPENROUTER_API_KEY)

    # Cap MLX unified memory usage to prevent the grounding model from
    # starving other processes (browser, OS, etc.) on the Mac.
    try:
        import mlx.core as mx
        mx.metal.set_memory_limit(int(MLX_MEMORY_LIMIT * mx.metal.device_info()["memory_size"]))
        logger.info(f"MLX memory limit set to {MLX_MEMORY_LIMIT:.0%} of device memory")
    except Exception as e:
        logger.debug(f"MLX memory limit not set ({e}) — non-fatal")

    _computer = Computer(
        use_host_computer_server=True,
        api_host=CUA_COMPUTER_SERVER_HOST,
        api_port=CUA_COMPUTER_SERVER_PORT,
    )
    await _computer.run()

    # --- Callback stack ---
    # Order matters: normalisation and security run first, then PII sanitization,
    # then memory/image optimisation, then observability, then housekeeping.
    _ws_status_cb = WebSocketStatusCallback()
    _run_guard_cb = RunGuardCallback()
    _pii_cb = PIISanitizerCallback(enabled=PII_SANITIZATION_ENABLED)

    callbacks = [
        # 1. Normalise malformed LLM output (hotkey→keypress, string keys→list, etc.)
        OperatorNormalizerCallback(),
        # 2. Security: intercept and block dangerous actions before execution
        SecurityInterceptionCallback(),
        # 3. Run guard: halt on consecutive wait() loops or wall-clock timeout
        _run_guard_cb,
        # 4. PII sanitization: mask personal data before cloud planning model calls
        _pii_cb,
        # 5. Memory safety: keep only N most recent screenshots in context
        ImageRetentionCallback(only_n_most_recent_images=IMAGE_RETENTION_COUNT),
        # 6. Image optimization: downscale/compress screenshots before LLM inference
        ImageOptimizerCallback(),
        # 7. Structured lifecycle logging
        LoggingCallback(level=logging.INFO),
        # 8. Audit trail: save full trajectory (screenshots, prompts, coordinates)
        TrajectorySaverCallback(
            trajectory_dir=TRAJECTORY_DIR,
            screenshot_dir=TRAJECTORY_SCREENSHOT_DIR,
        ),
        # 9. Broadcast detailed action status to WebSocket clients
        _ws_status_cb,
        # 10. Trim conversation history to prevent unbounded memory growth
        HistoryTrimCallback(history=_history, max_entries=50),
    ]

    _agent = ComputerAgent(
        model=CUA_MODEL,
        tools=[_computer],
        max_trajectory_budget=25.0,
        callbacks=callbacks,
        instructions=MACOS_INSTRUCTIONS,
        use_prompt_caching=True,
    )
    logger.info(
        f"ComputerAgent initialized — model={CUA_MODEL}, "
        f"pii_sanitization={PII_SANITIZATION_ENABLED}, "
        f"image_retention={IMAGE_RETENTION_COUNT}, "
        f"callbacks={len(callbacks)}"
    )


async def preload_model():
    """Eagerly load the vision model into memory.

    Called during startup so the first user prompt doesn't pay the
    model-load penalty (~10-30s depending on hardware).
    """
    if _agent is None:
        logger.warning("Cannot preload: agent not initialized.")
        return
    logger.info("Preloading vision model into memory...")
    try:
        dummy_history = [{"role": "user", "content": "hello"}]
        async for _ in _agent.run(dummy_history):
            pass
    except Exception as e:
        logger.warning(f"Model preload failed (non-fatal): {e}")
    logger.info("Vision model preloaded.")


async def shutdown():
    """Disconnect from the computer server."""
    global _computer
    if _computer:
        await _computer.disconnect()
        _computer = None
    logger.info("ComputerAgent shut down.")


def is_ready() -> bool:
    return _computer is not None and _agent is not None


def is_busy() -> bool:
    return _running


async def run_agent_task(prompt: str, broadcast: StatusCallback | None = None):
    """Run a natural language task through the composed ComputerAgent.

    Maintains conversation history for multi-turn context.
    Streams status updates via the broadcast callback.
    """
    global _running, _spotlight_open

    if not is_ready():
        raise RuntimeError("Agent not initialized. Call initialize() first.")
    if _running:
        raise RuntimeError("Agent is already processing a task.")

    def _send(status: str, msg: str):
        if broadcast:
            broadcast(status, msg)

    _running = True
    _spotlight_open = False

    # Wire per-task broadcast into callbacks
    if _ws_status_cb is not None:
        _ws_status_cb.set_broadcast(broadcast)
    if _pii_cb is not None:
        _pii_cb.set_broadcast(broadcast)

    try:
        # --- Fast-path: open apps via osascript instead of the vision loop ---
        stripped = prompt.strip()
        seed_items: list[dict] = []  # populated by fast-path if app opened

        # 1) Compound: "open Spotify and play some music"
        compound = OPEN_APP_THEN_PATTERN.match(stripped)
        if compound:
            app_name = compound.group(1).strip().strip("'\"")
            remaining_task = compound.group(2).strip()
            _send("thinking", f"Opening {app_name} directly...")
            if await open_app(app_name):
                _send("action", f"Opened {app_name} (fast-path)")
                result = await try_app_action(app_name, remaining_task)
                if result:
                    _send("done", f"Opened {app_name} and {result.lower()}.")
                    _history.append({"role": "user", "content": prompt})
                    _history.append({
                        "role": "assistant",
                        "content": f"Opened {app_name} and {result.lower()}.",
                    })
                    return
                # No macro matched — tell model the app is already open.
                # Seed a fresh screenshot so the composed loop won't take
                # its own (which may still show the previous app).
                seed_items = await _take_seeded_screenshot()

                prompt = (
                    f"{app_name} is already open and in the foreground. "
                    f"You can see it in the screenshot above. "
                    f"Do NOT open {app_name} again. Do NOT use Spotlight. "
                    f"Do NOT use Command+Tab. Do NOT click the Dock. "
                    f"The current screen IS {app_name} — proceed directly with the task. "
                    f"To search in {app_name}, click the search icon or search bar "
                    f"inside the {app_name} window first, then type your query. "
                    f"Do NOT type into any other field. "
                    f"Task: {remaining_task}"
                )
                logger.info(f"Fast-path opened '{app_name}', agent gets: {prompt}")
            else:
                logger.info(f"Fast-path failed for '{app_name}', agent gets full prompt.")

        # 2) Simple: "open Spotify" (no further instructions)
        elif OPEN_APP_PATTERN.match(stripped):
            app_name = OPEN_APP_PATTERN.match(stripped).group(1).strip().strip("'\"")
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

        # Inline instructions for models that ignore the instructions param
        enhanced_prompt = f"{MACOS_INSTRUCTIONS}\n\nTask: {prompt}"
        _history.append({"role": "user", "content": enhanced_prompt})

        # If the fast-path seeded a screenshot, inject it into history so the
        # composed loop sees an existing image and doesn't take a stale one.
        if seed_items:
            _history.extend(seed_items)
            logger.info("Seeded post-activation screenshot into history")

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

                    # Track Spotlight flow
                    if action_type == "keypress":
                        keys = action.get("keys", [])
                        if set(keys) == {"command", "space"} or set(keys) == {"cmd", "space"}:
                            _spotlight_open = True
                            logger.info("Detected Spotlight open")
                    elif action_type == "type" and _spotlight_open:
                        app_name = action.get("content", "") or action.get("text", "")
                        if app_name and await open_app(app_name):
                            logger.info(f"Fast-path: opened '{app_name}' via osascript")
                            _send("action", f"Opened {app_name} (fast-path)")
                        else:
                            logger.info("Falling back to auto-Enter after Spotlight type")
                            await auto_enter_after_type(_computer)
                        _spotlight_open = False

        # Check if RunGuardCallback halted the run
        if _run_guard_cb and _run_guard_cb.halt_reason:
            _send("error", _run_guard_cb.halt_reason)
            _history.append({
                "role": "assistant",
                "content": _run_guard_cb.halt_reason,
            })
        else:
            _send("done", "Task complete.")

    except SecurityBlockedError as e:
        logger.warning(f"Action blocked by security policy: {e}")
        _send("blocked", f"Security policy blocked an action: {e}")
        _history.append({
            "role": "assistant",
            "content": f"Action blocked by security policy: {e}",
        })
    except Exception as e:
        logger.exception("Agent task failed")
        _send("error", f"Agent error: {e}")
    finally:
        _running = False
        if _ws_status_cb is not None:
            _ws_status_cb.set_broadcast(None)
        if _pii_cb is not None:
            _pii_cb.set_broadcast(None)
        # Reclaim memory between turns — the grounding model allocates large
        # tensors that Python's refcount GC may not collect promptly.
        gc.collect()


def reset_history():
    """Clear the conversation history for a fresh start."""
    global _history
    _history = []
    logger.info("Agent conversation history reset.")


async def check_services() -> dict:
    """Check if required services (computer server) are reachable."""
    status = {"computer_server": False, "model": CUA_MODEL}

    def _tcp_check(host: str, port: int, timeout: float = 1.0) -> bool:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except (OSError, socket.timeout):
            return False

    status["computer_server"] = await asyncio.get_event_loop().run_in_executor(
        None, _tcp_check, CUA_COMPUTER_SERVER_HOST, CUA_COMPUTER_SERVER_PORT
    )

    return status
