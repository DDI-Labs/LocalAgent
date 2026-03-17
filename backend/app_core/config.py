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

# Cua computer server connection
CUA_COMPUTER_SERVER_HOST = os.getenv("CUA_COMPUTER_SERVER_HOST", "localhost")
CUA_COMPUTER_SERVER_PORT = int(os.getenv("CUA_COMPUTER_SERVER_PORT", "5757"))

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
