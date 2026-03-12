"""Custom callbacks for the LocalAgent ComputerAgent pipeline."""

from app_core.callbacks.history_trim import HistoryTrimCallback
from app_core.callbacks.image_optimizer import ImageOptimizerCallback
from app_core.callbacks.pii_sanitizer import PIISanitizerCallback
from app_core.callbacks.run_guard import RunGuardCallback
from app_core.callbacks.security import SecurityBlockedError, SecurityInterceptionCallback
from app_core.callbacks.ws_status import WebSocketStatusCallback

__all__ = [
    "HistoryTrimCallback",
    "ImageOptimizerCallback",
    "PIISanitizerCallback",
    "RunGuardCallback",
    "SecurityBlockedError",
    "SecurityInterceptionCallback",
    "WebSocketStatusCallback",
]
