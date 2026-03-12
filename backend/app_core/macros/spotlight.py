"""Spotlight auto-enter injection.

The 7B grounding model consistently fails to press Enter after typing in
Spotlight, so we inject it automatically when we detect the pattern:
    hotkey(command space) → type(text) → [auto Enter]
"""

import asyncio
import logging

logger = logging.getLogger(__name__)


async def auto_enter_after_type(computer) -> None:
    """Press Enter automatically after typing in Spotlight.

    Args:
        computer: The Cua Computer instance with an active interface.
    """
    if computer and computer.interface:
        logger.info("Auto-injecting Enter keypress after Spotlight type")
        await asyncio.sleep(0.3)  # Brief pause for search results to appear
        await computer.interface.press_key("enter")
        await asyncio.sleep(1.0)  # Wait for app to launch
