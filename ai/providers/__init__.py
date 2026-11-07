"""Small provider router; all model choices come from server configuration."""
from __future__ import annotations

import json

import httpx
from fastapi import HTTPException

from ai.humanizer.prompts import MODES, SYSTEM
from ai.providers import compatible_provider, ollama_provider, openai_provider

_ADAPTERS = {'ollama': ollama_provider, 'openai': openai_provider, 'compatible': compatible_provider}
OPENAI_CONFIGURATION_ERROR = 'OpenAI är inte konfigurerat. Lägg till OPENAI_API_KEY och OPENAI_MODEL i serverns .env.'


def configuration_error(settings) -> str | None:
    if settings.provider == 'openai':
        if not settings.openai_key.strip() or not settings.model or not settings.model.strip():
            return OPENAI_CONFIGURATION_ERROR
    elif settings.provider == 'ollama':
        if not settings.model or not settings.model.strip() or not settings.ollama_url.strip():
            return 'Ollama är inte konfigurerat. Ange OLLAMA_MODEL och OLLAMA_URL i serverns .env.'
    elif settings.provider == 'compatible':
        if not settings.model or not settings.model.strip() or not settings.compatible_url.strip() or not settings.compatible_key.strip():
            return 'AI-leverantören är inte konfigurerad. Ange AI_MODEL, AI_COMPATIBLE_URL och AI_COMPATIBLE_KEY i serverns .env.'
    else:
        return 'Okänd AI-leverantör. Ange ollama, openai eller compatible i AI_PROVIDER på servern.'
    return None


def generation_body(settings, payload, protected, output_tokens=None) -> dict:
    adapter = _ADAPTERS.get(settings.provider)
    if adapter is None:
        raise HTTPException(503, configuration_error(settings))
    user = json.dumps({'language': payload.language, 'tone': payload.tone, 'text': protected}, ensure_ascii=False)
    instructions = SYSTEM + '\nPlaceholders also include names, dates, numbers with their units and user-selected exact terms. Keep each actor/action/date/quantity relationship and explicit uncertainty unchanged. Do not infer causation from simultaneous observations.\nMode guidance: ' + MODES[payload.tone]
    # An internal readiness override may reduce, never enlarge, the server cap.
    cap = min(output_tokens or settings.max_output_tokens, settings.max_output_tokens)
    return adapter.generation_body(settings, instructions, user, cap)


async def generate(settings, payload, protected, transport=None, output_tokens=None) -> str:
    error = configuration_error(settings)
    if error:
        raise HTTPException(503, error)
    body = generation_body(settings, payload, protected, output_tokens)
    # No redirect following and no SDK retries: exactly one generation request.
    # CancelledError is deliberately not caught anywhere in the adapters.
    async with httpx.AsyncClient(timeout=httpx.Timeout(settings.request_timeout, connect=5), transport=transport,
                                 follow_redirects=False, trust_env=False) as client:
        return await _ADAPTERS[settings.provider].generate(client, settings, body)


__all__ = ['configuration_error', 'generation_body', 'generate']
