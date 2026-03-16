#!/usr/bin/env bash
# Setup script for the NoMachine CUA Agent
set -euo pipefail

echo "=== NoMachine CUA Agent Setup ==="

# 1. Check Python version
echo "[1/5] Checking Python..."
python3 --version 2>/dev/null || { echo "ERROR: Python 3.12+ required"; exit 1; }

# 2. Check Docker
echo "[2/5] Checking Docker..."
docker --version 2>/dev/null || { echo "ERROR: Docker is required"; exit 1; }

# 3. Install Python dependencies
echo "[3/5] Installing Python dependencies..."
pip install -r requirements.txt

# 4. Build the custom Docker image with NoMachine
echo "[4/5] Building Docker image (cua-nomachine:latest)..."
docker build -t cua-nomachine:latest docker/

# 5. Create .env from example if it doesn't exist
if [ ! -f .env ]; then
    echo "[5/5] Creating .env from .env.example..."
    cp .env.example .env
    echo ">>> IMPORTANT: Edit .env with your NoMachine host, username, and password"
else
    echo "[5/5] .env already exists, skipping."
fi

echo ""
echo "=== Setup complete ==="
echo ""
echo "Next steps:"
echo "  1. Edit .env with your NoMachine connection details"
echo "  2. Start Ollama:  ollama serve"
echo "  3. Pull the model: ollama pull qwen2.5vl:7b"
echo "  4. Run the agent:  python3 agent.py"
