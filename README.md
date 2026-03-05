# LocalAgent

A local AI-powered desktop automation system for macOS. Control your desktop with natural language prompts — open apps, play music, navigate UIs — all powered by a local vision-language model running on-device.

Built with a FastAPI backend (Python) and a React frontend, connected via WebSocket for real-time status updates.

## Architecture

```
┌──────────────────────────────────────────┐
│         Frontend (React + Tailwind)      │
│         http://localhost:5173            │
│                                          │
│  ChatInput → useAgentSocket (WebSocket)  │
│  ProcessMonitor ← real-time logs         │
└──────────────┬───────────────────────────┘
               │ ws://localhost:8000/ws
               │ JSON: {status, msg}
┌──────────────▼───────────────────────────┐
│         Backend (FastAPI)                │
│         http://localhost:8000            │
│                                          │
│  agent.py      → task execution          │
│  osascript     → fast-path app control   │
│  image_optimizer → screenshot compression│
└──────────┬───────────────────────────────┘
           │ HTTP + Vision
┌──────────▼───────────────────────────────┐
│     Cua Computer Server (localhost:5757) │
│     UI-TARS-1.5-7B (MLX)                │
│                                          │
│  Screenshots → Vision encoder            │
│  Actions     → Mouse/keyboard control    │
└──────────────────────────────────────────┘
```

### How it works

1. You type a natural language prompt in the frontend (e.g. "open Spotify and play some music")
2. The backend first tries **fast-path macros** — AppleScript commands that execute instantly without the vision model
3. If no macro matches, the **ComputerAgent** takes over: it captures a screenshot, runs it through UI-TARS (a 7B vision-language model running locally via MLX), and decides what to click/type next
4. Actions are executed on the desktop via the Cua computer server
5. Status updates stream back to the frontend in real-time via WebSocket

### Key optimizations

- **App-opening fast-path**: `open Spotify` runs `osascript` directly (~1s) instead of the vision loop (~20s/step)
- **Media control macros**: play, pause, skip, shuffle for Spotify/Apple Music via AppleScript
- **Screenshot compression**: Retina screenshots are downscaled to 1280px and JPEG-compressed (typically 90% smaller) before hitting the model
- **Single-image context**: Only the most recent screenshot is sent to the model to minimize prefill time
- **Wait-loop breaker**: Automatically stops if the model gets stuck repeating `wait()` 3+ times

## Prerequisites

- **macOS** (uses AppleScript/osascript for automation)
- **Python 3.11+**
- **Node.js 18+** with [bun](https://bun.sh/) (or npm)
- **Cua Computer Server** (`pip install cua-computer-server`)

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/<your-username>/LocalAgent.git
cd LocalAgent
```

### 2. Backend

```bash
cd backend

# Create and activate a virtual environment (recommended)
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp ../.env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
```

### 3. Frontend

```bash
cd frontend

# Install dependencies
bun install

# (or npm install)
```

## Running

You need **three terminals**:

### Terminal 1 — Cua Computer Server

```bash
python -m computer_server
# Starts on localhost:5757
```

### Terminal 2 — Backend

```bash
cd backend
source venv/bin/activate
python main.py
# Starts on http://localhost:8000
```

### Terminal 3 — Frontend

```bash
cd frontend
bun run dev
# Starts on http://localhost:5173
```

Open **http://localhost:5173** in your browser.

## Project structure

```
LocalAgent/
├── backend/
│   ├── main.py                 # FastAPI entry point, WebSocket /ws endpoint
│   ├── requirements.txt        # Python dependencies
│   ├── api/
│   │   ├── routes.py           # HTTP endpoints (/agent/status, /run, /reset)
│   │   └── websocket.py        # WebSocket connection manager
│   └── app_core/
│       ├── agent.py            # ComputerAgent logic, fast-path macros
│       ├── config.py           # CUA_MODEL, server host/port
│       └── image_optimizer.py  # Screenshot downscale + JPEG compression
│
├── frontend/
│   ├── package.json
│   ├── vite.config.ts          # Vite + Tailwind v4
│   └── src/
│       ├── App.tsx             # Main layout
│       ├── hooks/
│       │   └── useAgentSocket.ts   # WebSocket hook
│       └── components/
│           ├── ChatInput.tsx        # Prompt input + quick actions
│           ├── ProcessMonitor.tsx   # Real-time log viewer
│           ├── StatCards.tsx        # Status dashboard
│           └── Sidebar.tsx          # Navigation
│
├── .env.example                # Environment variable template
└── .gitignore
```

## WebSocket protocol

**Frontend sends:**
```json
{"type": "prompt", "content": "open Spotify and play music"}
{"type": "reset"}
```

**Backend broadcasts:**
```json
{"status": "thinking", "msg": "Opening Spotify directly..."}
{"status": "action",   "msg": "Opened Spotify (fast-path)"}
{"status": "done",     "msg": "Opened Spotify and started playback."}
{"status": "error",    "msg": "Agent stuck in wait loop, stopping task."}
```

## Configuration

All backend config lives in `backend/app_core/config.py` and can be overridden via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `CUA_MODEL` | `mlx/mlx-community/UI-TARS-1.5-7B-6bit` | Vision-language model |
| `CUA_COMPUTER_SERVER_HOST` | `localhost` | Cua server host |
| `CUA_COMPUTER_SERVER_PORT` | `5757` | Cua server port |
| `ANTHROPIC_API_KEY` | — | Required by cua-agent |

## Tech stack

| Layer | Technology |
|-------|------------|
| Frontend | React 19, TypeScript, Vite 7, Tailwind CSS v4 |
| Backend | FastAPI, Python 3.12, WebSocket |
| AI Model | UI-TARS-1.5-7B (MLX, runs locally) |
| Desktop control | Cua Computer Server, AppleScript |
| Icons | Lucide React |

## License

MIT
