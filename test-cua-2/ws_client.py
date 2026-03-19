import asyncio
import json
import sys

import websockets

SERVER_URL = "ws://localhost:8765"


async def receive_loop(ws):
    """Print incoming messages from the server."""
    try:
        async for raw in ws:
            msg = json.loads(raw)
            msg_type = msg.get("type")

            if msg_type == "ready":
                print("[server] Ready for tasks.")
            elif msg_type == "message":
                print(f"[agent] {msg['text']}")
            elif msg_type == "action":
                print(f"[action] {msg.get('detail', '')}")
            elif msg_type == "done":
                print(f"\n[done] {msg.get('summary', 'Task completed.')}\n")
            elif msg_type == "cancelled":
                print(f"\n[cancelled] {msg.get('message', '')}\n")
            elif msg_type == "error":
                print(f"\n[error] {msg['message']}\n")
            else:
                print(f"[unknown] {msg}")
    except websockets.ConnectionClosed:
        print("[disconnected] Server closed the connection.")


async def main():
    print(f"Connecting to {SERVER_URL}...")
    try:
        async with websockets.connect(SERVER_URL) as ws:
            receiver = asyncio.create_task(receive_loop(ws))

            loop = asyncio.get_event_loop()
            while True:
                try:
                    line = await loop.run_in_executor(None, lambda: input(">>> "))
                except EOFError:
                    break

                line = line.strip()
                if not line:
                    continue

                if line == "/quit":
                    break
                elif line == "/cancel":
                    await ws.send(json.dumps({"type": "cancel"}))
                elif line == "/help":
                    print("Commands:")
                    print("  <task text>  - Send a task to the agent")
                    print("  /cancel      - Cancel the running task")
                    print("  /quit        - Disconnect and exit")
                    print("  /help        - Show this help")
                else:
                    await ws.send(json.dumps({"type": "task", "content": line}))

            receiver.cancel()
    except ConnectionRefusedError:
        print(f"Could not connect to {SERVER_URL}. Is ws_server.py running?")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
