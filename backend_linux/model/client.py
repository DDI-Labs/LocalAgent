"""Ollama vision model client."""

import logging
from typing import Optional

import httpx

from config import OLLAMA_HOST, OLLAMA_MODEL

log = logging.getLogger(__name__)

# Reusable client with generous timeout for CPU inference
_client = httpx.Client(timeout=httpx.Timeout(600.0, connect=10.0))


def chat(
    messages: list[dict],
    model: str = OLLAMA_MODEL,
) -> str:
    """Send a chat request to Ollama and return the assistant's response text.

    Messages follow the Ollama chat format:
    [
        {
            "role": "user",
            "content": "What action should I take?",
            "images": ["<base64-encoded-image>"]   # optional
        },
        ...
    ]
    """
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": 0.3,
            "num_predict": 512,
        },
    }

    log.info("Sending request to Ollama (%s), %d messages", model, len(messages))

    try:
        resp = _client.post(f"{OLLAMA_HOST}/api/chat", json=payload)
        resp.raise_for_status()
    except httpx.ConnectError:
        raise RuntimeError(
            f"Cannot connect to Ollama at {OLLAMA_HOST}. "
            "Is Ollama running? Start it with: ollama serve"
        )
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"Ollama request failed: {e.response.status_code} {e.response.text}")

    data = resp.json()
    content = data["message"]["content"]
    log.info("Model response (%d chars): %s", len(content), content[:200])
    return content


def check_model_available(model: str = OLLAMA_MODEL) -> bool:
    """Check if the model is pulled and ready in Ollama."""
    try:
        resp = _client.get(f"{OLLAMA_HOST}/api/tags")
        resp.raise_for_status()
        models = [m["name"] for m in resp.json().get("models", [])]
        # Match with or without tag suffix
        return any(model in m or m in model for m in models)
    except (httpx.ConnectError, httpx.HTTPStatusError):
        return False
