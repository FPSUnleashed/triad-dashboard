"""Agent0 API client - sends fresh chats to Agent0."""
from __future__ import annotations

import asyncio
import random

import httpx

# Agent0 API configuration
# Token is computed from: runtime_id:auth_login:auth_password SHA256 -> base64[:16]
# See /a0/python/helpers/settings.py:create_auth_token()
AGENT0_BASE_URL = "http://127.0.0.1:80"
AGENT0_API_KEY = "Fj0xCr3wiUToR5Gb"

# Retry policy for transient failures
MAX_ATTEMPTS = 4
INITIAL_BACKOFF_SECONDS = 1.5
MAX_BACKOFF_SECONDS = 12.0
RETRYABLE_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}


def get_token() -> str:
    """Get the Agent0 API token (computed from runtime credentials)."""
    return AGENT0_API_KEY


def _next_backoff(attempt: int) -> float:
    # Exponential backoff with jitter
    base = min(MAX_BACKOFF_SECONDS, INITIAL_BACKOFF_SECONDS * (2 ** (attempt - 1)))
    jitter = random.uniform(0.0, 0.4)
    return base + jitter


async def send_fresh_chat(
    message: str,
    lifetime_hours: float = 1,
) -> dict:
    """
    Send a message to Agent0 as a FRESH chat (no context reuse).

    CRITICAL: Never send context_id - each step gets a brand new conversation.
    This prevents bugs from long conversation contexts.
    """
    url = f"{AGENT0_BASE_URL}/api_message"
    headers = {
        "Content-Type": "application/json",
        "X-API-KEY": get_token(),
    }
    payload = {
        "message": message,
        "lifetime_hours": lifetime_hours,
        # NOTE: No context_id - fresh chat every time!
    }

    last_error: str | None = None

    async with httpx.AsyncClient(timeout=None) as client:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = await client.post(url, json=payload, headers=headers)

                if response.status_code == 200:
                    try:
                        return response.json()
                    except Exception as e:
                        body_preview = response.text[:500]
                        raise Exception(
                            f"Agent0 API returned non-JSON success payload: {e}; body={body_preview}"
                        )

                body_preview = (response.text or "")[:1200]
                err = f"Agent0 API error {response.status_code}: {body_preview}"

                if response.status_code in RETRYABLE_STATUS_CODES and attempt < MAX_ATTEMPTS:
                    last_error = err
                    await asyncio.sleep(_next_backoff(attempt))
                    continue

                raise Exception(err)

            except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError, httpx.RequestError) as e:
                err = f"Agent0 transport error on attempt {attempt}/{MAX_ATTEMPTS}: {e}"
                if attempt < MAX_ATTEMPTS:
                    last_error = err
                    await asyncio.sleep(_next_backoff(attempt))
                    continue
                raise Exception(err)

    raise Exception(last_error or "Agent0 call failed after retries")
