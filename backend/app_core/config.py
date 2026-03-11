import os
from dotenv import load_dotenv

load_dotenv()

# Skip HuggingFace Hub metadata checks — model is already cached locally.
# This avoids a network round-trip on every startup.
os.environ.setdefault("HF_HUB_OFFLINE", "1")

# Cua ComputerAgent settings
CUA_MODEL = os.getenv("CUA_MODEL", "mlx/mlx-community/UI-TARS-1.5-7B-6bit")
CUA_COMPUTER_SERVER_HOST = os.getenv("CUA_COMPUTER_SERVER_HOST", "localhost")
CUA_COMPUTER_SERVER_PORT = int(os.getenv("CUA_COMPUTER_SERVER_PORT", "5757"))

# Memory safety — max recent screenshots kept in the model's context window.
# Keeps RAM stable during long multi-step tasks.  1 is aggressive but safe for
# the 7B model on a MacBook with limited unified memory.
IMAGE_RETENTION_COUNT = int(os.getenv("IMAGE_RETENTION_COUNT", "1"))

# Trajectory / audit trail directory (relative to project root).
TRAJECTORY_DIR = os.getenv("TRAJECTORY_DIR", "trajectories")
TRAJECTORY_SCREENSHOT_DIR = os.getenv("TRAJECTORY_SCREENSHOT_DIR", "trajectories/screenshots")

# WebSocket settings
WS_HEARTBEAT_INTERVAL = 30  # Seconds between keep-alive pings
