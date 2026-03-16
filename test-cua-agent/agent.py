"""
NoMachine Auto-Connect Agent
Uses CUA to launch a desktop sandbox, open NoMachine, and connect to a remote host.
"""

import asyncio
import os
from dotenv import load_dotenv
from computer import Computer
from agent import ComputerAgent, LLM, AgentLoop, LLMProvider

load_dotenv()

# --- Configuration ---
NOMACHINE_HOST = os.getenv("NOMACHINE_HOST", "192.168.1.100")
NOMACHINE_USER = os.getenv("NOMACHINE_USER", "user")
NOMACHINE_PASSWORD = os.getenv("NOMACHINE_PASSWORD", "password")
LLM_PROVIDER_NAME = os.getenv("LLM_PROVIDER", "ollama")


def get_llm() -> tuple[AgentLoop, LLM]:
    """Return the agent loop and LLM config based on the chosen provider."""
    if LLM_PROVIDER_NAME == "vllm":
        # UI-TARS via vLLM (best accuracy for GUI tasks, needs NVIDIA GPU)
        return AgentLoop.UITARS, LLM(
            provider=LLMProvider.OAICOMPAT,
            name=os.getenv("VLLM_MODEL", "ByteDance/UI-TARS-1.5-7B"),
            base_url=os.getenv("VLLM_BASE_URL", "http://localhost:8000/v1"),
            api_key="not-needed",
        )
    else:
        # Qwen 2.5 VL via Ollama (easier setup, runs on most hardware)
        return AgentLoop.OMNI, LLM(
            provider=LLMProvider.OLLAMA,
            name=os.getenv("OLLAMA_MODEL", "qwen2.5vl:7b"),
        )


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

    loop, model = get_llm()

    agent = ComputerAgent(
        computer=computer,
        loop=loop,
        model=model,
    )

    print(f"Starting NoMachine agent (provider={LLM_PROVIDER_NAME})...")
    print(f"Connecting to: {NOMACHINE_HOST} as {NOMACHINE_USER}")
    print("-" * 50)

    async with computer:
        async for result in agent.run(
            [{"role": "user", "content": PROMPT}],
        ):
            if hasattr(result, "text"):
                print(f"[Agent] {result.text}")
            else:
                print(f"[Step] {result}")

    print("-" * 50)
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
