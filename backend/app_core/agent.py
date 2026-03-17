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
    SKILL_LIBRARY_DIR,
    SKILL_MATCH_THRESHOLD,
)
from app_core.skills import SkillLibrary
from app_core.skills.compiler import compile_skill
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
from app_core.runtime.task_state import TaskState
from app_core.runtime.prompt_builder import PromptBuilder
from app_core.runtime.metrics import RunMetrics
from app_core.runtime.intent_router import IntentRouter, RouteResult
from app_core.runtime.fallback_executor import VisionFallbackExecutor
from app_core.runtime.observation import ObservationFusion
from app_core.runtime.guards import ConfidenceGuard
from app_core.adapters import BrowserAdapter, MediaAdapter, MacOSStateAdapter, BaseAdapter

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

# Skill library — loaded during initialize()
_skill_library: SkillLibrary | None = None

# Intent router and fallback executor — wired during initialize()
_intent_router: IntentRouter | None = None
_vision_fallback: VisionFallbackExecutor | None = None

# Adapters — instantiated during initialize()
_adapters: list[BaseAdapter] = []

# Observation and guard modules
_observation_fusion: ObservationFusion | None = None
_confidence_guard: ConfidenceGuard | None = None

# Skill preflight approval state — separate from takeover and action-level HITL.
# Used for task-scoped approval of approval_required skills.
_skill_approval_event = asyncio.Event()
_skill_approval_response: dict | None = None
_skill_approval_active = False

# Teach mode state — human demonstrates a task step-by-step on live screenshots.
_teach_active = False
_teach_steps: list[dict] = []
_teach_prompt: str = ""


# ---------------------------------------------------------------------------
# Teach mode public API (called from WebSocket handler)
# ---------------------------------------------------------------------------

async def teach_screenshot() -> str | None:
    """Take a screenshot and return base64. No model involved."""
    if _computer is None:
        return None
    try:
        raw = await _computer.interface.screenshot()
        return base64.b64encode(raw).decode("utf-8")
    except Exception as e:
        logger.warning(f"Teach screenshot failed: {e}")
        return None


async def teach_action(payload: dict) -> str | None:
    """Execute a single action and return a new screenshot.

    The payload uses ``action`` for the action type (since ``type`` is the
    WebSocket message type).  The recorded step normalises this to ``type``
    for compatibility with the skill converter.

    No model calls — the human is the planner.
    """
    global _teach_steps
    if _computer is None:
        return None

    action_type = payload.get("action", "") or payload.get("type", "")
    try:
        if action_type == "click":
            await _computer.interface.left_click(payload["x"], payload["y"])
        elif action_type == "type":
            await _computer.interface.type_text(payload.get("text", ""))
        elif action_type == "keypress":
            keys = payload.get("keys", [])
            if len(keys) > 1:
                await _computer.interface.hotkey(*keys)
            elif len(keys) == 1:
                await _computer.interface.press_key(keys[0])
        elif action_type == "wait":
            await asyncio.sleep(1.5)
    except Exception as e:
        logger.warning(f"Teach action failed: {e}")
        return None

    # Normalise step for the converter: use "type" as the action key
    step = {k: v for k, v in payload.items() if k not in ("type", "action")}
    step["type"] = action_type
    _teach_steps.append(step)
    logger.info("Teach step %d: %s", len(_teach_steps), step)
    return await teach_screenshot()


def start_teach(prompt: str) -> None:
    """Enter teach mode with the given prompt as the intended task."""
    global _teach_active, _teach_steps, _teach_prompt
    _teach_active = True
    _teach_steps = []
    _teach_prompt = prompt
    logger.info("Teach mode started — prompt: %s", prompt)


def cancel_teach() -> None:
    """Exit teach mode without saving."""
    global _teach_active, _teach_steps, _teach_prompt
    _teach_active = False
    _teach_steps = []
    _teach_prompt = ""
    logger.info("Teach mode cancelled.")


def is_teaching() -> bool:
    return _teach_active


def get_teach_steps() -> list[dict]:
    return list(_teach_steps)


def get_teach_prompt() -> str:
    return _teach_prompt


# ---------------------------------------------------------------------------
# HITL public API (called from WebSocket handler)
# ---------------------------------------------------------------------------

