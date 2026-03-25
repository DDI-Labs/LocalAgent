from __future__ import annotations

import re

from .models import ParsedPrompt
from .utils import normalize_plate, normalize_text_key


NAME_PATTERNS = [
    re.compile(r"\b(?:i\s*am|i'm)\s+([A-Za-z][A-Za-z'-]{0,30})\b", re.IGNORECASE),
]

PLATE_PATTERNS = [
    re.compile(
        r"\b(?:licen[cs]e|licence)\s*plate(?:\s*(?:number|no\.?))?\s*(?:is|=|:)?\s*([A-Za-z0-9-]{2,15})",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bplate(?:\s*(?:number|no\.?))?\s*(?:is|=|:)?\s*([A-Za-z0-9-]{2,15})",
        re.IGNORECASE,
    ),
    re.compile(
        r"\brego(?:\s*(?:number|no\.?))?\s*(?:is|=|:)?\s*([A-Za-z0-9-]{2,15})",
        re.IGNORECASE,
    ),
]

BUILDING_HINT_PATTERNS = [
    re.compile(r"\bfrom\s+([A-Za-z0-9][A-Za-z0-9 _-]{0,50})", re.IGNORECASE),
    re.compile(r"\bbuilding[-\s]*([A-Za-z0-9_-]{1,20})", re.IGNORECASE),
]


def parse_prompt(prompt: str, alias_lookup: dict[str, str]) -> ParsedPrompt:
    requester_name = _extract_name(prompt)
    license_plate = _extract_plate(prompt)
    building_id = _extract_building(prompt, alias_lookup)

    return ParsedPrompt(
        original_prompt=prompt,
        requester_name=requester_name,
        building_id=building_id,
        license_plate=license_plate,
    )


def _extract_name(prompt: str) -> str | None:
    for pattern in NAME_PATTERNS:
        match = pattern.search(prompt)
        if match:
            raw_name = match.group(1).strip().strip(".,!?")
            return raw_name if raw_name else None
    return None


def _extract_plate(prompt: str) -> str | None:
    for pattern in PLATE_PATTERNS:
        match = pattern.search(prompt)
        if not match:
            continue
        return normalize_plate(match.group(1))
    return None


def _extract_building(prompt: str, alias_lookup: dict[str, str]) -> str | None:
    lower_prompt = prompt.lower()

    # Prefer explicit alias hits first.
    aliases = sorted(alias_lookup.keys(), key=len, reverse=True)
    for alias_key in aliases:
        if len(alias_key) < 3:
            continue
        alias_chars_pattern = _alias_chars_pattern(alias_key)
        if re.search(alias_chars_pattern, lower_prompt):
            return alias_lookup[alias_key]

    # Fall back to phrases like "from Building-A".
    for pattern in BUILDING_HINT_PATTERNS:
        match = pattern.search(prompt)
        if not match:
            continue

        candidate_raw = match.group(1).strip().strip(".,!?")
        tokens = re.split(r"\s+", candidate_raw)

        for size in range(min(4, len(tokens)), 0, -1):
            candidate = " ".join(tokens[:size])
            key = normalize_text_key(candidate)
            if key in alias_lookup:
                return alias_lookup[key]
    return None


def _alias_chars_pattern(alias_key: str) -> str:
    # Build a tolerant pattern that allows punctuation between alias characters.
    # Example alias_key "buildinga" -> b\W*u\W*i ...
    chars = [re.escape(ch) for ch in alias_key]
    return r"\b" + r"\W*".join(chars) + r"\b"
