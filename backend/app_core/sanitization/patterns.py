"""Compiled regex patterns for common PII types.

Each pattern is a (name, compiled_regex) tuple.  The name is used as the
placeholder category (e.g. "EMAIL" → [EMAIL_1], [EMAIL_2], …).
"""

import re

# Ordered so more specific patterns match first (e.g. SSN before generic digits).
PII_PATTERNS: list[tuple[str, re.Pattern]] = [
    # Email addresses
    ("EMAIL", re.compile(
        r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Z|a-z]{2,}\b"
    )),

    # US Social Security Numbers (XXX-XX-XXXX)
    ("SSN", re.compile(
        r"\b\d{3}-\d{2}-\d{4}\b"
    )),

    # Credit card numbers (13-19 digits, optionally separated by spaces/dashes)
    ("CREDIT_CARD", re.compile(
        r"\b(?:\d[ \-]*?){13,19}\b"
    )),

    # US phone numbers (various formats)
    ("PHONE", re.compile(
        r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"
    )),

    # IP addresses (IPv4)
    ("IP_ADDRESS", re.compile(
        r"\b(?:\d{1,3}\.){3}\d{1,3}\b"
    )),

    # Dates that may indicate DOB (MM/DD/YYYY, DD-MM-YYYY, YYYY-MM-DD)
    ("DATE", re.compile(
        r"\b(?:\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}|\d{4}[/\-]\d{1,2}[/\-]\d{1,2})\b"
    )),

    # Dollar amounts ($X,XXX.XX)
    ("MONEY", re.compile(
        r"\$[\d,]+(?:\.\d{2})?"
    )),
]
