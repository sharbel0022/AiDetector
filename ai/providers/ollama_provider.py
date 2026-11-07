"""Ollama chat adapter retaining strict JSON and explicit completion checks."""
import time

from fastapi import HTTPException

from ai.humanizer.prompts import SCHEMA
from ai.providers.common import metered_response, request_json, validated_text
from ai.usage import GenerationResult


def generation_body(settings, instructions, user, cap) -> dict:
    body = {'model': settings.model, 'stream': False, 'format': SCHEMA,
            'messages': [{'role': 'system', 'content': instructions}, {'role': 'user', 'content': user}],
            'options': {'temperature': 0.3, 'num_predict': cap, 'num_ctx': 32768}}
    if settings.ollama_think is not None:
        body['think'] = settings.ollama_think
    return body


async def generate(client, settings, body) -> str:
    started = time.perf_counter()
    data = await request_json(client, settings, 'POST', settings.ollama_url.rstrip('/') + '/api/chat', body=body)
    with metered_response('ollama', data, (time.perf_counter() - started) * 1000) as usage:
        if data.get('done') is not True or data.get('done_reason') == 'length':
            raise HTTPException(502, 'Ollama slutförde inte textsvar. Förkorta texten eller kontrollera serverns utmatningsgräns.')
        try:
            raw = data['message']['content']
        except (KeyError, TypeError):
            raise HTTPException(502, 'Ollama gav ett ogiltigt strukturerat svar. Försök igen.') from None
        return GenerationResult(validated_text(raw), usage)