def submit_hitl_response(response: dict) -> None:
    """Route a HITL response from the frontend to the correct handler.

    For *approval* requests the HITLCallback itself holds the asyncio.Event.
    For *takeover* requests the module-level event is used.
    For *skill_approval* requests the skill preflight event is used.
    """
    global _hitl_takeover_response, _skill_approval_response

    mode = response.get("mode", "")

    if mode == "approval" and _hitl_cb is not None and _hitl_cb.is_waiting:
        _hitl_cb.submit_response(response)
        return

    if mode == "takeover" and _hitl_takeover_active:
        _hitl_takeover_response = response
        _hitl_takeover_event.set()
        return

    if mode == "skill_approval" and _skill_approval_active:
        _skill_approval_response = response
        _skill_approval_event.set()
        return

    # Cancel — stop any pending HITL
    if mode == "cancel":
        if _hitl_cb is not None and _hitl_cb.is_waiting:
            _hitl_cb.cancel()
        if _hitl_takeover_active:
            _hitl_takeover_response = {"action": "cancel"}
            _hitl_takeover_event.set()
        if _skill_approval_active:
            _skill_approval_response = {"approved": False, "reason": "cancelled"}
            _skill_approval_event.set()
        return

    logger.warning("HITL response received but no handler waiting: %s", response)


def is_hitl_waiting() -> bool:
    """Return True if the agent is paused waiting for human input."""
    return (
        (_hitl_cb is not None and _hitl_cb.is_waiting)
        or _hitl_takeover_active
        or _skill_approval_active
    )


