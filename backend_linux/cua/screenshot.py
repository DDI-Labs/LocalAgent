"""Screen capture using scrot (X11), primary monitor only."""

import subprocess
import re
import base64
import logging
from io import BytesIO

from PIL import Image

from config import SCREENSHOT_PATH, SCREENSHOT_MAX_DIM

log = logging.getLogger(__name__)

# Cached primary monitor geometry: (x_offset, y_offset, width, height)
_primary_geometry: tuple[int, int, int, int] | None = None


def _get_primary_geometry() -> tuple[int, int, int, int]:
    """Get the primary monitor's geometry from xrandr.

    Returns (x_offset, y_offset, width, height).
    """
    global _primary_geometry
    if _primary_geometry is not None:
        return _primary_geometry

    try:
        result = subprocess.run(
            ["xrandr", "--query"],
            capture_output=True,
            text=True,
            check=True,
        )
        for line in result.stdout.splitlines():
            if "primary" in line and " connected " in line:
                # e.g. "eDP-1 connected primary 6144x3456+3840+0 ..."
                m = re.search(r"(\d+)x(\d+)\+(\d+)\+(\d+)", line)
                if m:
                    w, h, x_off, y_off = (
                        int(m.group(1)),
                        int(m.group(2)),
                        int(m.group(3)),
                        int(m.group(4)),
                    )
                    _primary_geometry = (x_off, y_off, w, h)
                    log.info(
                        "Primary monitor: %dx%d at +%d+%d",
                        w, h, x_off, y_off,
                    )
                    return _primary_geometry
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        log.warning("xrandr failed: %s", e)

    raise RuntimeError(
        "Cannot detect primary monitor. Ensure xrandr is available and a primary monitor is set."
    )


def capture(output_path: str = SCREENSHOT_PATH) -> str:
    """Take a screenshot of the primary monitor and return the file path."""
    x_off, y_off, w, h = _get_primary_geometry()

    try:
        # scrot -a: capture a specific area (x,y,w,h)
        subprocess.run(
            ["scrot", "-a", f"{x_off},{y_off},{w},{h}", "--overwrite", output_path],
            check=True,
            capture_output=True,
        )
        log.info("Screenshot saved to %s (%dx%d)", output_path, w, h)
        return output_path
    except FileNotFoundError:
        raise RuntimeError(
            "scrot is not installed. Install it with: sudo apt install scrot"
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"scrot failed: {e.stderr.decode()}")


def capture_and_encode(
    max_dimension: int = SCREENSHOT_MAX_DIM,
    jpeg_quality: int = 75,
) -> str:
    """Take a screenshot of the primary monitor, compress it, and return base64.

    Downscales to max_dimension and converts to JPEG for smaller payloads
    to the vision model.
    """
    path = capture()
    img = Image.open(path)

    # Downscale if needed
    w, h = img.size
    if max(w, h) > max_dimension:
        scale = max_dimension / max(w, h)
        img = img.resize(
            (int(w * scale), int(h * scale)),
            Image.LANCZOS,
        )

    buf = BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=jpeg_quality)
    encoded = base64.b64encode(buf.getvalue()).decode("utf-8")

    log.info(
        "Screenshot encoded: %dx%d -> %dx%d, %d KB",
        w, h, img.size[0], img.size[1], len(buf.getvalue()) // 1024,
    )
    return encoded


def get_screen_size() -> tuple[int, int]:
    """Return (width, height) of the primary monitor."""
    _, _, w, h = _get_primary_geometry()
    return w, h
