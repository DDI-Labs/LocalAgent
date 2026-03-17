#!/usr/bin/env bash
# Setup script for the NoMachine CUA Agent
set -euo pipefail

echo "=== NoMachine CUA Agent Setup ==="

# 1. Check Python version (needs 3.12 or 3.13)
echo "[1/5] Checking Python..."
PYTHON=""
for candidate in python3.13 python3.12 python3; do
    if command -v "$candidate" &>/dev/null; then
        ver=$("$candidate" -c "import sys; print(f'{sys.version_info.minor}')")
        if [[ "$ver" -ge 12 && "$ver" -le 13 ]]; then
            PYTHON="$candidate"
            break
        fi
    fi
done
if [ -z "$PYTHON" ]; then
    echo "ERROR: Python 3.12 or 3.13 required. Install with:"
    echo "  sudo add-apt-repository ppa:deadsnakes/ppa"
    echo "  sudo apt install python3.13 python3.13-venv"
    exit 1
fi
echo "  Using: $PYTHON ($($PYTHON --version))"

# 2. Check Docker
echo "[2/5] Checking Docker..."
docker --version 2>/dev/null || { echo "ERROR: Docker is required"; exit 1; }

# 3. Create venv and install Python dependencies
echo "[3/5] Creating venv and installing dependencies..."
$PYTHON -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
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
echo "  2. Activate the venv:  source .venv/bin/activate"
echo "  3. Start vLLM:  vllm serve ByteDance/UI-TARS-1.5-7B --dtype half --max-model-len 4096"
echo "  4. Run the agent:  python3 agent.py"
echo ""
echo "  Or with Ollama instead of vLLM:"
echo "  3. ollama pull qwen2.5vl:7b"
echo "  4. python3 agent.py"
