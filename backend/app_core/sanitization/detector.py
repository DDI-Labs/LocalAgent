"""PII detection engine combining spaCy NER with regex patterns.

Returns a list of (start, end, category, original_text) spans found in text.
Spans are sorted by start position and do not overlap (longer matches win).

Performance notes:
- Short text (< PII_NER_MIN_LENGTH chars) skips NER entirely — regex only.
  Most UI element descriptions ("OK", "Cancel", "Submit") are short and don't
  contain PII, so this avoids ~100ms of spaCy overhead per label.
- spaCy NER runs in a thread pool executor to avoid blocking the event loop.
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import NamedTuple

from app_core.sanitization.patterns import PII_PATTERNS

logger = logging.getLogger(__name__)

# Lazy-loaded spaCy model
_nlp = None

# Dedicated thread pool for NER — single thread is enough since spaCy
# releases the GIL during inference, and we process one text at a time.
_ner_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ner")


class PIISpan(NamedTuple):
    start: int
    end: int
    category: str
    text: str


def _load_spacy():
    """Lazy-load the spaCy model on first use."""
    global _nlp
    if _nlp is not None:
        return _nlp
    try:
        import spacy
        _nlp = spacy.load("en_core_web_sm")
        logger.info("spaCy en_core_web_sm model loaded for PII detection")
    except (ImportError, OSError) as e:
        logger.warning(
            f"spaCy not available ({e}). PII detection will use regex only. "
            "Install with: pip3 install spacy && python3 -m spacy download en_core_web_sm"
        )
        _nlp = False  # Sentinel: tried and failed
    return _nlp


# spaCy entity labels we treat as PII
_NER_CATEGORY_MAP = {
    "PERSON": "PERSON",
    "ORG": "ORG",
    "GPE": "LOCATION",      # Geopolitical entity (cities, countries)
    "LOC": "LOCATION",
    "MONEY": "MONEY",
    "DATE": "DATE",
    "CARDINAL": None,        # Skip bare numbers — too noisy
    "ORDINAL": None,
}


def _run_ner(text: str) -> list[PIISpan]:
    """Run spaCy NER synchronously (called from thread pool)."""
    nlp = _load_spacy()
    if not nlp or nlp is False:
        return []
    spans: list[PIISpan] = []
    doc = nlp(text)
    for ent in doc.ents:
        category = _NER_CATEGORY_MAP.get(ent.label_)
        if category:
            spans.append(PIISpan(ent.start_char, ent.end_char, category, ent.text))
    return spans


def _run_regex(text: str) -> list[PIISpan]:
    """Run regex patterns against text (always fast, no async needed)."""
    spans: list[PIISpan] = []
    for category, pattern in PII_PATTERNS:
        for match in pattern.finditer(text):
            spans.append(PIISpan(match.start(), match.end(), category, match.group()))
    return spans


def detect_pii(text: str, ner_min_length: int = 40) -> list[PIISpan]:
    """Find all PII spans in *text* using NER + regex (synchronous).

    Args:
        text: The text to scan.
        ner_min_length: Skip spaCy NER for text shorter than this.
            Short UI labels ("OK", "Cancel") rarely contain PII and
            skipping NER saves ~100-200ms per call.

    Returns non-overlapping spans sorted by start position.
    """
    spans: list[PIISpan] = []

    # Stage 1: spaCy NER (skip for short text — performance optimisation)
    if len(text) >= ner_min_length:
        spans.extend(_run_ner(text))

    # Stage 2: Regex patterns (always runs — fast enough for any length)
    spans.extend(_run_regex(text))

    return _resolve_overlaps(spans)


async def detect_pii_async(text: str, ner_min_length: int = 40) -> list[PIISpan]:
    """Async version that runs NER in a thread pool to avoid blocking the event loop.

    Use this from async callbacks; falls back to regex-only for short text.
    """
    regex_spans = _run_regex(text)

    if len(text) >= ner_min_length:
        loop = asyncio.get_running_loop()
        ner_spans = await loop.run_in_executor(_ner_executor, _run_ner, text)
        return _resolve_overlaps(ner_spans + regex_spans)

    return _resolve_overlaps(regex_spans)


def _resolve_overlaps(spans: list[PIISpan]) -> list[PIISpan]:
    """Remove overlapping spans, preferring longer matches."""
    if not spans:
        return []

    # Sort by start position, then by length descending (longer first)
    sorted_spans = sorted(spans, key=lambda s: (s.start, -(s.end - s.start)))

    result: list[PIISpan] = [sorted_spans[0]]
    for span in sorted_spans[1:]:
        prev = result[-1]
        if span.start >= prev.end:
            # No overlap
            result.append(span)
        elif (span.end - span.start) > (prev.end - prev.start):
            # Current span is longer — replace previous
            result[-1] = span
        # Otherwise skip (previous span is longer or equal)

    return result
