"""Cua ComputerAgent orchestrator — composed model pipeline with HITL.

Architecture:
  1. Local Grounding (UI-TARS 7B MLX) — processes screenshots, identifies UI elements
  2. PII Sanitization — masks personal data before cloud calls
  3. Cloud Planning (Claude Sonnet 4.5 via OpenRouter) — decides actions from sanitized text
  4. Local Execution — re-maps to real data and performs actions via Computer tool

Human-in-the-Loop (HITL):
  - Escalation: when the agent gets stuck (consecutive waits), the system pauses
    and asks the user to perform a manual click (takeover mode).
  - Protected actions: when the planning model proposes an action matching a
    sensitive keyword list, the system pauses for user approval before executing.
"""

import asyncio
import base64
import gc
import logging
import socket
import uuid
from pathlib import Path
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
    HITL_APPROVAL_TIMEOUT,
    HITL_ENABLED,
    HITL_MAX_TAKEOVER_ATTEMPTS,
    HITL_SENSITIVE_ACTIONS,
    IMAGE_RETENTION_COUNT,
    MLX_MEMORY_LIMIT,
    TRAJECTORY_DIR,
    TRAJECTORY_SCREENSHOT_DIR,
    TRAINING_TRAJECTORY_DIR,
    TRAINING_TRAJECTORY_SCREENSHOT_DIR,
    PII_SANITIZATION_ENABLED,
    OPENROUTER_API_KEY,
)
from app_core.callbacks import (
    HITLCallback,
    HITLRejectedError,
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


# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------
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
_hitl_cb: HITLCallback | None = None
_trajectory_cb: TrajectorySaverCallback | None = None

# HITL takeover state — used when the agent is stuck and waiting for a
# manual click from the user.
_hitl_takeover_event = asyncio.Event()
_hitl_takeover_response: dict | None = None
_hitl_takeover_active = False


# ---------------------------------------------------------------------------
# HITL public API (called from WebSocket handler)
# ---------------------------------------------------------------------------

def submit_hitl_response(response: dict) -> None:
    """Route a HITL response from the frontend to the correct handler.

    For *approval* requests the HITLCallback itself holds the asyncio.Event.
    For *takeover* requests the module-level event is used.
    """
    global _hitl_takeover_response

    mode = response.get("mode", "")

    if mode == "approval" and _hitl_cb is not None and _hitl_cb.is_waiting:
        _hitl_cb.submit_response(response)
        return

    if mode == "takeover" and _hitl_takeover_active:
        _hitl_takeover_response = response
        _hitl_takeover_event.set()
        return

    # Cancel — stop any pending HITL
    if mode == "cancel":
        if _hitl_cb is not None and _hitl_cb.is_waiting:
            _hitl_cb.cancel()
        if _hitl_takeover_active:
            _hitl_takeover_response = {"action": "cancel"}
            _hitl_takeover_event.set()
        return

    logger.warning("HITL response received but no handler waiting: %s", response)


def is_hitl_waiting() -> bool:
    """Return True if the agent is paused waiting for human input."""
    return (
        (_hitl_cb is not None and _hitl_cb.is_waiting)
        or _hitl_takeover_active
    )


def get_hitl_state() -> dict | None:
    """Return the current pending HITL request payload, or None."""
    if _hitl_cb is not None and _hitl_cb.pending_request:
        return _hitl_cb.pending_request
    if _hitl_takeover_active:
        return {"mode": "takeover"}
    return None


# ---------------------------------------------------------------------------
# Training mode (Composed Grounding demonstrations)
# ---------------------------------------------------------------------------
_training_mode = False


def set_training_mode(enabled: bool) -> None:
    """Toggle training mode on or off.

    In training mode every agent action is gated for human approval so the
    user acts as the "planner" while the grounding model does the "seeing".
    Trajectories are saved to a dedicated demonstrations directory for
    fine-tuning the local UI-TARS model.
    """
    global _training_mode
    _training_mode = enabled
    if _hitl_cb is not None:
        _hitl_cb.training_mode = enabled
    # Swap trajectory directory so training demos are kept separate
    if _trajectory_cb is not None:
        if enabled:
            _trajectory_cb.trajectory_dir = Path(TRAINING_TRAJECTORY_DIR)
            _trajectory_cb.screenshot_dir = Path(TRAINING_TRAJECTORY_SCREENSHOT_DIR)
        else:
            _trajectory_cb.trajectory_dir = Path(TRAJECTORY_DIR)
            _trajectory_cb.screenshot_dir = Path(TRAJECTORY_SCREENSHOT_DIR)
    logger.info("Training mode %s", "enabled" if enabled else "disabled")


def is_training_mode() -> bool:
    return _training_mode


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

async def initialize():
    """Connect to the Cua computer server and create the composed agent."""
    global _computer, _agent, _ws_status_cb, _run_guard_cb, _pii_cb, _hitl_cb, _trajectory_cb

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
    # then HITL gating, then memory/image optimisation, then observability,
    # then housekeeping.
    _ws_status_cb = WebSocketStatusCallback()
    _run_guard_cb = RunGuardCallback()
    _pii_cb = PIISanitizerCallback(enabled=PII_SANITIZATION_ENABLED)
    _hitl_cb = HITLCallback(
        sensitive_actions=HITL_SENSITIVE_ACTIONS,
        approval_timeout=HITL_APPROVAL_TIMEOUT,
        enabled=HITL_ENABLED,
    )
    _hitl_cb.set_run_guard(_run_guard_cb)
    _trajectory_cb = TrajectorySaverCallback(
        trajectory_dir=TRAJECTORY_DIR,
        screenshot_dir=TRAJECTORY_SCREENSHOT_DIR,
    )

    callbacks = [
        # 1. Normalise malformed LLM output (hotkey→keypress, string keys→list, etc.)
        OperatorNormalizerCallback(),
        # 2. Security: intercept and block dangerous actions before execution
        SecurityInterceptionCallback(),
        # 3. Run guard: halt on consecutive wait() loops or wall-clock timeout
        _run_guard_cb,
        # 4. PII sanitization: mask personal data before cloud planning model calls
        _pii_cb,
        # 5. HITL: pause for approval on sensitive actions
        _hitl_cb,
        # 6. Memory safety: keep only N most recent screenshots in context
        ImageRetentionCallback(only_n_most_recent_images=IMAGE_RETENTION_COUNT),
        # 7. Image optimization: downscale/compress screenshots before LLM inference
        ImageOptimizerCallback(),
        # 8. Structured lifecycle logging
        LoggingCallback(level=logging.INFO),
        # 9. Audit trail: save full trajectory (screenshots, prompts, coordinates)
        _trajectory_cb,
        # 10. Broadcast detailed action status to WebSocket clients
        _ws_status_cb,
        # 11. Trim conversation history to prevent unbounded memory growth
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
        f"hitl={HITL_ENABLED}, "
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


# ---------------------------------------------------------------------------
# HITL takeover helper
# ---------------------------------------------------------------------------

async def _handle_takeover(broadcast: StatusCallback | None) -> bool:
    """Pause the task for a human takeover click.

    Takes a fresh screenshot, broadcasts a ``waiting_for_human`` message, and
    waits for the user to click on the screenshot.  Executes the click via the
    Computer tool and injects the result into history.

    Returns True if the takeover succeeded and the agent loop should resume,
    False if the user cancelled or it timed out.
    """
    global _hitl_takeover_active, _hitl_takeover_response

    if _computer is None:
        return False

    def _send(status: str, msg: str, **extra):
        if broadcast:
            broadcast(status, msg, **extra)

    # Take a fresh screenshot for the user to click on
    try:
        raw = await _computer.interface.screenshot()
        b64 = base64.b64encode(raw).decode("utf-8")
        screenshot_url = f"data:image/png;base64,{b64}"
    except Exception as e:
        logger.warning(f"Takeover screenshot failed: {e}")
        return False

    _hitl_takeover_event.clear()
    _hitl_takeover_response = None
    _hitl_takeover_active = True

    _send(
        "waiting_for_human",
        "Agent is stuck — click on the screen to help.",
        hitl={"mode": "takeover"},
        screenshot=screenshot_url,
    )
    logger.info("HITL takeover: waiting for user click")

    # Wait for user response
    try:
        await asyncio.wait_for(
            _hitl_takeover_event.wait(), timeout=HITL_APPROVAL_TIMEOUT
        )
    except asyncio.TimeoutError:
        _hitl_takeover_active = False
        logger.warning("HITL takeover timed out")
        _send("error", "Takeover timed out — no click received.")
        return False
    finally:
        _hitl_takeover_active = False

    response = _hitl_takeover_response
    if not response or response.get("action") == "cancel":
        _send("info", "Takeover cancelled by user.")
        return False

    # Execute the user's click
    x = response.get("x")
    y = response.get("y")
    if x is None or y is None:
        _send("error", "Invalid takeover click — missing coordinates.")
        return False

    try:
        await _computer.interface.click(x, y)
        _send("action", f"User clicked at ({x}, {y})")
        logger.info(f"HITL takeover: executed click at ({x}, {y})")
    except Exception as e:
        logger.warning(f"HITL takeover click failed: {e}")
        _send("error", f"Takeover click failed: {e}")
        return False

    # Inject the manual click + fresh screenshot into history
    seed_items = await _take_seeded_screenshot()
    if seed_items:
        _history.extend(seed_items)

    # Also inject a note so the planning model knows a human helped
    _history.append({
        "role": "user",
        "content": (
            "A human operator just clicked at the correct location for you. "
            "Continue with the task from the current screen state."
        ),
    })

    _send("info", "Takeover complete — resuming agent.")
    return True


# ---------------------------------------------------------------------------
# Main task runner
# ---------------------------------------------------------------------------

async def run_agent_task(prompt: str, broadcast: StatusCallback | None = None):
    """Run a natural language task through the composed ComputerAgent.

    Maintains conversation history for multi-turn context.
    Streams status updates via the broadcast callback.

    When HITL is enabled and the agent gets stuck (consecutive waits), the
    system enters takeover mode instead of erroring — allowing the user to
    perform a manual click and resume.
    """
    global _running, _spotlight_open

    if not is_ready():
        raise RuntimeError("Agent not initialized. Call initialize() first.")
    if _running:
        raise RuntimeError("Agent is already processing a task.")

    def _send(status: str, msg: str, **extra):
        if broadcast:
            broadcast(status, msg, **extra)

    _running = True
    _spotlight_open = False

    # Wire per-task broadcast into callbacks
    if _ws_status_cb is not None:
        _ws_status_cb.set_broadcast(broadcast)
    if _pii_cb is not None:
        _pii_cb.set_broadcast(broadcast)
    if _hitl_cb is not None:
        _hitl_cb.set_broadcast(broadcast)

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

        # ----- Agent loop with HITL takeover support -----
        takeover_attempts = 0

        while True:
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

            # --- Post-loop: check why the agent stopped ---
            if not (_run_guard_cb and _run_guard_cb.halt_reason):
                # Normal completion
                _send("done", "Task complete.")
                break

            halt = _run_guard_cb.halt_reason

            # Check if HITL takeover should kick in (stuck on consecutive waits)
            if (
                HITL_ENABLED
                and "consecutive wait" in halt
                and takeover_attempts < HITL_MAX_TAKEOVER_ATTEMPTS
            ):
                takeover_attempts += 1
                logger.info(
                    "HITL takeover triggered (attempt %d/%d): %s",
                    takeover_attempts, HITL_MAX_TAKEOVER_ATTEMPTS, halt,
                )
                if await _handle_takeover(broadcast):
                    # User performed a click — resume the agent loop
                    continue
                else:
                    # User cancelled or timed out — stop the task
                    _send("error", f"Task stopped: {halt}")
                    _history.append({
                        "role": "assistant",
                        "content": halt,
                    })
                    break
            else:
                # HITL disabled or max attempts exceeded — error as before
                _send("error", halt)
                _history.append({
                    "role": "assistant",
                    "content": halt,
                })
                break

    except HITLRejectedError as e:
        logger.info(f"Action rejected via HITL: {e}")
        _send("blocked", f"Action rejected: {e}")
        _history.append({
            "role": "assistant",
            "content": f"Action rejected by user: {e}",
        })
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
        if _hitl_cb is not None:
            _hitl_cb.set_broadcast(None)
        # Reclaim memory between turns — the grounding model allocates large
        # tensors that Python's refcount GC may not collect promptly.
        gc.collect()


def reset_history():
    """Clear the conversation history for a fresh start."""
    global _history
    _history = []
    # Cancel any pending HITL requests
    if _hitl_cb is not None:
        _hitl_cb.cancel()
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
