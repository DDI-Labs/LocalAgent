"""WebSocket manager for real-time status broadcasting."""

import json
from fastapi import WebSocket


class ConnectionManager:
    """Manages active WebSocket connections and broadcasts status updates."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, status: str, msg: str, **extra):
        """Send a status update to all connected clients.

        Optional extra fields (e.g. screenshot, click) are merged into the
        JSON payload so the frontend can display richer data.
        """
        payload = json.dumps({"status": status, "msg": msg, **extra})
        stale = []
        for connection in self.active_connections:
            try:
                await connection.send_text(payload)
            except Exception:
                stale.append(connection)
        for conn in stale:
            self.active_connections.remove(conn)


# Singleton instance used across the application
manager = ConnectionManager()
