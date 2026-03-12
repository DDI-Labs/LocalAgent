"""macOS automation macros — AppleScript helpers, Spotlight, and task patterns."""

from app_core.macros.applescript import open_app, try_app_action, run_osascript
from app_core.macros.spotlight import auto_enter_after_type
from app_core.macros.patterns import (
    MACOS_INSTRUCTIONS,
    OPEN_APP_PATTERN,
    OPEN_APP_THEN_PATTERN,
)

__all__ = [
    "open_app",
    "try_app_action",
    "run_osascript",
    "auto_enter_after_type",
    "MACOS_INSTRUCTIONS",
    "OPEN_APP_PATTERN",
    "OPEN_APP_THEN_PATTERN",
]
