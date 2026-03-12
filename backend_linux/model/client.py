"""Ollama vision model client."""

import json
import logging
import time
from typing import Callable, Optional

import httpx

from config import OLLAMA_HOST, OLLAMA_MODEL

log = logging.getLogger(__name__)

# Reusable client with generous timeout
_client = httpx.Client(timeout=httpx.Timeout(600.0, connect=10.0))


def chat(
    messages: list[dict],
    model: str = OLLAMA_MODEL,
    on_token: Optional[Callable[[str], None]] = None,
    _retries: int = 1,
) -> str:
    """Send a chat request to Ollama and return the assistant's response text.

    Uses streaming to provide real-time token output and timing diagnostics.
    Retries once on server errors (500) which can happen from transient OOM.

    Args:
        messages: Ollama chat format messages.
        model: Model name.
        on_token: Optional callback fired for each token chunk as it arrives.
        _retries: Number of retries remaining on server errors.
    """
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "keep_alive": "10m",
        "options": {
            "temperature": 0.3,
            "num_predict": 512,
            "num_ctx": 2048,
        },
    }

    log.info("Sending request to Ollama (%s), %d messages", model, len(messages))
    t_start = time.monotonic()
    t_first_token = None

    try:
        with _client.stream("POST", f"{OLLAMA_HOST}/api/chat", json=payload) as resp:
            if resp.status_code >= 500:
                resp.read()
                error_msg = f"Ollama server error: {resp.status_code} {resp.text[:200]}"
                if _retries > 0:
                    log.warning("%s — retrying (%d left)", error_msg, _retries)
                    time.sleep(2)
                    return chat(messages, model, on_token, _retries - 1)
                raise RuntimeError(error_msg)
            if resp.status_code != 200:
                resp.read()
                raise RuntimeError(
                    f"Ollama request failed: {resp.status_code} {resp.text[:200]}"
                )
            chunks = []
            for line in resp.iter_lines():
                if not line:
                    continue
                data = json.loads(line)
                if "error" in data:
                    raise RuntimeError(f"Ollama error: {data['error']}")
                token = data.get("message", {}).get("content", "")
                if token:
                    if t_first_token is None:
                        t_first_token = time.monotonic()
                        log.info(
                            "First token after %.1fs (model load + vision encode)",
                            t_first_token - t_start,
                        )
                    chunks.append(token)
                    if on_token:
                        on_token(token)
    except httpx.ConnectError:
        raise RuntimeError(
            f"Cannot connect to Ollama at {OLLAMA_HOST}. "
            "Is Ollama running? Start it with: ollama serve"
        )

    content = "".join(chunks)
    t_end = time.monotonic()
    log.info(
        "Model response (%d chars) in %.1fs total (%.1fs to first token): %s",
        len(content),
        t_end - t_start,
        (t_first_token - t_start) if t_first_token else 0,
        content[:200],
    )
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
