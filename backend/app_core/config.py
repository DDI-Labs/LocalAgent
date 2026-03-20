import os
from dotenv import load_dotenv

load_dotenv()

# Skip HuggingFace Hub metadata checks — model is already cached locally.
# This avoids a network round-trip on every startup.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
# Suppress HuggingFace Hub progress bars ("Fetching 13 files..." noise).
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
# Suppress tqdm progress bars from transformers/mlx_vlm during model loading.
os.environ.setdefault("TQDM_DISABLE", "1")

# ---------------------------------------------------------------------------
# Composed model configuration
# ---------------------------------------------------------------------------
# The grounding model runs locally (processes screenshots, identifies UI elements).
# The planning model runs in the cloud (decides actions from sanitized element text).
# CUA's composed_grounded loop joins them with "+" syntax automatically.

GROUNDING_MODEL = os.getenv(
    "GROUNDING_MODEL", "mlx/mlx-community/UI-TARS-1.5-7B-6bit"
)
PLANNING_MODEL = os.getenv(
    "PLANNING_MODEL", "openrouter/anthropic/claude-sonnet-4.5"
)

# Combined model string for ComputerAgent (grounding+planning).
# Override CUA_MODEL directly to use a single model instead of composed.
CUA_MODEL = os.getenv("CUA_MODEL", f"{GROUNDING_MODEL}+{PLANNING_MODEL}")

# OpenRouter API key — required when PLANNING_MODEL uses openrouter/ prefix.
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# Cua computer server connection (used when SANDBOX_ENABLED=false)
CUA_COMPUTER_SERVER_HOST = os.getenv("CUA_COMPUTER_SERVER_HOST", "localhost")
CUA_COMPUTER_SERVER_PORT = int(os.getenv("CUA_COMPUTER_SERVER_PORT", "5757"))

# ---------------------------------------------------------------------------
# Sandbox configuration
# ---------------------------------------------------------------------------
# Set SANDBOX_ENABLED=true to run actions inside a Cua sandbox instead of
# the local host computer server.  The grounding model still runs locally.
#
# Providers:
#   lume   — local macOS VM via Apple Virtualization Framework (no API key)
#   cloud  — Cua cloud sandbox (requires CUA_API_KEY)
#   docker — local Linux container (no API key)
#
# Example — Lume macOS VM:
#   SANDBOX_ENABLED=true
#   SANDBOX_PROVIDER=lume
#   SANDBOX_OS_TYPE=macos
#   SANDBOX_NAME=macos-sequoia-cua:latest
#
# Example — Cua cloud (Linux):
#   SANDBOX_ENABLED=true
#   SANDBOX_PROVIDER=cloud
#   SANDBOX_OS_TYPE=linux
#   SANDBOX_NAME=my-sandbox-123
#   CUA_API_KEY=sk_cua-api01_...
SANDBOX_ENABLED = os.getenv("SANDBOX_ENABLED", "false").lower() == "true"

# When SANDBOX_NAME is set and the lume daemon is available, automatically
# start the VM before connecting so the backend is self-contained.
LUME_AUTO_START = os.getenv("LUME_AUTO_START", "true").lower() == "true"
LUME_API_PORT = int(os.getenv("LUME_API_PORT", "7777"))

# AppleScript macros and local adapters only work when the computer server
# runs on the same machine. Automatically disabled for remote/VM setups.
MACOS_MACROS_ENABLED = (
    not SANDBOX_ENABLED
    and CUA_COMPUTER_SERVER_HOST in ("localhost", "127.0.0.1")
)

SANDBOX_PROVIDER = os.getenv("SANDBOX_PROVIDER", "lume")
SANDBOX_OS_TYPE = os.getenv("SANDBOX_OS_TYPE", "macos")
SANDBOX_NAME = os.getenv("SANDBOX_NAME", "macos-sequoia-cua:latest")
SANDBOX_DISPLAY = os.getenv("SANDBOX_DISPLAY", "1024x768")
SANDBOX_MEMORY = os.getenv("SANDBOX_MEMORY", "8GB")
SANDBOX_CPU = os.getenv("SANDBOX_CPU", "4")
CUA_API_KEY = os.getenv("CUA_API_KEY", "")

# ---------------------------------------------------------------------------
# PII sanitization
# ---------------------------------------------------------------------------
PII_SANITIZATION_ENABLED = os.getenv("PII_SANITIZATION_ENABLED", "true").lower() == "true"
# Skip NER for text shorter than this (regex-only). Avoids spaCy overhead on
# tiny strings like button labels ("OK", "Cancel") that dominate UI descriptions.
PII_NER_MIN_LENGTH = int(os.getenv("PII_NER_MIN_LENGTH", "40"))

