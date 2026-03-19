import os
import asyncio
from dotenv import load_dotenv
from computer import Computer
from agent import ComputerAgent

load_dotenv()

TASK = """
Find and open the NoMachine application on this computer.
Once NoMachine is open, look for available remote computer connections.
If there is a saved connection, double-click it to connect.
If there are no saved connections but you see options to create one, describe what you see.
Take your time and wait for windows to fully load before interacting.
"""

computer = Computer(use_host_computer_server=True)


async def main():
    await computer.run()
    try:
        agent = ComputerAgent(
            model="cua/anthropic/claude-sonnet-4.5",
            tools=[computer],
        )

        messages = [{"role": "user", "content": TASK}]

        async for result in agent.run(messages):
            for item in result.get("output", []):
                if item.get("type") == "message":
                    for content in item.get("content", []):
                        if isinstance(content, dict) and content.get("text"):
                            print(content["text"])
                elif item.get("type") == "action":
                    print(f"  -> {item}")
    finally:
        await computer.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
