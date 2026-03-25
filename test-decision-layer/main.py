#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable

from decision_layer.config_loader import load_config
from decision_layer.engine import DecisionEngine


def _default_config_path() -> Path:
    return Path(__file__).resolve().parent / "config" / "buildings.sample.json"


def _read_prompt(args: argparse.Namespace) -> str:
    if args.prompt:
        return args.prompt
    raise ValueError("Prompt text is required.")


def _build_cua_reporter(verbose: bool) -> Callable[[str], None] | None:
    if not verbose:
        return None

    def _report(line: str) -> None:
        print(line, file=sys.stderr, flush=True)

    return _report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="POC decision layer for car park lost-ticket verification."
    )
    parser.add_argument("prompt", nargs="?", help="Driver prompt text.")
    parser.add_argument(
        "--config",
        default=str(_default_config_path()),
        help="Path to building config JSON file.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print routed details to stderr.",
    )
    args = parser.parse_args()

    try:
        prompt = _read_prompt(args)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    config = load_config(Path(args.config))
    engine = DecisionEngine(config, cua_event_reporter=_build_cua_reporter(args.verbose))
    result = engine.process_prompt(prompt)

    if result.route == "openclaw":
        print("Delegating to openclaw")
        return 0

    print(result.decision)
    if args.verbose:
        print(
            json.dumps(
                {
                    "route": result.route,
                    "decision": result.decision,
                    "reason": result.reason,
                    "parsed_prompt": result.parsed_prompt,
                    "details": result.details,
                },
                indent=2,
            ),
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