# ---------------------------------------------------------------------------
# Memory & observability
# ---------------------------------------------------------------------------
# Max recent screenshots kept in the model's context window.
# With the composed pipeline, the grounding model needs to see recent state
# changes to avoid clicking the same wrong target repeatedly.  3 gives enough
# visual history without blowing up VRAM.  (Old value of 1 caused stuck loops
# because the model couldn't tell its click had no effect.)
IMAGE_RETENTION_COUNT = int(os.getenv("IMAGE_RETENTION_COUNT", "3"))

# ---------------------------------------------------------------------------
# MLX VRAM management
# ---------------------------------------------------------------------------
# Cap MLX memory usage to prevent the grounding model from starving other
# processes on the Mac.  Value is a fraction of total unified memory (0.0–1.0).
# Default 0.70 = 70%, leaving ~30% for OS, browser, and other apps.
MLX_MEMORY_LIMIT = float(os.getenv("MLX_MEMORY_LIMIT", "0.70"))

# Trajectory / audit trail directory (relative to project root).
TRAJECTORY_DIR = os.getenv("TRAJECTORY_DIR", "trajectories")
TRAJECTORY_SCREENSHOT_DIR = os.getenv("TRAJECTORY_SCREENSHOT_DIR", "trajectories/screenshots")
# Training mode saves gold-standard human demonstrations for fine-tuning.
TRAINING_TRAJECTORY_DIR = os.getenv("TRAINING_TRAJECTORY_DIR", "demonstrations")
TRAINING_TRAJECTORY_SCREENSHOT_DIR = os.getenv(
    "TRAINING_TRAJECTORY_SCREENSHOT_DIR", "demonstrations/screenshots"
)

# ---------------------------------------------------------------------------
# Human-in-the-Loop (HITL)
# ---------------------------------------------------------------------------
# Master toggle for HITL features (escalation on stuck loops + sensitive action gating).
HITL_ENABLED = os.getenv("HITL_ENABLED", "true").lower() == "true"
# Comma-separated keywords that trigger an approval prompt before the action executes.
# Matched case-insensitively against the planning model's reasoning and action content.
HITL_SENSITIVE_ACTIONS = [
    s.strip()
    for s in os.getenv(
        "HITL_SENSITIVE_ACTIONS",
        "Send,Delete,Confirm,Submit,Purchase,Remove,Trash,Pay,Uninstall",
    ).split(",")
    if s.strip()
]
# Seconds to wait for a human response before timing out and rejecting.
HITL_APPROVAL_TIMEOUT = int(os.getenv("HITL_APPROVAL_TIMEOUT", "120"))
# Maximum number of takeover attempts per task before giving up.
HITL_MAX_TAKEOVER_ATTEMPTS = int(os.getenv("HITL_MAX_TAKEOVER_ATTEMPTS", "3"))

# ---------------------------------------------------------------------------
# Demonstration-guided skills
# ---------------------------------------------------------------------------
# Directory containing SKILL.md files (relative to project root).
SKILL_LIBRARY_DIR = os.getenv("SKILL_LIBRARY_DIR", "skills")
# Minimum composite score (0.0–1.0) for a skill to match a user prompt.
SKILL_MATCH_THRESHOLD = float(os.getenv("SKILL_MATCH_THRESHOLD", "0.55"))

# WebSocket settings
WS_HEARTBEAT_INTERVAL = 30  # Seconds between keep-alive pings

# ---------------------------------------------------------------------------
# Telemetry
# ---------------------------------------------------------------------------
# Cua SDK collects anonymous usage stats by default (OS, run durations, token
# counts). Defaults to false here — set to true to allow collection.
CUA_TELEMETRY_ENABLED = os.getenv("CUA_TELEMETRY_ENABLED", "false").lower() == "true"

# ---------------------------------------------------------------------------
# Tracing
# ---------------------------------------------------------------------------
# Low-level computer interaction tracing — records every click/type/screenshot
# call with timing data, saved as ZIP archives alongside trajectories.
# Unlike trajectories (agent-level), tracing captures raw interface calls.
TRACING_ENABLED = os.getenv("TRACING_ENABLED", "false").lower() == "true"
TRACING_DIR = os.getenv("TRACING_DIR", "traces")

# ---------------------------------------------------------------------------
# Sandboxed Python & Interactive Shell
# ---------------------------------------------------------------------------
# Allow the planning model to execute Python code and shell commands directly
# in the connected VM/sandbox environment instead of going through the vision
# loop. Dramatically faster for data processing, file operations, and scripting.
SANDBOXED_PYTHON_ENABLED = os.getenv("SANDBOXED_PYTHON_ENABLED", "true").lower() == "true"
# Name of the persistent venv maintained inside the VM for agent code runs.
SANDBOXED_PYTHON_VENV = os.getenv("SANDBOXED_PYTHON_VENV", "agent_env")
INTERACTIVE_SHELL_ENABLED = os.getenv("INTERACTIVE_SHELL_ENABLED", "true").lower() == "true"
# Timeout (seconds) for a single shell command executed via PTY.
SHELL_COMMAND_TIMEOUT = int(os.getenv("SHELL_COMMAND_TIMEOUT", "30"))
