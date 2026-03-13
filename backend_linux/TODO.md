# LocalAgent — Road to Demo-Ready

## P0 — Security (before any demo)
- [ ] Move credentials out of source code into `.env` file
- [ ] Fix `/sites` endpoint to use allowlist (only return id, name, app, description)
- [ ] Fix race condition — move agent creation inside `_agent_lock`

## P1 — Core Capability (makes the demo actually work)
- [ ] Add API-based model option (Claude/GPT-4V) as alternative to local Ollama
- [ ] Add human-in-the-loop escalation when agent gets stuck (see Improvement #2 below)
- [ ] Add task queue with retry (SQLite-backed, auto-retry with different strategy on failure)

## P2 — Reliability (stops it from crashing/hanging)
- [ ] Add agent execution timeout (configurable `AGENT_TIMEOUT_SECONDS`)
- [ ] Add timeout to scrot subprocess call (`timeout=10`)
- [ ] Add input validation with Pydantic models on `/run` and WebSocket endpoints
- [ ] Clamp parsed coordinates to screen bounds before executing
- [ ] Fix `/run` endpoint blocking — run agent in background thread like WebSocket does
- [ ] Fix `notify-send` Popen zombie leak — switch to `subprocess.run`
- [ ] Prune `self.messages` in-place (not just trim for sending) to prevent memory bloat

## P3 — Production Polish
- [ ] Add persistent decision audit log (SQLite: task_id, site, outcome, steps, duration, screenshots)
- [ ] Add `GET /status` endpoint to check if agent is running and its progress
- [ ] Use timestamped subdirectories for debug screenshots instead of nuking them each run
- [ ] Add scroll direction validation (reject anything other than up/down)
- [ ] Move magic numbers to config (sleep timings, model temperature, num_ctx, num_predict)
- [ ] Add success rate tracking / basic metrics (SQLite table: outcome, steps, duration per run)
- [ ] Log warning on empty model response instead of silently treating as wait
- [ ] Fix silent WebSocket send failures — log error and set disconnected flag

---

## Planned Improvements

### Improvement 1: Action History Context
Give the model a summary of its last N actions so it knows what it already tried.
Prevents loops, gives the model situational awareness across steps.

### Improvement 2: Interactive User Suggestions
When the agent gets stuck (repeat loop or uncertain), pause and prompt the user
for a natural-language suggestion (e.g., "click the NoMachine icon on the desktop").
The agent incorporates the suggestion as its next action context.

### Improvement 3: Learn-by-Demonstration
Record a human performing the task step-by-step:
screenshot → human action (click/type/etc.) → screenshot → ...
Store these as demonstration trajectories. The agent replays/references them
as few-shot examples for future runs on the same site/workflow.
