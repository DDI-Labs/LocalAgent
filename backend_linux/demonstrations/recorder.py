"""Record human demonstrations for learn-by-demonstration.

Usage (CLI):
    python -m demonstrations.recorder --site tower-a

The recorder captures a human performing a task step-by-step:
1. Takes a screenshot (what the human sees)
2. Human performs an action (click, type, hotkey, etc.)
3. Records the action with coordinates/text
4. Repeats until human says 'done'

Produces a demonstration directory:
    demonstrations/data/<site_id>/demo_<timestamp>/
        step_01.json   # {"action": "hotkey(super)", "description": "Open Activities"}
        step_01.png    # screenshot BEFORE the action
        step_02.json
        step_02.png
        ...
"""

import json
import subprocess
import time
import shutil
from datetime import datetime
from pathlib import Path

from cua import screenshot, executor

DEMO_DIR = Path(__file__).parent / "data"


def _get_demo_path(site_id: str) -> Path:
    """Create a new timestamped demo directory for a site."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = DEMO_DIR / site_id / f"demo_{ts}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def record_step(demo_path: Path, step: int, action: str, description: str) -> None:
    """Save a single demonstration step (screenshot + action)."""
    # Copy current screenshot as step evidence
    src = Path("/tmp/localagent_screenshot.png")
    dst = demo_path / f"step_{step:02d}.png"
    if src.exists():
        shutil.copy2(str(src), str(dst))

    # Save action metadata
    meta = {
        "step": step,
        "action": action,
        "description": description,
        "timestamp": datetime.now().isoformat(),
    }
    meta_path = demo_path / f"step_{step:02d}.json"
    meta_path.write_text(json.dumps(meta, indent=2))


def list_demos(site_id: str) -> list[Path]:
    """List all demonstration directories for a site, newest first."""
    site_dir = DEMO_DIR / site_id
    if not site_dir.exists():
        return []
    demos = sorted(site_dir.iterdir(), reverse=True)
    return [d for d in demos if d.is_dir()]


def load_demo(demo_path: Path) -> list[dict]:
    """Load all steps from a demonstration directory."""
    steps = []
    for meta_file in sorted(demo_path.glob("step_*.json")):
        steps.append(json.loads(meta_file.read_text()))
    return steps


def format_demo_for_prompt(steps: list[dict], max_steps: int = 10) -> str:
    """Format a demonstration as a compact text block for the model prompt.

    Keeps it brief: one line per step, no screenshots (those are too large).
    """
    if not steps:
        return ""

    lines = ["DEMONSTRATION — A human completed this task as follows:"]
    for s in steps[:max_steps]:
        lines.append(f"  Step {s['step']}: {s['action']}  # {s['description']}")
    if len(steps) > max_steps:
        lines.append(f"  ... ({len(steps) - max_steps} more steps)")
    lines.append("Follow a similar sequence of actions. Adapt if the screen looks different.")
    return "\n".join(lines)


def _capture_click() -> tuple[int, int]:
    """Wait for the user to click somewhere on screen, return (x, y) relative to primary monitor."""
    # xdotool getmouselocation --shell after waiting for a click via xev/xinput is complex.
    # Simpler: use xdotool to select a point (like a crosshair picker).
    result = subprocess.run(
        ["xdotool", "getmouselocation", "--shell"],
        capture_output=True, text=True, check=True,
    )
    # Parse: X=1234\nY=567\nSCREEN=0\nWINDOW=...
    vals = {}
    for line in result.stdout.strip().split("\n"):
        if "=" in line:
            k, v = line.split("=", 1)
            vals[k] = int(v)

    # Convert absolute coords to primary-monitor-relative
    from cua.screenshot import _get_primary_geometry
    x_off, y_off, _, _ = _get_primary_geometry()
    return vals.get("X", 0) - x_off, vals.get("Y", 0) - y_off


def run_interactive_recording(site_id: str) -> Path:
    """Run an interactive CLI recording session.

    The flow per step:
    1. Screenshot is taken automatically (what's on screen now)
    2. You choose action type: click / type / hotkey / done
       - click: you click on the actual screen, coordinates are captured
       - type: you type the text to enter
       - hotkey: you type the key combo (e.g. super, Return, ctrl+a)
    3. The action is EXECUTED for you on the desktop
    4. You add a brief description
    5. Repeat until 'done'

    Returns the path to the saved demonstration directory.
    """
    print(f"\n--- Recording demonstration for site: {site_id} ---")
    print("How it works:")
    print("  1. Screenshot is taken automatically")
    print("  2. Choose action type:")
    print("     c = click (then click on the screen where you want)")
    print("     t = type (then enter the text to type)")
    print("     h = hotkey (then enter key combo like 'super', 'Return')")
    print("     d = double-click (then click on the screen)")
    print("     done = finish recording")
    print("  3. The action is executed for you")
    print("  4. Add a brief description\n")

    demo_path = _get_demo_path(site_id)
    print(f"Saving to: {demo_path}\n")

    step = 1
    while True:
        # Capture what's on screen BEFORE the action
        print(f"  Step {step}: Taking screenshot...")
        try:
            screenshot.capture_and_encode()
        except RuntimeError as e:
            print(f"  Screenshot failed: {e}")
            break

        print(f"  Screenshot saved: /tmp/localagent_screenshot.png")
        choice = input(f"  Action type (c=click, t=type, h=hotkey, d=double-click, done=finish): ").strip().lower()

        if choice in ("done", "quit", "exit", ""):
            print(f"\n  Recording complete: {step - 1} steps saved to {demo_path}")
            break

        action = ""
        if choice == "c":
            print(f"  >>> Click on the target on your screen NOW, then press Enter here...")
            input()  # wait for them to click and come back
            x, y = _capture_click()
            action = f"click({x},{y})"
            executor.click(x, y)
            print(f"  ✓ Clicked at ({x}, {y})")

        elif choice == "d":
            print(f"  >>> Double-click on the target on your screen NOW, then press Enter here...")
            input()
            x, y = _capture_click()
            action = f"double_click({x},{y})"
            executor.double_click(x, y)
            print(f"  ✓ Double-clicked at ({x}, {y})")

        elif choice == "t":
            text = input(f"  Text to type: ").strip()
            if not text:
                print(f"  Skipped (empty text)")
                continue
            action = f"type('{text}')"
            executor.type_text(text)
            print(f"  ✓ Typed: {text}")

        elif choice == "h":
            keys = input(f"  Key combo (e.g. super, Return, ctrl+a, Tab): ").strip()
            if not keys:
                print(f"  Skipped (empty)")
                continue
            action = f"hotkey({keys})"
            executor.hotkey(keys)
            print(f"  ✓ Pressed: {keys}")

        else:
            print(f"  Unknown choice '{choice}', try again.")
            continue

        description = input(f"  Brief description (e.g. 'Click NoMachine icon'): ").strip()
        if not description:
            description = action

        record_step(demo_path, step, action, description)
        print(f"  ✓ Step {step} recorded\n")
        step += 1

    return demo_path
