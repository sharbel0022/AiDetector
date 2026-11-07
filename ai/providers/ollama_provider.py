"""Ollama chat adapter retaining strict JSON and explicit completion checks."""
from fastapi import HTTPException

from ai.humanizer.prompts import SCHEMA
from ai.providers.common import request_json, validated_text


def generation_body(settings, instructions, user, cap) -> dict:
    body = {'model': settings.model, 'stream': False, 'format': SCHEMA,
            'messages': [{'role': 'system', 'content': instructions}, {'role': 'user', 'content': user}],
            'options': {'temperature': 0.3, 'num_predict': cap, 'num_ctx': 32768}}
    if settings.ollama_think is not None:
        body['think'] = settings.ollama_think
    return body


async def generate(client, settings, body) -> str:
    data = await request_json(client, settings, 'POST', settings.ollama_url.rstrip('/') + '/api/chat', body=body)
    if data.get('done') is not True or data.get('done_reason') == 'length':
        raise HTTPException(502, 'Ollama slutförde inte textsvar. Förkorta texten eller kontrollera serverns utmatningsgräns.')
    try:
        raw = data['message']['content']
    except (KeyError, TypeError):
        raise HTTPException(502, 'Ollama gav ett ogiltigt strukturerat svar. Försök igen.') from None
    return validated_text(raw)
