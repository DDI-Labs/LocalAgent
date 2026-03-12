"""Reversible PII masking with a bidirectional mapping store.

Usage:
    masker = PIIMasker()
    sanitized = masker.mask("Send $500 to John Smith at john@example.com")
    # → "Send <<PII:MONEY_1>> to <<PII:PERSON_1>> at <<PII:EMAIL_1>>"

    restored = masker.unmask(sanitized)
    # → "Send $500 to John Smith at john@example.com"

Placeholder format:
    <<PII:CATEGORY_N>>

    Uses << >> delimiters with a PII: prefix to avoid collisions with standard
    UI labels like [OK], [Cancel], [Submit], [Back], etc.  The double-angle-bracket
    + prefix combination never appears in real UI element text.
"""

import logging
from collections import defaultdict

from app_core.sanitization.detector import detect_pii, detect_pii_async

logger = logging.getLogger(__name__)

# Prefix used inside placeholders — must be unique enough that the planning
# model never confuses it with a real UI element description.
_PLACEHOLDER_PREFIX = "PII"


class PIIMasker:
    """Masks PII in text and can reverse the masking.

    Each instance maintains its own mapping so a single masker can be reused
    across an entire agent turn for consistent placeholders (the same value
    always maps to the same placeholder within a turn).
    """

    def __init__(self, ner_min_length: int = 40):
        # value → placeholder  (e.g. "John Smith" → "<<PII:PERSON_1>>")
        self._to_placeholder: dict[str, str] = {}
        # placeholder → value  (e.g. "<<PII:PERSON_1>>" → "John Smith")
        self._to_original: dict[str, str] = {}
        # Counter per category for sequential numbering
        self._counters: dict[str, int] = defaultdict(int)
        # Min text length to trigger spaCy NER (shorter = regex only)
        self._ner_min_length = ner_min_length

    def _get_placeholder(self, category: str, original: str) -> str:
        """Return a stable placeholder for *original* text in *category*."""
        if original in self._to_placeholder:
            return self._to_placeholder[original]

        self._counters[category] += 1
        placeholder = f"<<{_PLACEHOLDER_PREFIX}:{category}_{self._counters[category]}>>"

        self._to_placeholder[original] = placeholder
        self._to_original[placeholder] = original
        return placeholder

    def mask(self, text: str) -> str:
        """Replace all detected PII in *text* with placeholders (synchronous)."""
        spans = detect_pii(text, ner_min_length=self._ner_min_length)
        if not spans:
            return text
        return self._apply_spans(text, spans)

    async def mask_async(self, text: str) -> str:
        """Replace all detected PII in *text* with placeholders (async).

        Runs spaCy NER in a thread pool so the event loop isn't blocked.
        """
        spans = await detect_pii_async(text, ner_min_length=self._ner_min_length)
        if not spans:
            return text
        return self._apply_spans(text, spans)

    def _apply_spans(self, text: str, spans) -> str:
        """Build masked text from detected spans."""
        parts: list[str] = []
        prev_end = 0
        masked_count = 0

        for span in spans:
            parts.append(text[prev_end:span.start])
            placeholder = self._get_placeholder(span.category, span.text)
            parts.append(placeholder)
            prev_end = span.end
            masked_count += 1

        parts.append(text[prev_end:])

        if masked_count:
            logger.debug(f"Masked {masked_count} PII span(s)")

        return "".join(parts)

    def unmask(self, text: str) -> str:
        """Restore all placeholders in *text* back to original values."""
        result = text
        for placeholder, original in self._to_original.items():
            result = result.replace(placeholder, original)
        return result

    @property
    def mapping(self) -> dict[str, str]:
        """Read-only view of placeholder → original mapping (for logging)."""
        return dict(self._to_original)

    def clear(self):
        """Reset all mappings for a new turn."""
        self._to_placeholder.clear()
        self._to_original.clear()
        self._counters.clear()