def get_hitl_state() -> dict | None:
    """Return the current pending HITL request payload, or None."""
    if _hitl_cb is not None and _hitl_cb.pending_request:
        return _hitl_cb.pending_request
    if _hitl_takeover_active:
        return {"mode": "takeover"}
    if _skill_approval_active:
        return {"mode": "skill_approval"}
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
    global _computer, _agent, _ws_status_cb, _run_guard_cb, _pii_cb, _hitl_cb, _trajectory_cb, _skill_library, _intent_router, _vision_fallback, _adapters, _observation_fusion, _confidence_guard

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

    # Load the skill library
    _skill_library = SkillLibrary(Path(SKILL_LIBRARY_DIR), SKILL_MATCH_THRESHOLD)
    _skill_library.load()

    # Set up the vision fallback executor
    _vision_fallback = VisionFallbackExecutor(_agent, _computer)

    # Initialize adapters
    _adapters = [
        BrowserAdapter(),
        MediaAdapter(),
        MacOSStateAdapter(),
    ]

    # Initialize observation fusion and confidence guards
    _observation_fusion = ObservationFusion(adapters=_adapters)
    _confidence_guard = ConfidenceGuard()

    # Set up the intent router with ordered strategies
    _intent_router = IntentRouter()
    _intent_router.register("macro", _route_macro)
    _intent_router.register("adapter", _route_adapter)
    _intent_router.register("skill", _route_skill)

    logger.info(
        f"ComputerAgent initialized — model={CUA_MODEL}, "
        f"hitl={HITL_ENABLED}, "
        f"pii_sanitization={PII_SANITIZATION_ENABLED}, "
        f"image_retention={IMAGE_RETENTION_COUNT}, "
        f"skills={len(_skill_library.skills)}, "
        f"callbacks={len(callbacks)}, "
        f"router_strategies={_intent_router.strategy_names}"
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

async def _handle_takeover(
    broadcast: StatusCallback | None,
    history: list[dict],
) -> bool:
    """Pause the task for a human takeover click.

    Takes a fresh screenshot, broadcasts a ``waiting_for_human`` message, and
    waits for the user to click on the screenshot.  Executes the click via the
    Computer tool and injects the result into the provided *history* list.

    The caller passes the run-local history so that takeover data does not
    leak into the persistent ``_history``.

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

    # Inject the manual click + fresh screenshot into the run-local history
    seed_items = await _take_seeded_screenshot()
    if seed_items:
        history.extend(seed_items)

    # Also inject a note so the planning model knows a human helped
    history.append({
        "role": "user",
        "content": (
            "A human operator just clicked at the correct location for you. "
            "Continue with the task from the current screen state."
        ),
    })

    _send("info", "Takeover complete — resuming agent.")
    return True


# ---------------------------------------------------------------------------
# Skill preflight approval
# ---------------------------------------------------------------------------

async def _preflight_skill_approval(
    skill,
    broadcast: StatusCallback | None,
) -> bool:
    """Ask the user to approve an ``approval_required`` skill before execution.

    This is a *task-scoped* gate — it fires once before any actions run,
    unlike the action-scoped HITLCallback which fires per-action.

    Returns True if approved, False if rejected or timed out.
    """
    global _skill_approval_active, _skill_approval_response

    _skill_approval_event.clear()
    _skill_approval_response = None
    _skill_approval_active = True

    steps_preview = "\n".join(
        f"Step {s.index}: {s.description}" for s in skill.steps[:5]
    )

    if broadcast:
        broadcast(
            "waiting_for_human",
            f"Skill '{skill.name}' requires approval before executing.",
            hitl={
                "mode": "skill_approval",
                "action_description": f"Execute skill: {skill.name}\n{skill.description}",
                "matched_keyword": "skill_approval",
                "reasoning": steps_preview,
            },
        )
    logger.info("Skill preflight approval: waiting for user — %s", skill.name)

    try:
        await asyncio.wait_for(
            _skill_approval_event.wait(), timeout=HITL_APPROVAL_TIMEOUT
        )
    except asyncio.TimeoutError:
        _skill_approval_active = False
        logger.warning("Skill preflight approval timed out for: %s", skill.name)
        if broadcast:
            broadcast("info", f"Skill approval timed out — skipping: {skill.name}")
        return False
    finally:
        _skill_approval_active = False

    return bool(_skill_approval_response and _skill_approval_response.get("approved"))


# ---------------------------------------------------------------------------
# Routing strategies (registered in initialize())
# ---------------------------------------------------------------------------

async def _route_macro(state: TaskState) -> RouteResult:
    """Try to handle the task via AppleScript macros."""
    stripped = state.original_prompt.strip()

    # Compound: "open Spotify and play some music"
    compound = OPEN_APP_THEN_PATTERN.match(stripped)
    if compound:
        app_name = compound.group(1).strip().strip("'\"")
        remaining_task = compound.group(2).strip()
        state.current_app = app_name
        state.remaining_task = remaining_task

        if await open_app(app_name):
            state.app_opened_by_macro = True
            result = await try_app_action(app_name, remaining_task)
            if result:
                return RouteResult(
                    handled=True,
                    execution_layer="macro",
                    final_outcome=f"Opened {app_name} and {result.lower()}.",
                )
            # Macro opened app but couldn't handle the remaining task
            state.seed_items = await _take_seeded_screenshot()
            state.skill_query = remaining_task
            state.effective_prompt = (
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
            return RouteResult(handled=False, execution_layer="macro_partial")

    # Simple: "open Spotify"
    if OPEN_APP_PATTERN.match(stripped):
        app_name = OPEN_APP_PATTERN.match(stripped).group(1).strip().strip("'\"")
        state.current_app = app_name
        if await open_app(app_name):
            return RouteResult(
                handled=True,
                execution_layer="macro",
                final_outcome=f"Opened {app_name} via fast-path.",
            )

    return RouteResult(handled=False)


async def _route_adapter(state: TaskState) -> RouteResult:
    """Try to handle the task via a structured adapter."""
    for adapter in _adapters:
        if adapter.can_handle(state.effective_prompt):
            logger.info("Adapter '%s' can handle: %s", adapter.name, state.effective_prompt[:60])
            result = await adapter.execute(state.effective_prompt)
            if result.success:
                return RouteResult(
                    handled=True,
                    execution_layer=f"adapter:{adapter.name}",
                    final_outcome=result.message,
                )
            logger.info("Adapter '%s' attempted but failed: %s", adapter.name, result.message)
    return RouteResult(handled=False)


async def _route_skill(state: TaskState) -> RouteResult:
    """Try to match and set up a skill for execution."""
    if _skill_library is None:
        return RouteResult(handled=False)

    match_result = _skill_library.match(state.skill_query)
    if not match_result and state.skill_query != state.original_prompt:
        match_result = _skill_library.match(state.original_prompt)

    if not match_result:
        return RouteResult(handled=False)

    state.matched_skill, state.skill_score = match_result
    state.compiled_skill = _skill_library.get_compiled(state.matched_skill.name)
    if state.compiled_skill is None:
        state.compiled_skill = compile_skill(state.matched_skill)

    # Skill found but still needs to go through the vision loop with guidance.
    # The skill context is now on state for prompt_builder to use.
    return RouteResult(
        handled=False,
        execution_layer="skill",
    )


# ---------------------------------------------------------------------------
# Main task runner
# ---------------------------------------------------------------------------

async def run_agent_task(prompt: str, broadcast: StatusCallback | None = None):
    """Run a natural language task through the composed ComputerAgent.

    Execution priority (via IntentRouter):
      macro → adapter → compiled skill → vision/planner fallback.

    Uses a run-scoped ``TaskState`` so that skill preambles, transient
    screenshots, and takeover notes do not contaminate the persistent
    ``_history``.  Only the original user prompt and a concise final
    outcome are persisted after the run completes.
    """
    global _running

    if not is_ready():
        raise RuntimeError("Agent not initialized. Call initialize() first.")
    if _running:
        raise RuntimeError("Agent is already processing a task.")

    state = TaskState(original_prompt=prompt, effective_prompt=prompt, skill_query=prompt)
    metrics = RunMetrics()

    def _send(status: str, msg: str, **extra):
        if broadcast:
            broadcast(status, msg, **extra)

    _running = True

    # Reset per-task modules
    if _observation_fusion is not None:
        _observation_fusion.reset()
    if _confidence_guard is not None:
        _confidence_guard.reset()

    # Wire per-task broadcast into callbacks
    if _ws_status_cb is not None:
        _ws_status_cb.set_broadcast(broadcast)
    if _pii_cb is not None:
        _pii_cb.set_broadcast(broadcast)
    if _hitl_cb is not None:
        _hitl_cb.set_broadcast(broadcast)

    try:
        metrics.total.start()

        # --- Route through intent router ---
        with metrics.macro.measure():
            route = await _intent_router.route(state) if _intent_router else RouteResult()

        if route.handled:
            state.execution_layer = route.execution_layer
            state.final_outcome = route.final_outcome or "Task complete."
            _send("done", state.final_outcome)
            _history.append(state.history_summary())
            _history.append(state.outcome_summary())
            metrics.total.stop()
            metrics.log_summary()
            return

        # --- Skill preflight approval (if router resolved a skill match) ---
        if state.matched_skill:
            _send("info", f"Skill matched: {state.matched_skill.name} (score={state.skill_score:.2f})")
            if state.matched_skill.approval_required and HITL_ENABLED:
                approved = await _preflight_skill_approval(state.matched_skill, broadcast)
                if not approved:
                    state.final_outcome = f"Skill '{state.matched_skill.name}' rejected by user."
                    _send("blocked", state.final_outcome)
                    _history.append(state.history_summary())
                    _history.append(state.outcome_summary())
                    metrics.total.stop()
                    metrics.log_summary()
                    return

        # --- Build prompt via centralized builder ---
        state.execution_layer = route.execution_layer or ("skill" if state.matched_skill else "vision")
        enhanced_prompt = PromptBuilder.build(state)

        # --- Run-local history (does NOT pollute persistent _history) ---
        state.run_history = list(_history)
        state.run_history.append({"role": "user", "content": enhanced_prompt})

        if state.seed_items:
            state.run_history.extend(state.seed_items)
            logger.info("Seeded post-activation screenshot into run_history")

        _send("thinking", f"Processing: {state.effective_prompt[:80]}...")

        # --- Vision/planner fallback loop ---
        await _vision_fallback.run(
            state,
            broadcast=broadcast,
            open_app_fn=open_app,
            auto_enter_fn=auto_enter_after_type,
            run_guard_cb=_run_guard_cb,
            handle_takeover_fn=_handle_takeover,
            hitl_enabled=HITL_ENABLED,
            max_takeover=HITL_MAX_TAKEOVER_ATTEMPTS,
        )

        # --- Persist only concise summary to _history ---
        _history.append(state.history_summary())
        _history.append(state.outcome_summary())

    except HITLRejectedError as e:
        logger.info("Action rejected via HITL: %s", e)
        state.final_outcome = f"Action rejected by user: {e}"
        _send("blocked", f"Action rejected: {e}")
        _history.append(state.history_summary())
        _history.append(state.outcome_summary())
    except SecurityBlockedError as e:
        logger.warning("Action blocked by security policy: %s", e)
        state.final_outcome = f"Action blocked by security policy: {e}"
        _send("blocked", f"Security policy blocked an action: {e}")
        _history.append(state.history_summary())
        _history.append(state.outcome_summary())
    except Exception as e:
        logger.exception("Agent task failed")
        _send("error", f"Agent error: {e}")
    finally:
        _running = False
        metrics.total.stop()
        metrics.log_summary()
        logger.info("Task state: %s", state.to_log_dict())
        if _ws_status_cb is not None:
            _ws_status_cb.set_broadcast(None)
        if _pii_cb is not None:
            _pii_cb.set_broadcast(None)
        if _hitl_cb is not None:
            _hitl_cb.set_broadcast(None)
        gc.collect()


def reset_history():
    """Clear the conversation history for a fresh start."""
    global _history, _skill_approval_response
    _history = []
    # Cancel any pending HITL requests
    if _hitl_cb is not None:
        _hitl_cb.cancel()
    if _skill_approval_active:
        _skill_approval_response = {"approved": False, "reason": "reset"}
        _skill_approval_event.set()
    logger.info("Agent conversation history reset.")


def reload_skills() -> int:
    """Hot-reload the skill library from disk. Returns the number of loaded skills."""
    if _skill_library is not None:
        _skill_library.reload()
        logger.info("Skill library reloaded: %d skills", len(_skill_library.skills))
        return len(_skill_library.skills)
    return 0


def get_skills_info() -> list[dict]:
    """Return metadata for all loaded skills."""
    if _skill_library is None:
        return []
    return [
        {
            "name": s.name,
            "description": s.description,
            "trigger_phrases": s.trigger_phrases,
            "approval_required": s.approval_required,
            "steps": len(s.steps),
            "file": str(s.file_path),
        }
        for s in _skill_library.skills
    ]


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
