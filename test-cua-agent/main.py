"""
NoMachine Auto-Connect Agent
Uses CUA to launch a desktop sandbox, open NoMachine, and connect to a remote host.
"""

import asyncio
import os
from dotenv import load_dotenv
from computer import Computer
from agent import ComputerAgent

load_dotenv()

# Force Ollama's OpenAI-compatible endpoint for litellm
if os.getenv("LLM_PROVIDER", "ollama") == "ollama":
    os.environ.setdefault("OPENAI_API_KEY", "not-needed")
    os.environ.setdefault("OPENAI_API_BASE", "http://localhost:11434/v1")

import litellm
litellm.api_base = os.environ.get("OPENAI_API_BASE", None)

# Patch litellm.acompletion to always inject api_base for Ollama
_original_acompletion = litellm.acompletion
async def _patched_acompletion(*args, **kwargs):
    if "api_base" not in kwargs or kwargs["api_base"] is None:
        kwargs["api_base"] = litellm.api_base
    return await _original_acompletion(*args, **kwargs)
litellm.acompletion = _patched_acompletion

# --- Configuration ---
NOMACHINE_HOST = os.getenv("NOMACHINE_HOST", "192.168.1.100")
NOMACHINE_USER = os.getenv("NOMACHINE_USER", "user")
NOMACHINE_PASSWORD = os.getenv("NOMACHINE_PASSWORD", "password")
LLM_PROVIDER_NAME = os.getenv("LLM_PROVIDER", "ollama")


def get_model_string() -> str:
    """Return the model string based on the chosen provider."""
    if LLM_PROVIDER_NAME == "vllm":
        # UI-TARS via vLLM (best accuracy for GUI tasks, needs NVIDIA GPU)
        return os.getenv("VLLM_MODEL", "ByteDance/UI-TARS-1.5-7B")
    else:
        # Qwen 2.5 VL via Ollama using OpenAI-compatible endpoint (supports vision)
        return "omni+" + os.getenv("OLLAMA_MODEL", "openai/qwen2.5vl:7b")


PROMPT = f"""
1. Open the NoMachine application from the application menu or by running "nomachine" from a terminal.
2. Wait for NoMachine to fully load.
3. Click "New" to create a new connection.
4. Set the protocol to NX.
5. Enter the host address: {NOMACHINE_HOST}
6. Leave the port as default (4000) unless it needs changing.
7. Click "Continue" or "Next" through the configuration screens, keeping defaults.
8. When prompted, enter the username: {NOMACHINE_USER}
9. Enter the password: {NOMACHINE_PASSWORD}
10. Accept any host verification prompts or SSH fingerprint dialogs.
11. Click "Connect" and wait for the remote desktop session to appear.
12. Once connected, take a screenshot to confirm the remote desktop is visible.
"""


async def main():
    # Use the custom Docker image with NoMachine pre-installed
    computer = Computer(
        os_type="linux",
        provider_type="docker",
        image="cua-nomachine:latest",  # our custom image from docker/Dockerfile
        name="nomachine-agent",
    )

    model = get_model_string()

    agent = ComputerAgent(
        model=model,
        tools=[computer],
        api_base="http://localhost:11434" if LLM_PROVIDER_NAME == "ollama" else os.getenv("VLLM_BASE_URL", "http://localhost:8000/v1"),
    )

    print(f"Starting NoMachine agent (model={model})...")
    print(f"Connecting to: {NOMACHINE_HOST} as {NOMACHINE_USER}")
    print("-" * 50)

    async with computer:
        async for result in agent.run(PROMPT):
            if hasattr(result, "text"):
                print(f"[Agent] {result.text}")
            else:
                print(f"[Step] {result}")

    print("-" * 50)
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
