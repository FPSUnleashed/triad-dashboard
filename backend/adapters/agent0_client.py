"""Agent0 API client - sends fresh chats to Agent0."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import random
from pathlib import Path

import httpx

from ..config import AGENT0_API_KEY as CONFIG_AGENT0_API_KEY
from ..config import AGENT0_BASE_URL as CONFIG_AGENT0_BASE_URL

SETTINGS_PATH = Path('/a0/usr/settings.json')
DOTENV_PATH = Path('/a0/usr/.env')
MAX_ATTEMPTS = 4
INITIAL_BACKOFF_SECONDS = 1.5
MAX_BACKOFF_SECONDS = 12.0
RETRYABLE_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}


def _load_json_settings() -> dict:
    if not SETTINGS_PATH.exists():
        return {}
    try:
        return json.loads(SETTINGS_PATH.read_text())
    except Exception:
        return {}


def _load_dotenv_values() -> dict:
    vals: dict[str, str] = {}
    if not DOTENV_PATH.exists():
        return vals
    try:
        for line in DOTENV_PATH.read_text().splitlines():
            if '=' not in line or line.lstrip().startswith('#'):
                continue
            k, v = line.split('=', 1)
            vals[k.strip()] = v.strip()
    except Exception:
        return {}
    return vals


def _derive_token(runtime_id: str, auth_login: str = '', auth_password: str = '') -> str:
    runtime_id = (runtime_id or '').strip()
    if not runtime_id:
        return ''
    auth_login = (auth_login or '').strip()
    auth_password = (auth_password or '').strip()
    hash_bytes = hashlib.sha256(f'{runtime_id}:{auth_login}:{auth_password}'.encode()).digest()
    return base64.urlsafe_b64encode(hash_bytes).decode().replace('=', '')[:16]


def _derive_token_from_dotenv() -> str:
    vals = _load_dotenv_values()
    return _derive_token(
        vals.get('A0_PERSISTENT_RUNTIME_ID', ''),
        vals.get('AUTH_LOGIN', ''),
        vals.get('AUTH_PASSWORD', ''),
    )


def _derive_token_from_settings(settings: dict | None = None) -> str:
    settings = settings or _load_json_settings()
    return _derive_token(
        str(settings.get('runtime_id') or ''),
        str(settings.get('auth_login') or ''),
        str(settings.get('auth_password') or ''),
    )


def get_token() -> str:
    env_token = (CONFIG_AGENT0_API_KEY or os.getenv('AGENT0_API_KEY') or '').strip()
    if env_token:
        return env_token

    settings = _load_json_settings()

    settings_token = str(settings.get('mcp_server_token') or '').strip()
    if settings_token:
        return settings_token

    derived = _derive_token_from_dotenv()
    if derived:
        return derived

    derived = _derive_token_from_settings(settings)
    if derived:
        return derived

    raise RuntimeError(
        'Agent0 API token not found. Set AGENT0_API_KEY, populate /a0/usr/settings.json '
        'mcp_server_token, or ensure runtime token inputs exist in /a0/usr/.env or settings.json.'
    )


def get_base_url() -> str:
    return (CONFIG_AGENT0_BASE_URL or os.getenv('AGENT0_BASE_URL') or 'http://127.0.0.1:80').rstrip('/')


def _next_backoff(attempt: int) -> float:
    base = min(MAX_BACKOFF_SECONDS, INITIAL_BACKOFF_SECONDS * (2 ** (attempt - 1)))
    jitter = random.uniform(0.0, 0.4)
    return base + jitter


async def send_fresh_chat(message: str, lifetime_hours: float = 1) -> dict:
    """Send a message to Agent0 as a fresh chat with no context reuse."""
    url = f"{get_base_url()}/api_message"
    headers = {
        'Content-Type': 'application/json',
        'X-API-KEY': get_token(),
    }
    payload = {
        'message': message,
        'lifetime_hours': lifetime_hours,
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
                        raise Exception(f'Agent0 API returned non-JSON success payload: {e}; body={body_preview}')

                body_preview = (response.text or '')[:1200]
                err = f'Agent0 API error {response.status_code}: {body_preview}'

                if response.status_code in RETRYABLE_STATUS_CODES and attempt < MAX_ATTEMPTS:
                    last_error = err
                    await asyncio.sleep(_next_backoff(attempt))
                    continue

                raise Exception(err)

            except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError, httpx.RequestError) as e:
                err = f'Agent0 transport error on attempt {attempt}/{MAX_ATTEMPTS}: {e}'
                if attempt < MAX_ATTEMPTS:
                    last_error = err
                    await asyncio.sleep(_next_backoff(attempt))
                    continue
                raise Exception(err)

    raise Exception(last_error or 'Agent0 call failed after retries')


async def send_chat(message: str, context_id: str | None = None, lifetime_hours: float = 1) -> dict:
    """Send a message to Agent0, optionally continuing an existing chat context."""
    url = f"{get_base_url()}/api_message"
    headers = {
        'Content-Type': 'application/json',
        'X-API-KEY': get_token(),
    }
    payload = {
        'message': message,
        'lifetime_hours': lifetime_hours,
    }
    if context_id:
        payload['context_id'] = context_id

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
                        raise Exception(f'Agent0 API returned non-JSON success payload: {e}; body={body_preview}')

                body_preview = (response.text or '')[:1200]
                err = f'Agent0 API error {response.status_code}: {body_preview}'

                if response.status_code in RETRYABLE_STATUS_CODES and attempt < MAX_ATTEMPTS:
                    last_error = err
                    await asyncio.sleep(_next_backoff(attempt))
                    continue

                raise Exception(err)

            except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError, httpx.RequestError) as e:
                err = f'Agent0 transport error on attempt {attempt}/{MAX_ATTEMPTS}: {e}'
                if attempt < MAX_ATTEMPTS:
                    last_error = err
                    await asyncio.sleep(_next_backoff(attempt))
                    continue
                raise Exception(err)

    raise Exception(last_error or 'Agent0 call failed after retries')

