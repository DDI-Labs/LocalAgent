import os

# Ollama
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5vl:3b")

# Agent behaviour
AGENT_MAX_STEPS = int(os.getenv("AGENT_MAX_STEPS", "30"))
AGENT_MAX_CONSECUTIVE_WAITS = int(os.getenv("AGENT_MAX_CONSECUTIVE_WAITS", "3"))

# Screenshot
SCREENSHOT_PATH = "/tmp/localagent_screenshot.png"
DEBUG_DIR = "/tmp/localagent_debug"
SCREENSHOT_MAX_DIM = int(os.getenv("SCREENSHOT_MAX_DIM", "768"))

# Server
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8001"))
