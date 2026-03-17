"""Base adapter interface for structured app/platform interaction.

Adapters expose deterministic high-level actions and structured state
for specific apps or platform capabilities, bypassing the vision loop
when accurate information is available.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AdapterState:
    """Structured state snapshot from an adapter."""

    adapter_name: str
    available: bool = False
    app_name: str | None = None
    title: str | None = None
    url: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class AdapterAction:
    """A deterministic action an adapter can perform."""

    name: str
    description: str
    parameters: dict[str, str] = field(default_factory=dict)


@dataclass
class AdapterResult:
    """Outcome of an adapter action."""

    success: bool
    message: str = ""
    new_state: AdapterState | None = None


class BaseAdapter(ABC):
    """Interface that all platform/app adapters must implement."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable adapter name."""

    @abstractmethod
    async def get_state(self) -> AdapterState:
        """Return the current structured state."""

    @abstractmethod
    def can_handle(self, prompt: str) -> bool:
        """Return True if this adapter can handle the given prompt."""

    @abstractmethod
    async def execute(self, prompt: str) -> AdapterResult:
        """Attempt to handle the prompt. Returns result."""

    @abstractmethod
    def available_actions(self) -> list[AdapterAction]:
        """List deterministic actions this adapter supports."""
