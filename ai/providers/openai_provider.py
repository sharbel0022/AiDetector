"""OpenAI Responses adapter with a non-generating model access check."""
from __future__ import annotations

import hashlib
import time
from urllib.parse import quote

from fastapi import HTTPException

from ai.humanizer.prompts import SCHEMA
from ai.providers.common import request_json, validated_text

API_URL = 'https://api.openai.com/v1'
MODEL_CACHE_SECONDS = 300


def generation_body(settings, instructions, user, cap) -> dict:
    return {'model': settings.model, 'instructions': instructions, 'input': user,
            'store': False, 'max_output_tokens': cap,
            'text': {'format': {'type': 'json_schema', 'name': 'rewrite', 'strict': True, 'schema': SCHEMA}}}


async def _check_model(client, settings, headers) -> None:
    # GET /models/{model} confirms account access, not Responses/JSON capability.
    # The actual structured generation (including the explicit readiness probe)
    # remains necessary to establish that the configured model supports this API.
    cache_key = (settings.model, hashlib.sha256(settings.openai_key.encode()).hexdigest())
    if settings._openai_model_cache.get(cache_key, 0) > time.monotonic():
        return
    data = await request_json(client, settings, 'GET', f'{API_URL}/models/{quote(settings.model, safe="")}', headers=headers)
    if data.get('id') != settings.model:
        raise HTTPException(502, 'OpenAI gav ogiltig modellinformation. Kontrollera OPENAI_MODEL och försök igen.')
    settings._openai_model_cache.clear()
    settings._openai_model_cache[cache_key] = time.monotonic() + MODEL_CACHE_SECONDS


async def generate(client, settings, body) -> str:
    headers = {'Authorization': f'Bearer {settings.openai_key}'}
    await _check_model(client, settings, headers)
    data = await request_json(client, settings, 'POST', f'{API_URL}/responses', headers=headers, body=body)
    if data.get('status') != 'completed':
        raise HTTPException(502, 'OpenAI slutförde inte textsvar inom den angivna gränsen. Förkorta texten eller kontrollera serverns utmatningsgräns.')
    try:
        parts = []
        for item in data['output']:
            if item.get('type') != 'message':
                continue
            if item.get('status', 'completed') != 'completed':
                raise HTTPException(502, 'OpenAI slutförde inte hela textsvaret. Förkorta texten eller kontrollera serverns utmatningsgräns.')
            for content in item['content']:
                if content.get('type') == 'refusal':
                    raise HTTPException(502, 'OpenAI avböjde textbearbetningen. Ändra texten och försök igen.')
                if content.get('type') == 'output_text':
                    parts.append(content['text'])
        raw = ''.join(parts)
    except (KeyError, TypeError, AttributeError):
        raise HTTPException(502, 'OpenAI gav ett ogiltigt strukturerat svar. Försök igen.') from None
    return validated_text(raw)
