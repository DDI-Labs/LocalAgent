"""
NoMachine Auto-Connect Agent
Uses CUA to launch a desktop sandbox, open NoMachine, and connect to a remote host.
"""

import os
import asyncio
from dotenv import load_dotenv

load_dotenv()

from computer import Computer
from agent import ComputerAgent

# --- Configuration ---
NOMACHINE_HOST = os.getenv("NOMACHINE_HOST", "192.168.1.100")
NOMACHINE_USER = os.getenv("NOMACHINE_USER", "user")
NOMACHINE_PASSWORD = os.getenv("NOMACHINE_PASSWORD", "password")

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
    computer = Computer(
        os_type="linux",
        provider_type="docker",
        image="cua-nomachine:latest",
        name="nomachine-agent",
        timeout=300,
    )

    model = "huggingface-local/ByteDance-Seed/UI-TARS-1.5-7B"

    agent = ComputerAgent(
        model=model,
        tools=[computer],
    )

    print(f"Starting NoMachine agent (model={model})...")
    print(f"Connecting to: {NOMACHINE_HOST} as {NOMACHINE_USER}")
    print("-" * 50)

    async with computer:
        async for result in agent.run(PROMPT):
            if hasattr(result, "text"):
                print(f"[Agent] {result.text}")
            else:
                # Truncate base64 image data in output
                s = str(result)
                while "data:image/" in s:
                    start = s.index("data:image/")
                    end = s.find("'", start)
                    if end == -1:
                        end = s.find('"', start)
                    if end != -1:
                        s = s[:start] + "<image>" + s[end:]
                    else:
                        break
                print(f"[Step] {s}")

    print("-" * 50)
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
