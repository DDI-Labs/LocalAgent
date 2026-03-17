"""Vision/planner fallback executor — wraps the existing composed agent loop.

This module encapsulates the expensive grounding+planning pipeline so that
the intent router and deterministic executor can hand off to it when they
cannot resolve a task on their own.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from agent import ComputerAgent
    from computer import Computer

from app_core.runtime.task_state import TaskState

logger = logging.getLogger(__name__)

StatusCallback = Callable[..., None]


class VisionFallbackExecutor:
    """Run the composed agent loop (grounding + planner) for a task.

    Wraps the logic previously inline in ``run_agent_task``'s while loop
    into a callable unit the router/executor can invoke.
    """

    def __init__(
        self,
        agent: "ComputerAgent",
        computer: "Computer",
    ):
        self._agent = agent
        self._computer = computer

    async def run(
        self,
        state: TaskState,
        broadcast: StatusCallback | None = None,
        open_app_fn: Any = None,
        auto_enter_fn: Any = None,
        run_guard_cb: Any = None,
        handle_takeover_fn: Any = None,
        hitl_enabled: bool = True,
        max_takeover: int = 3,
    ) -> None:
        """Execute the vision loop, updating *state* in place.

        This method replicates the while-loop logic from
        ``run_agent_task`` but reads and writes all mutable data through
        ``state`` instead of local variables.
        """
        def _send(status: str, msg: str, **extra):
            if broadcast:
                broadcast(status, msg, **extra)

        while True:
            async for result in self._agent.run(state.run_history):
                for item in result.get("output", []):
                    msg_type = item.get("type", "")
                    if msg_type == "message":
                        for block in item.get("content", []):
                            if block.get("type") == "text":
                                text = block["text"]
                                _send("action", text)
                                state.run_history.append(
                                    {"role": "assistant", "content": text}
                                )
                                state.final_outcome = text
                    elif msg_type == "computer_call":
                        action = item.get("action", {})
                        action_type = action.get("type", "unknown")
                        state.last_action = action
                        state.action_count += 1

                        if action_type == "keypress":
                            keys = action.get("keys", [])
                            if set(keys) in ({"command", "space"}, {"cmd", "space"}):
                                state.spotlight_open = True
                        elif action_type == "type" and state.spotlight_open:
                            app_name = action.get("content", "") or action.get("text", "")
                            if open_app_fn and app_name and await open_app_fn(app_name):
                                _send("action", f"Opened {app_name} (fast-path)")
                            elif auto_enter_fn:
                                await auto_enter_fn(self._computer)
                            state.spotlight_open = False

            # Post-loop: check why agent stopped
            if not (run_guard_cb and run_guard_cb.halt_reason):
                state.final_outcome = "Task complete."
                _send("done", state.final_outcome)
                return

            halt = run_guard_cb.halt_reason

            if (
                hitl_enabled
                and "consecutive wait" in halt
                and state.takeover_attempts < max_takeover
                and handle_takeover_fn
            ):
                state.takeover_attempts += 1
                state.human_intervened = True
                logger.info(
                    "HITL takeover (attempt %d/%d): %s",
                    state.takeover_attempts, max_takeover, halt,
                )
                if await handle_takeover_fn(broadcast, state.run_history):
                    continue
                else:
                    state.final_outcome = f"Task stopped: {halt}"
                    _send("error", state.final_outcome)
                    return
            else:
                state.final_outcome = halt
                _send("error", halt)
                return
