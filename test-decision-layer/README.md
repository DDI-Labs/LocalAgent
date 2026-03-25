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

`api` and `cua` adapters support three execution modes:

- `simulate` (safe local prototype mode)
- `command` (run a system command)
- `http` (call an HTTP endpoint)

For this sample, `simulate` is used.

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

## Tests

```bash
python3 -m unittest discover -s tests -p "test_*.py"
```

