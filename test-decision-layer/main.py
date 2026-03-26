#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable

from decision_layer.config_loader import load_config
from decision_layer.engine import DecisionEngine
from decision_layer.models import DecisionResult


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


def _build_cua_alert(result: DecisionResult) -> tuple[str, str, str] | None:
    if result.route != "cua":
        return None
    if str(result.details.get("mode", "")).lower() not in {"websocket", "ws"}:
        return None

    if result.reason == "CUA websocket task completed":
        return (
            "CUA task completed",
            f"Decision: {result.decision}. Check the terminal for details.",
            "normal",
        )

    reason = result.reason or "CUA task needs attention."
    return (
        "CUA needs attention",
        f"{reason} Check the terminal for details.",
        "critical",
    )


def _spawn_popup(command: list[str]) -> bool:
    try:
        subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return True
    except OSError:
        return False


def _send_linux_alert(title: str, message: str, urgency: str) -> bool:
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return False

    try:
        completed = subprocess.run(
            [
                "notify-send",
                "--app-name",
                "test-decision-layer",
                "--urgency",
                urgency,
                title,
                message,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=5,
        )
        if completed.returncode == 0:
            return True
    except (OSError, subprocess.SubprocessError):
        pass

    zenity_mode = "--error" if urgency == "critical" else "--info"
    if _spawn_popup(["zenity", zenity_mode, "--title", title, "--text", message]):
        return True

    return _spawn_popup(["xmessage", "-center", f"{title}\n\n{message}"])


def _maybe_alert_cua_result(result: DecisionResult, alerts_enabled: bool) -> None:
    if not alerts_enabled:
        return

    alert = _build_cua_alert(result)
    if not alert:
        return

    title, message, urgency = alert
    _send_linux_alert(title, message, urgency)


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
    parser.add_argument(
        "--no-cua-alerts",
        action="store_true",
        help="Disable Linux desktop alerts for websocket CUA completion or failure.",
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

    _maybe_alert_cua_result(result, alerts_enabled=not args.no_cua_alerts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
