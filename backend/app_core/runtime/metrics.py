"""Per-stage timing instrumentation for agent runs.

Provides lightweight context-manager timers and a run-level metrics
collector so we can measure where latency actually goes.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class StepTimer:
    """Accumulates elapsed time for a named stage across multiple calls."""

    name: str
    total_ms: float = 0.0
    call_count: int = 0
    _start: float = 0.0

    def start(self) -> None:
        self._start = time.monotonic()

    def stop(self) -> float:
        elapsed = (time.monotonic() - self._start) * 1000
        self.total_ms += elapsed
        self.call_count += 1
        return elapsed

    @contextmanager
    def measure(self):
        """Context manager that records one timed span."""
        self.start()
        try:
            yield self
        finally:
            elapsed = self.stop()
            logger.debug(
                "[%s] %.0fms (total=%.0fms, calls=%d)",
                self.name, elapsed, self.total_ms, self.call_count,
            )


@dataclass
class RunMetrics:
    """Collects per-stage timings for a single run_agent_task() call."""

    screenshot: StepTimer = field(default_factory=lambda: StepTimer("screenshot"))
    image_opt: StepTimer = field(default_factory=lambda: StepTimer("image_opt"))
    planner: StepTimer = field(default_factory=lambda: StepTimer("planner"))
    grounding: StepTimer = field(default_factory=lambda: StepTimer("grounding"))
    callbacks: StepTimer = field(default_factory=lambda: StepTimer("callbacks"))
    macro: StepTimer = field(default_factory=lambda: StepTimer("macro"))
    skill_match: StepTimer = field(default_factory=lambda: StepTimer("skill_match"))
    action_exec: StepTimer = field(default_factory=lambda: StepTimer("action_exec"))
    total: StepTimer = field(default_factory=lambda: StepTimer("total"))

    prompt_tokens_total: int = 0
    completion_tokens_total: int = 0
    step_count: int = 0

    def summary(self) -> dict:
        """Return a dict suitable for logging or WebSocket broadcast."""
        timers = {
            t.name: {"ms": round(t.total_ms), "calls": t.call_count}
            for t in [
                self.screenshot, self.image_opt, self.planner,
                self.grounding, self.callbacks, self.macro,
                self.skill_match, self.action_exec, self.total,
            ]
            if t.call_count > 0
        }
        return {
            "timings": timers,
            "prompt_tokens": self.prompt_tokens_total,
            "completion_tokens": self.completion_tokens_total,
            "steps": self.step_count,
        }

    def log_summary(self) -> None:
        """Emit a single structured INFO log with the run summary."""
        s = self.summary()
        parts = [f"{k}={v['ms']}ms" for k, v in s["timings"].items()]
        parts.append(f"steps={s['steps']}")
        parts.append(f"prompt_tok={s['prompt_tokens']}")
        logger.info("Run metrics: %s", ", ".join(parts))
