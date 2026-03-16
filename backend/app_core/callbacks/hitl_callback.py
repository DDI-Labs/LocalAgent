"""Human-in-the-Loop callback — pauses for approval on sensitive actions.

Integrates with the agent callback pipeline to intercept actions that match a
configurable "sensitive action" keyword list.  When a match is found the
callback broadcasts a ``waiting_for_human`` status over the WebSocket and
blocks the agent loop until the user approves or rejects.

The callback captures context from ``on_llm_start`` (the messages sent to the
planning model, which include the grounding model's UI element descriptions)
and checks it against the keyword list in ``on_computer_call_start``.

Training mode:
  When ``training_mode`` is True, *every* action is gated for approval — not
  just sensitive ones.  The grounding model's UI element descriptions are
  broadcast alongside each approval request so the user can see what the model
  "sees" and make informed planning decisions.  The resulting trajectories
  serve as gold-standard demonstrations for fine-tuning the local model.
"""

import asyncio
import logging
from typing import Any, Callable, Dict, List

from agent.callbacks.base import AsyncCallbackHandler

logger = logging.getLogger(__name__)

StatusCallback = Callable[..., None]


class HITLRejectedError(RuntimeError):
    """Raised when a user rejects a sensitive action via HITL."""


class HITLCallback(AsyncCallbackHandler):
    """Intercepts sensitive actions and pauses for human approval."""

    def __init__(
        self,
        sensitive_actions: list[str],
        approval_timeout: float = 120.0,
        enabled: bool = True,
    ):
        self.sensitive_actions = [kw.lower() for kw in sensitive_actions]
        self.approval_timeout = approval_timeout
        self.enabled = enabled
        self.training_mode = False

        self._broadcast: StatusCallback | None = None

        # Captured from the most recent on_llm_start — contains grounding
        # model output and planning context so we can match keywords.
        self._last_context: str = ""
        # Latest screenshot extracted from on_llm_start messages so we can
        # include it in the waiting_for_human broadcast (the ws_status
        # callback runs after HITL in the pipeline and would never fire).
        self._last_screenshot: str | None = None

        # Approval synchronisation
        self._event = asyncio.Event()
        self._response: dict | None = None
        self._pending: dict | None = None

        # Optional reference to RunGuardCallback so we can pause its
        # wall-clock timer while waiting for human input.
        self._run_guard: Any | None = None

    # -- wiring ---------------------------------------------------------------

    def set_broadcast(self, broadcast: StatusCallback | None) -> None:
        self._broadcast = broadcast

    def set_run_guard(self, run_guard: Any) -> None:
        """Link to the RunGuardCallback to pause its timer during HITL waits."""
        self._run_guard = run_guard

    # -- public state ---------------------------------------------------------

    @property
    def is_waiting(self) -> bool:
        return self._pending is not None

    @property
    def pending_request(self) -> dict | None:
        return self._pending

    # -- external entry point -------------------------------------------------

    def submit_response(self, response: dict) -> None:
        """Called by the WebSocket handler when the user responds."""
        self._response = response
        self._event.set()

    def cancel(self) -> None:
        """Cancel any pending HITL request (e.g. on task reset)."""
        if self._pending:
            self._response = {"approved": False, "reason": "cancelled"}
            self._event.set()

    # -- callback hooks -------------------------------------------------------

    async def on_run_start(
        self, kwargs: Dict[str, Any], old_items: List[Dict[str, Any]]
    ) -> None:
        self._last_context = ""
        self._last_screenshot = None
        self._pending = None
        self._response = None

    async def on_llm_start(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Capture context and latest screenshot from LLM messages.

        In the composed pipeline the messages include grounding model output
        which describes UI elements (e.g. "Send button at (450, 600)").
        We also extract the most recent screenshot so we can include it in
        the ``waiting_for_human`` broadcast — the ws_status callback runs
        later in the pipeline and would not fire while HITL is blocking.

        Must return the messages list — the CUA framework chains callbacks
        and passes the return value to the next callback.
        """
        parts: list[str] = []
        for msg in messages[-5:]:  # last 5 messages for context
            content = msg.get("content", "")
            if isinstance(content, str):
                parts.append(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            parts.append(block["text"])
                        # input_image in user content blocks
                        elif block.get("type") == "input_image" and block.get("image_url"):
                            self._last_screenshot = block["image_url"]
            # computer_call_output format (nested output)
            if msg.get("type") == "computer_call_output":
                output = msg.get("output", {})
                if isinstance(output, dict) and output.get("type") == "input_image":
                    url = output.get("image_url", "")
                    if url:
                        self._last_screenshot = url
        self._last_context = " ".join(parts)
        return messages

    async def on_computer_call_start(self, item: Dict[str, Any]) -> None:
        if not self.enabled:
            return

        action = item.get("action", {})
        desc = _describe_action(action)

        # Extract proposed click coordinates for click actions so the
        # frontend can display where the agent wants to click.
        proposed_click = None
        if action.get("type") in ("click", "double_click"):
            cx, cy = action.get("x"), action.get("y")
            if cx is not None and cy is not None:
                proposed_click = {"x": cx, "y": cy}

        # In training mode, gate every action for human approval.
        if self.training_mode:
            matched = "training"
        else:
            matched = self._match_sensitive(action)
            if matched is None:
                return

        # --- Pause for approval -----------------
        self._pending = {
            "mode": "approval",
            "action_description": desc,
            "matched_keyword": matched,
            "reasoning": self._last_context[-500:],
            "training_mode": self.training_mode,
            "proposed_click": proposed_click,
        }
        self._event.clear()
        self._response = None

        label = "Training step" if self.training_mode else "Approval needed"
        logger.info("HITL %s: %s (keyword=%s)", label.lower(), desc, matched)

        if self._broadcast:
            extra: Dict[str, Any] = {"hitl": self._pending}
            if self._last_screenshot:
                extra["screenshot"] = self._last_screenshot
            self._broadcast(
                "waiting_for_human",
                f"{label}: {desc}" + (f" (detected: \"{matched}\")" if not self.training_mode else ""),
                **extra,
            )

        # Pause the run-guard wall-clock timer while we wait for human input.
        if self._run_guard:
            self._run_guard.pause_timer()

        # Block the agent loop until the user responds.
        # Training mode waits indefinitely; normal approval has a timeout.
        try:
            if self.training_mode:
                await self._event.wait()
            else:
                try:
                    await asyncio.wait_for(
                        self._event.wait(), timeout=self.approval_timeout
                    )
                except asyncio.TimeoutError:
                    self._pending = None
                    logger.warning("HITL approval timed out for: %s", desc)
                    if self._broadcast:
                        self._broadcast("info", f"Approval timed out — action rejected: {desc}")
                    raise HITLRejectedError(f"HITL approval timed out: {desc}")
        finally:
            if self._run_guard:
                self._run_guard.resume_timer()

        self._pending = None

        if self._response and self._response.get("approved"):
            logger.info("HITL approved: %s", desc)
            if self._broadcast:
                self._broadcast("info", f"Action approved by user: {desc}")
            return

        # Correction — user rejected but provided the correct click location.
        # Mutate the action in-place so the framework executes at the
        # corrected coordinates instead of the original ones.
        if self._response and self._response.get("correction"):
            correction = self._response["correction"]
            action["x"] = correction["x"]
            action["y"] = correction["y"]
            corrected_desc = f"Click at ({correction['x']}, {correction['y']})"
            logger.info("HITL correction applied: %s → %s", desc, corrected_desc)
            if self._broadcast:
                self._broadcast("info", f"Correction applied: {corrected_desc}")
            return  # Execute the corrected action

        # Rejected or cancelled
        reason = (self._response or {}).get("reason", "rejected by user")
        logger.info("HITL rejected: %s (%s)", desc, reason)
        if self._broadcast:
            self._broadcast("info", f"Action rejected: {desc}")
        raise HITLRejectedError(f"User rejected action: {desc}")

    # -- internals ------------------------------------------------------------

    def _match_sensitive(self, action: dict) -> str | None:
        """Return the first matched keyword or None."""
        # Build text to check: action content + captured planning context
        parts: list[str] = []

        action_type = action.get("type", "")
        if action_type == "type":
            parts.append(action.get("text", "") or action.get("content", ""))
        elif action_type == "keypress":
            parts.append(" ".join(action.get("keys", [])))

        parts.append(self._last_context)
        check = " ".join(parts).lower()

        for kw in self.sensitive_actions:
            if kw in check:
                return kw
        return None


def _describe_action(action: dict) -> str:
    """Human-readable description of an agent action."""
    t = action.get("type", "unknown")
    if t == "click":
        return f"Click at ({action.get('x', '?')}, {action.get('y', '?')})"
    if t == "double_click":
        return f"Double-click at ({action.get('x', '?')}, {action.get('y', '?')})"
    if t == "type":
        text = action.get("text", "") or action.get("content", "")
        preview = text[:60] + "..." if len(text) > 60 else text
        return f'Type: "{preview}"'
    if t == "keypress":
        return f"Press: {' + '.join(action.get('keys', []))}"
    if t == "scroll":
        return "Scroll"
    return f"Action: {t}"
