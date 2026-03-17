"""Platform and app adapters for deterministic action execution."""

from app_core.adapters.base import BaseAdapter, AdapterState, AdapterAction, AdapterResult
from app_core.adapters.browser import BrowserAdapter
from app_core.adapters.media import MediaAdapter
from app_core.adapters.macos_state import MacOSStateAdapter

__all__ = [
    "BaseAdapter",
    "AdapterState",
    "AdapterAction",
    "AdapterResult",
    "BrowserAdapter",
    "MediaAdapter",
    "MacOSStateAdapter",
]
