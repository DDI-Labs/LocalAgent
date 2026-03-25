from __future__ import annotations

import json
import re
from typing import Any


def normalize_text_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def normalize_plate(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def to_decision(value: Any, default: str = "Denied") -> str:
    if isinstance(value, bool):
        return "Accepted" if value else "Denied"
    if isinstance(value, (int, float)):
        return "Accepted" if value > 0 else "Denied"
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"accepted", "accept", "allow", "allowed", "approved", "yes", "true"}:
            return "Accepted"
        if normalized in {"denied", "deny", "rejected", "reject", "no", "false"}:
            return "Denied"
    return default


def extract_decision_from_text_or_json(content: str, default: str = "Denied") -> str:
    text = content.strip()
    if not text:
        return default

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = None

    if isinstance(payload, dict):
        lowered = {str(key).lower(): value for key, value in payload.items()}
        for key in (
            "decision",
            "status",
            "result",
            "accepted",
            "accessstatus",
            "access_status",
            "completed",
        ):
            if key in lowered:
                return to_decision(lowered[key], default=default)
        return default

    return to_decision(text, default=default)
