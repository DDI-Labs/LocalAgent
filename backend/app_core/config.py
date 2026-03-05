import os
from dotenv import load_dotenv

load_dotenv()

# Cua ComputerAgent settings
CUA_MODEL = os.getenv("CUA_MODEL", "mlx/mlx-community/UI-TARS-1.5-7B-6bit")
CUA_COMPUTER_SERVER_HOST = os.getenv("CUA_COMPUTER_SERVER_HOST", "localhost")
CUA_COMPUTER_SERVER_PORT = int(os.getenv("CUA_COMPUTER_SERVER_PORT", "5757"))

# WebSocket settings
WS_HEARTBEAT_INTERVAL = 30  # Seconds between keep-alive pings
