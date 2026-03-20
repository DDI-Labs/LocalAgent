# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

LocalAgent is a macOS desktop automation system. Users type natural language prompts (e.g. "open Spotify and play music") and the system controls the desktop via screenshots + mouse/keyboard actions. It uses a **composed model pipeline**: a local vision model (UI-TARS) for grounding and a cloud model (Claude via OpenRouter) for planning, with PII sanitization between them.

## Running the Project

Requires **three terminals** running simultaneously:

```bash
# Terminal 1 — Cua Computer Server (desktop control daemon)
python -m computer_server
# localhost:5757

# Terminal 2 — Backend
cd backend && source venv/bin/activate && python main.py
# localhost:8000

# Terminal 3 — Frontend
cd frontend && bun run dev
# localhost:5173
```

### Setup

```bash
# Backend
cd backend && python -m venv venv && source venv/bin/activate && pip install -r requirements.txt
cp ../.env.example .env  # then fill in API keys

# Frontend
cd frontend && bun install
```

### Lint

```bash
cd frontend && npm run lint
```

## Architecture

```
Frontend (React, :5173) ──WebSocket──> Backend (FastAPI, :8000) ──HTTP──> Cua Computer Server (:5757)
```

**Composed model pipeline** (configured via `GROUNDING_MODEL` + `PLANNING_MODEL` env vars):
1. **Grounding** — UI-TARS 1.5 7B runs locally via MLX, processes screenshots, identifies UI elements
2. **PII Sanitization** — spaCy NER + regex masks personal data from grounding output
3. **Planning** — Claude Sonnet 4.5 via OpenRouter receives sanitized text, decides actions
4. **Execution** — Actions sent to Cua Computer Server for mouse/keyboard control

The model string uses `+` syntax for composed models: `mlx/...UI-TARS...+openrouter/anthropic/claude-sonnet-4.5`

**Fast-path macros** bypass the vision loop entirely for common tasks (opening apps, media controls) using AppleScript — ~1s vs ~20s/step.

### Backend (`backend/`)

- [main.py](backend/main.py) — FastAPI app, WebSocket `/ws` endpoint, lifespan management
- [app_core/agent.py](backend/app_core/agent.py) — ComputerAgent orchestrator: initializes composed model, runs agent loop, handles fast-path patterns
- [app_core/config.py](backend/app_core/config.py) — All env var configuration (model names, API keys, PII settings, memory limits)
- [api/routes.py](backend/api/routes.py) — HTTP endpoints: `/agent/status`, `/agent/run`, `/agent/reset`
- [api/websocket.py](backend/api/websocket.py) — WebSocket connection manager with broadcast
- [app_core/callbacks/](backend/app_core/callbacks/) — 10-stage callback pipeline (security, PII, image optimization, logging, trajectory saving, WebSocket status, etc.)
- [app_core/macros/](backend/app_core/macros/) — AppleScript automation: app opening, media control, Spotlight integration
- [app_core/sanitization/](backend/app_core/sanitization/) — PII detection (spaCy NER + regex) and reversible masking

### Frontend (`frontend/`)

- React 19 + TypeScript + Vite + Tailwind CSS v4
- [src/hooks/useAgentSocket.ts](frontend/src/hooks/useAgentSocket.ts) — WebSocket hook managing agent state, logs, screenshot data
- [src/components/ScreenshotViewer.tsx](frontend/src/components/ScreenshotViewer.tsx) — Shows agent's view with red click-dot overlay
- [src/components/ChatInput.tsx](frontend/src/components/ChatInput.tsx) — Prompt input with quick-action buttons

### WebSocket Protocol

Frontend sends: `{"type": "prompt", "content": "..."}` or `{"type": "reset"}`

Backend broadcasts: `{"status": "thinking|action|done|error|blocked|info", "msg": "...", "screenshot": "base64...", "click": {"x": N, "y": N}}`

## Modified System Packages (not in git)

These Cua library files have local patches that must be reapplied if packages are reinstalled:

1. `agent/adapters/mlxvlm_adapter.py` — `max_tokens`: 128 → 512; `generate()` return: unpack tuple → `result.text` (mlx_vlm now returns `GenerationResult` object)
2. `computer/interface/models.py` — `Key.COMMAND="cmd"`, `Key.OPTION="alt"`
3. `agent/loops/uitars.py` — `predict_click` regex: added `start_box` pattern
4. `agent/loops/composed_grounded.py` — `get_last_computer_call_image`: accept JPEG (was PNG-only)

After editing system packages, delete `__pycache__/*.pyc` to invalidate bytecode cache.

## Platform

macOS only — deep AppleScript integration for app control, Spotlight search, window management, and multi-monitor support.
