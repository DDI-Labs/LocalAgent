"""Screenshot optimization callback for ComputerAgent.

Reduces image size before sending to the LLM to save tokens and speed up inference.
- Resolution scaling: downsizes screenshots (e.g. Retina 2x → 1x)
- JPEG compression: uses JPEG instead of PNG for smaller payloads
"""

import base64
import io
import logging
from typing import Any, Dict, List

from PIL import Image
from agent.callbacks.base import AsyncCallbackHandler

logger = logging.getLogger(__name__)

# Target max dimension (width or height) for screenshots sent to the LLM.
# 1280px is plenty for the model to see UI elements — no need for full Retina.
TARGET_MAX_DIMENSION = 1024

# JPEG quality (0-100). 60 is a good balance of quality vs size.
JPEG_QUALITY = 60


def _is_already_optimized(base64_data: str) -> bool:
    """Check if an image has already been compressed by us.

    Heuristic: if it's a small JPEG (< 80KB decoded) and already within our
    target dimensions, skip re-processing to avoid wasting CPU every LLM call.
    """
    raw_size = len(base64_data) * 3 // 4  # approx decoded size
    return raw_size < 80_000  # 80KB — our compressed outputs are typically 5-60KB


def _optimize_image(base64_data: str) -> str:
    """Downscale and compress a base64-encoded screenshot."""
    # Skip images that are already small enough (previously optimized)
    if _is_already_optimized(base64_data):
        logger.debug("Skipping already-optimized image")
        return base64_data

    image_bytes = base64.b64decode(base64_data)
    image = Image.open(io.BytesIO(image_bytes))

    original_size = len(image_bytes)
    w, h = image.size

    # Scale down if larger than target
    if max(w, h) > TARGET_MAX_DIMENSION:
        scale = TARGET_MAX_DIMENSION / max(w, h)
        new_w, new_h = int(w * scale), int(h * scale)
        image = image.resize((new_w, new_h), Image.Resampling.LANCZOS)
        logger.debug(f"Resized screenshot: {w}x{h} → {new_w}x{new_h}")

    # Convert to RGB (JPEG doesn't support alpha) and compress
    if image.mode in ("RGBA", "P"):
        image = image.convert("RGB")

    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    compressed = buf.getvalue()

    logger.info(
        f"Screenshot optimized: {original_size // 1024}KB → {len(compressed) // 1024}KB "
        f"({100 - len(compressed) * 100 // original_size}% reduction)"
    )

    return base64.b64encode(compressed).decode("utf-8")


class ImageOptimizerCallback(AsyncCallbackHandler):
    """Intercepts screenshots before they reach the LLM and optimizes them."""

    async def on_llm_start(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Downscale and compress any screenshot images in the message history."""
        for message in messages:
            # Handle computer_call_output messages (screenshots after actions)
            if message.get("type") == "computer_call_output":
                output = message.get("output", {})
                if output.get("type") == "input_image":
                    image_url = output.get("image_url", "")
                    if image_url.startswith("data:image"):
                        # Extract base64 data, optimize, and replace
                        base64_data = image_url.split(",", 1)[1]
                        optimized = _optimize_image(base64_data)
                        output["image_url"] = f"data:image/jpeg;base64,{optimized}"

            # Handle content blocks with images (initial screenshots)
            content = message.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "input_image":
                        image_url = block.get("image_url", "")
                        if isinstance(image_url, str) and image_url.startswith("data:image"):
                            base64_data = image_url.split(",", 1)[1]
                            optimized = _optimize_image(base64_data)
                            block["image_url"] = f"data:image/jpeg;base64,{optimized}"

        return messages
