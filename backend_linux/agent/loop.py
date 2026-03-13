"""Core agent loop: screenshot -> model -> parse -> execute -> repeat."""

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Optional

from PIL import Image, ImageDraw, ImageFont

from cua import screenshot, executor, parser
from model import client
from agent.prompt import get_system_prompt, build_task_prompt
from config import AGENT_MAX_STEPS, AGENT_MAX_CONSECUTIVE_WAITS, DEBUG_DIR, SCREENSHOT_PATH, OLLAMA_MODEL

log = logging.getLogger(__name__)


class AgentLoop:
    """Runs the CUA agent loop for a single task."""

    def __init__(
        self,
        task_details: dict,
        on_status: Optional[Callable[[str, str], None]] = None,
        site: Optional[dict] = None,
    ):
        """
        Args:
            task_details: Extracted voice note details dict.
            on_status: Optional callback(status, message) for real-time updates.
                       status is one of: 'thinking', 'action', 'done', 'error'.
            site: Optional site dict (from sites.py) with app, credentials, etc.
        """
        self.task_details = task_details
        self.site = site
        self.on_status = on_status or (lambda s, m: None)
        self.messages: list[dict] = []
        self.step_count = 0
        self.consecutive_waits = 0
        self._last_action_sig: str = ""
        self._last_action_summary: str = ""
        self._consecutive_same_actions: int = 0
        self._stopped = False
        self._debug_dir = Path(DEBUG_DIR)
        self._setup_debug_dir()

    @staticmethod
    def _notify(outcome: str, reason: str, steps: int) -> None:
        """Send a desktop notification with the agent result."""
        icons = {"granted": "dialog-ok", "denied": "dialog-error",
                 "error": "dialog-warning", "stopped": "dialog-information",
                 "max_steps": "dialog-warning", "unknown": "dialog-question"}
        icon = icons.get(outcome, "dialog-information")
        urgency = "critical" if outcome in ("error", "denied") else "normal"
        title = f"LocalAgent — {outcome.upper()}"
        body = f"{reason}\n({steps} steps)"
        try:
            subprocess.Popen(
                ["notify-send", "-u", urgency, "-i", icon, title, body],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            log.debug("notify-send not available")

    def _setup_debug_dir(self) -> None:
        """Create/clean the debug directory for step-by-step screenshots."""
        if self._debug_dir.exists():
            shutil.rmtree(self._debug_dir)
        self._debug_dir.mkdir(parents=True)
        log.info("Debug screenshots: %s", self._debug_dir)

    def _save_debug_screenshot(self, step: int, action: parser.Action, response: str) -> None:
        """Save an annotated screenshot showing what the model decided to do."""
        try:
            img = Image.open(SCREENSHOT_PATH).copy()
            draw = ImageDraw.Draw(img)

            # Draw crosshair + circle at click target
            if action.x is not None and action.y is not None:
                x, y = action.x, action.y
                r = 30
                # Red circle
                draw.ellipse([x - r, y - r, x + r, y + r], outline="red", width=4)
                # Crosshair
                draw.line([x - r * 2, y, x + r * 2, y], fill="red", width=2)
                draw.line([x, y - r * 2, x, y + r * 2], fill="red", width=2)

                # Drag endpoint
                if action.x2 is not None and action.y2 is not None:
                    x2, y2 = action.x2, action.y2
                    draw.ellipse([x2 - r, y2 - r, x2 + r, y2 + r], outline="blue", width=4)
                    draw.line([x, y, x2, y2], fill="yellow", width=3)

            # Draw text label at the top
            thought = action.thought or ""
            label = f"Step {step}: {action.type}"
            if action.text:
                label += f"({action.text[:40]})"
            elif action.x is not None:
                label += f"({action.x}, {action.y})"

            # Background bar for text
            draw.rectangle([0, 0, img.width, 60], fill=(0, 0, 0, 180))
            draw.text((10, 5), label, fill="white")
            if thought:
                draw.text((10, 30), thought[:120], fill="yellow")

            # Save
            out_path = self._debug_dir / f"step_{step:02d}.png"
            img.save(str(out_path))

            # Also save as "latest.png" for live viewing
            latest_path = self._debug_dir / "latest.png"
            img.save(str(latest_path))

            log.info("Debug screenshot saved: %s", out_path)
        except Exception as e:
            log.warning("Failed to save debug screenshot: %s", e)

    def stop(self) -> None:
        """Signal the loop to stop after the current step."""
        self._stopped = True

    def _emit(self, status: str, msg: str) -> None:
        log.info("[%s] %s", status, msg)
        self.on_status(status, msg)

    def _build_initial_messages(self) -> list[dict]:
        task_prompt = build_task_prompt(self.task_details, site=self.site)
        return [
            {"role": "system", "content": get_system_prompt(OLLAMA_MODEL)},
            {"role": "user", "content": task_prompt},
        ]

    def run(self) -> dict:
        """Execute the agent loop. Returns a result dict.

        Returns:
            {
                "outcome": "granted" | "denied" | "error" | "stopped" | "max_steps",
                "reason": str,
                "steps": int,
            }
        """
        result = self._run_loop()
        self._notify(result["outcome"], result["reason"], result["steps"])
        return result

    def _run_loop(self) -> dict:
        """Internal loop — run() wraps this to add notifications."""
        self.messages = self._build_initial_messages()
        screen_w, screen_h = screenshot.get_screen_size()

        # Hide the terminal running the agent so it doesn't appear in screenshots
        executor.minimize_active_window()

        self._emit("thinking", "Starting task...")

        for step in range(1, AGENT_MAX_STEPS + 1):
            if self._stopped:
                return {"outcome": "stopped", "reason": "Agent stopped by user.", "steps": step}

            self.step_count = step
            self._emit("thinking", f"Step {step}/{AGENT_MAX_STEPS}: Taking screenshot...")

            # 1. Capture screenshot
            try:
                img_b64 = screenshot.capture_and_encode()
            except RuntimeError as e:
                self._emit("error", str(e))
                return {"outcome": "error", "reason": str(e), "steps": step}

            # 2. Send to model
            self._emit("thinking", f"Step {step}/{AGENT_MAX_STEPS}: Asking model...")

            # Include what was done last so the model doesn't repeat
            if self._last_action_summary:
                prompt = f"I executed: {self._last_action_summary}. Here is the updated screenshot. What is the single next action?"
            else:
                prompt = "Here is the current screenshot. What is the single next action?"

            self.messages.append({
                "role": "user",
                "content": prompt,
                "images": [img_b64],
            })

            # Build trimmed message list: system prompt + recent exchanges + latest screenshot
            # This prevents context blowup and degenerate repeated outputs.
            system_msgs = [m for m in self.messages if m["role"] == "system"]
            non_system = [m for m in self.messages if m["role"] != "system"]
            # Keep at most 10 non-system messages (5 user+assistant pairs)
            trimmed = non_system[-10:] if len(non_system) > 10 else non_system
            candidate = system_msgs + trimmed

            # Strip images from all but the latest user message
            messages_to_send = []
            for i, msg in enumerate(candidate):
                if "images" in msg and i < len(candidate) - 1:
                    msg = {k: v for k, v in msg.items() if k != "images"}
                messages_to_send.append(msg)

            _token_buf = []

            def _on_token(tok: str) -> None:
                _token_buf.append(tok)
                # Emit streaming preview every ~10 tokens
                if len(_token_buf) % 10 == 0:
                    partial = "".join(_token_buf)
                    self._emit("thinking", f"Step {step}: ...{partial[-80:]}")

            try:
                response = client.chat(messages_to_send, on_token=_on_token)
            except RuntimeError as e:
                if "GGML_ASSERT" in str(e):
                    # Context too large — aggressively trim and retry once
                    log.warning("GGML crash, retrying with minimal context")
                    self._emit("thinking", "Context too large, trimming and retrying...")
                    minimal = system_msgs + non_system[-4:]
                    messages_to_send = []
                    for i, msg in enumerate(minimal):
                        if "images" in msg and i < len(minimal) - 1:
                            msg = {k: v for k, v in msg.items() if k != "images"}
                        messages_to_send.append(msg)
                    try:
                        _token_buf.clear()
                        response = client.chat(messages_to_send, on_token=_on_token)
                    except RuntimeError as e2:
                        self._emit("error", str(e2))
                        return {"outcome": "error", "reason": str(e2), "steps": step}
                else:
                    self._emit("error", str(e))
                    return {"outcome": "error", "reason": str(e), "steps": step}

            # Add assistant response to conversation history
            self.messages.append({
                "role": "assistant",
                "content": response,
            })

            # 3. Parse actions (supports multi-action responses)
            try:
                actions = parser.parse_all(response, screen_w, screen_h)
            except Exception as e:
                log.warning("Failed to parse model output: %s — treating as wait", e)
                actions = [parser.Action(type="wait", thought=f"Parse error: {e}")]

            first_action = actions[0]

            # Save annotated debug screenshot (first action)
            self._save_debug_screenshot(step, first_action, response)

            if first_action.thought:
                self._emit("thinking", first_action.thought)

            # 4. Check for completion
            if first_action.type == "done":
                outcome, reason = self._extract_decision(first_action.thought or response)
                self._emit("done", f"Decision: {outcome.upper()} — {reason}")
                return {"outcome": outcome, "reason": reason, "steps": step}

            # 5. Check wait loop and repeated-action loop
            action_sig = f"{first_action.type}:{first_action.x},{first_action.y},{first_action.text}"
            if first_action.type == "wait":
                self.consecutive_waits += 1
                if self.consecutive_waits >= AGENT_MAX_CONSECUTIVE_WAITS:
                    self._emit("error", "Agent stuck in wait loop, stopping.")
                    return {
                        "outcome": "error",
                        "reason": "Stuck in wait loop.",
                        "steps": step,
                    }
            else:
                self.consecutive_waits = 0

            if action_sig == self._last_action_sig:
                self._consecutive_same_actions += 1
                if self._consecutive_same_actions >= 4:
                    self._emit("error", f"Agent stuck repeating same action: {action_sig}")
                    return {
                        "outcome": "error",
                        "reason": f"Stuck repeating: {action_sig}",
                        "steps": step,
                    }
                if self._consecutive_same_actions >= 2:
                    # Nudge the model with corrective guidance based on what it's stuck doing
                    nudge = (
                        f"STOP. Your action '{first_action.type}({self._action_summary(first_action)})' "
                        f"was repeated {self._consecutive_same_actions} times with no effect. "
                        "You MUST do something different.\n"
                    )
                    if first_action.type == "hotkey" and first_action.text and "super" in first_action.text.lower():
                        nudge += (
                            "The Activities launcher should be open now. "
                            "Your next action MUST be: type the application name. "
                            "Do NOT press super again."
                        )
                    elif first_action.type == "hotkey" and first_action.text and first_action.text.lower() in ("ctrl+c", "ctrl+z", "ctrl+d", "ctrl+q", "alt+f4"):
                        nudge += (
                            "STOP trying to close or interact with the terminal. "
                            "IGNORE the terminal completely. It does not exist. "
                            "Focus on opening the application you need using the super key."
                        )
                    elif first_action.type == "click":
                        nudge += (
                            "Clicking this position is not working. "
                            "Try a different position, or try using keyboard instead."
                        )
                    elif first_action.type == "type":
                        nudge += (
                            "Typing is not working. Make sure the right field is focused. "
                            "Try clicking the text field first, then type."
                        )
                    else:
                        nudge += "Try a completely different action or approach."
                    self.messages.append({"role": "user", "content": nudge})
                    self._emit("thinking", f"Nudging model: repeated {self._consecutive_same_actions}x")
            else:
                self._consecutive_same_actions = 0
            self._last_action_sig = action_sig

            # 6. Execute all actions from this response
            executed_summaries = []
            for i, action in enumerate(actions):
                label = f"Step {step}" if len(actions) == 1 else f"Step {step}.{i+1}"
                self._emit("action", f"{label}: {action.type}({self._action_summary(action)})")
                try:
                    self._execute(action)
                    executed_summaries.append(f"{action.type}({self._action_summary(action)})")
                except Exception as e:
                    self._emit("error", f"Action execution failed: {e}")
                    return {"outcome": "error", "reason": str(e), "steps": step}

            # Update action summary for context in next prompt
            self._last_action_summary = ", ".join(executed_summaries)

        self._emit("error", f"Reached max steps ({AGENT_MAX_STEPS}).")
        return {"outcome": "max_steps", "reason": "Max steps reached.", "steps": AGENT_MAX_STEPS}

    def _execute(self, action: parser.Action) -> None:
        """Dispatch an action to the executor."""
        match action.type:
            case "click":
                executor.click(action.x, action.y)
            case "double_click":
                executor.double_click(action.x, action.y)
            case "right_click":
                executor.right_click(action.x, action.y)
            case "type":
                executor.type_text(action.text)
            case "hotkey":
                executor.hotkey(action.text)
            case "scroll":
                executor.scroll(action.x, action.y, action.direction)
            case "drag":
                executor.drag(action.x, action.y, action.x2, action.y2)
            case "wait":
                executor.wait()

    def _extract_decision(self, text: str) -> tuple[str, str]:
        """Try to extract grant/deny decision from the model's conclusion."""
        lower = text.lower() if text else ""
        if "grant" in lower or "approve" in lower or "allow" in lower:
            return "granted", text
        elif "deny" in lower or "denied" in lower or "reject" in lower:
            return "denied", text
        return "unknown", text

    def _action_summary(self, action: parser.Action) -> str:
        """Short human-readable summary of an action."""
        match action.type:
            case "click" | "double_click" | "right_click":
                return f"{action.x}, {action.y}"
            case "type":
                return repr(action.text[:30]) if action.text else ""
            case "hotkey":
                return action.text or ""
            case "scroll":
                return f"{action.x}, {action.y}, {action.direction}"
            case "drag":
                return f"{action.x},{action.y} -> {action.x2},{action.y2}"
            case _:
                return ""
