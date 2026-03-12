"""Task regex patterns and system instructions for the macOS agent."""

import re

# System instructions for the model. Kept short to minimise prefill tokens.
MACOS_INSTRUCTIONS = (
    "You are controlling a macOS desktop. "
    "CRITICAL RULES:\n"
    "- To open apps: hotkey(key='command space'), then type(content='AppName'). "
    "Enter will be pressed automatically after typing.\n"
    "- Do NOT press enter yourself after typing in Spotlight. It is handled automatically.\n"
    "- Do NOT look for taskbar/dock icons. Use Spotlight only.\n"
    "- After typing an app name, wait() for the app to load.\n"
    "- When searching in apps like Spotify, YouTube, or browsers, use your knowledge "
    "to understand what the user means. For example, 'bohemian rhapsody' is a song by Queen, "
    "'Taylor Swift' is an artist, 'Dark Side of the Moon' is an album. "
    "After searching, click the correct category (Songs, Artists, Albums) if available, "
    "then click the correct result.\n"
)

# Regex to detect simple "open <app>" tasks (no further instructions).
OPEN_APP_PATTERN = re.compile(
    r"^(?:open|launch|start|run)\s+(.+?)(?:\s+app(?:lication)?)?$",
    re.IGNORECASE,
)

# Regex to detect compound tasks that START with opening an app, e.g.
# "open Spotify and play some music", "launch Safari and go to google.com".
# Group 1 = app name, Group 2 = the rest of the task after "and"/"then"/",".
OPEN_APP_THEN_PATTERN = re.compile(
    r"^(?:open|launch|start|run)\s+(.+?)\s+(?:and|then|,)\s+(.+)$",
    re.IGNORECASE,
)
