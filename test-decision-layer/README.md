# Test Decision Layer Prototype

This is a clean-slate prototype for routing lost-ticket checks to one of:

- `api`
- `cua`
- `openclaw`

The router reads building-specific config and returns:

- `Accepted`
- `Denied`
- `Delegating to openclaw` (exactly, for `openclaw` routes)

No third-party dependencies are required.

## Quick Start

```bash
cd /home/uthp/Documents/Projects/LocalAgent/test-decision-layer
python3 main.py "Hey, I'm Travis from Building-A. I lost my ticket. My Licence plate number is BYU0293. Can you patch me through"
```

Expected output:

```text
Accepted
```

## Config

Default config path:

`config/buildings.sample.json`

Each building defines `method` (`api`, `cua`, or `openclaw`) and method-specific details.

`api` and `cua` adapters support execution modes including:

- `simulate` (safe local prototype mode)
- `command` (run a system command)
- `http` (call an HTTP endpoint)
- `websocket` (send real tasks to CUA WebSocket server)

This sample now includes:

- simulated entries (`Building-A`, `Building-B`)
- openclaw delegation (`Building-C`)
- live HTTP entry (`Building-API`)
- real CUA WebSocket entry (`Building-CUA`)

Useful HTTP fields in config:

- `endpoint` or `endpoint_template`
- `http_method`
- `query_params` (supports placeholders like `{license_plate}`)
- `decision_field` (for example `accessStatus` or `completed`)

Useful CUA websocket fields in config:

- `mode: websocket`
- `ws_server_url` (for example `ws://localhost:8765`)
- `model` (forwarded to CUA runtime task request)
- `verification_url_template`
- `decision_field`

## CLI

```bash
python3 main.py "<driver prompt>"
python3 main.py "<driver prompt>" --config /path/to/buildings.json
python3 main.py "<driver prompt>" --verbose
```

Behavior:

- `api` route: prints `Accepted` or `Denied`
- `cua` route: prints `Accepted` or `Denied`
- `openclaw` route: prints `Delegating to openclaw` and exits

Examples:

```bash
python3 main.py "Hi, I'm Chris from Building-API. Plate number is ABC123"
python3 main.py "Hi, I'm Pat from Building-CUA. Plate number is 3"
```

## Real CUA Flow

On your target machine (where CUA deps are installed):

1. Prepare runtime config:

```bash
cd /home/uthp/Documents/Projects/LocalAgent/test-decision-layer/cua_runtime
cp config.sample.json config.json
```

2. Start the single runtime process:

```bash
cd /home/uthp/Documents/Projects/LocalAgent/test-decision-layer/cua_runtime
python3 ws_server.py
```

`ws_server.py` now starts both `computer_server` and the CUA websocket service in one process.
Use one `Ctrl+C` to shut down both.

3. Run decision layer prompt for `Building-CUA`:

```bash
cd /home/uthp/Documents/Projects/LocalAgent/test-decision-layer
python3 main.py "Hi, I'm Pat from Building-CUA. Plate number is 3" --verbose
```

The CUA adapter sends a real task to the running CUA websocket server, waits for completion, and expects the agent to output:

`FINAL_DECISION: Accepted` or `FINAL_DECISION: Denied`

## Tests

```bash
python3 -m unittest discover -s tests -p "test_*.py"
```
