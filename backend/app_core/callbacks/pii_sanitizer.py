"""PII sanitizer callback — masks personal data before cloud model calls.

In the composed model pipeline, the grounding model (local) produces text
descriptions of UI elements.  Before these descriptions reach the cloud
planning model, this callback replaces any PII with reversible placeholders.

After the planning model responds, the masker restores original values so
the local execution layer can act on real data (coordinates, app names, etc.).

Performance:
- spaCy NER runs in a thread pool (via mask_async) so it never blocks the
  event loop or creates laggy WebSocket status updates.
- Short text (< ner_min_length chars) skips NER entirely — regex-only path
  takes <1ms vs ~100-200ms for spaCy.  Most UI labels are short.
"""

import logging
from typing import Any, Callable, Dict, List

from agent.callbacks.base import AsyncCallbackHandler

from app_core.sanitization import PIIMasker
from app_core.config import PII_NER_MIN_LENGTH

logger = logging.getLogger(__name__)

StatusCallback = Callable[..., None]


class PIISanitizerCallback(AsyncCallbackHandler):
    """Sanitizes PII from messages before they reach the cloud planning model."""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._masker = PIIMasker(ner_min_length=PII_NER_MIN_LENGTH)
        self._broadcast: StatusCallback | None = None

    def set_broadcast(self, broadcast: StatusCallback | None) -> None:
        """Optional: wire up WebSocket broadcast for sanitization events."""
        self._broadcast = broadcast

    async def on_run_start(
        self, kwargs: Dict[str, Any], old_items: List[Dict[str, Any]]
    ) -> None:
        """Reset the masker at the start of each agent run."""
        self._masker.clear()

    async def on_llm_start(
        self, messages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Sanitize text content in messages before they go to the LLM.

        In the composed pipeline, the planning model receives element
        descriptions as text.  We mask any PII found in those descriptions.
        Uses mask_async to run NER in a thread pool — no event loop blocking.
        """
        if not self.enabled:
            return messages

        masked_count = 0

        for message in messages:
            # Sanitize top-level text content
            if isinstance(message.get("content"), str):
                original = message["content"]
                sanitized = await self._masker.mask_async(original)
                if sanitized != original:
                    message["content"] = sanitized
                    masked_count += 1

            # Sanitize content blocks (list of dicts)
            content = message.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        original = block.get("text", "")
                        sanitized = await self._masker.mask_async(original)
                        if sanitized != original:
                            block["text"] = sanitized
                            masked_count += 1

        if masked_count:
            logger.info(f"PII sanitizer masked content in {masked_count} message block(s)")
            if self._broadcast:
                self._broadcast("action", f"Sanitized {masked_count} block(s) before cloud call")

        return messages

    async def on_run_end(
        self,
        kwargs: Dict[str, Any],
        old_items: List[Dict[str, Any]],
        new_items: List[Dict[str, Any]],
    ) -> None:
        """Restore PII in the planning model's output so execution uses real values."""
        if not self.enabled:
            return

        restored = False
        for item in new_items:
            # Unmask text in message content
            if item.get("type") == "message":
                content_blocks = item.get("content", [])
                if isinstance(content_blocks, list):
                    for block in content_blocks:
                        if isinstance(block, dict) and block.get("type") == "text":
                            original = block["text"]
                            unmasked = self._masker.unmask(original)
                            if unmasked != original:
                                block["text"] = unmasked
                                restored = True
                elif isinstance(content_blocks, str):
                    unmasked = self._masker.unmask(content_blocks)
                    if unmasked != content_blocks:
                        item["content"] = unmasked
                        restored = True

            # Unmask text in computer_call actions (e.g. type content)
            if item.get("type") == "computer_call":
                action = item.get("action", {})
                for key in ("content", "text", "query"):
                    if key in action and isinstance(action[key], str):
                        unmasked = self._masker.unmask(action[key])
                        if unmasked != action[key]:
                            action[key] = unmasked
                            restored = True

        if restored:
            logger.info("PII sanitizer restored original values in planning model output")

        # Log mapping summary (redacted) for audit
        mapping = self._masker.mapping
        if mapping:
            logger.debug(
                f"PII mapping this turn: {len(mapping)} placeholder(s) — "
                f"{', '.join(mapping.keys())}"
            )
