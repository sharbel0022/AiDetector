"""Explicitly configured OpenAI-compatible Chat Completions adapter."""
from fastapi import HTTPException

from ai.humanizer.prompts import SCHEMA
from ai.providers.common import request_json, validated_text


def generation_body(settings, instructions, user, cap) -> dict:
    return {'model': settings.model, 'stream': False, 'max_tokens': cap,
            'messages': [{'role': 'system', 'content': instructions}, {'role': 'user', 'content': user}],
            'response_format': {'type': 'json_schema', 'json_schema': {'name': 'rewrite', 'strict': True, 'schema': SCHEMA}}}


async def generate(client, settings, body) -> str:
    headers = {'Authorization': f'Bearer {settings.compatible_key}'}
    data = await request_json(client, settings, 'POST', settings.compatible_url.rstrip('/') + '/chat/completions', headers=headers, body=body)
    try:
        choice = data['choices'][0]
        if choice.get('finish_reason') != 'stop' or choice['message'].get('refusal'):
            raise HTTPException(502, 'AI-leverantören slutförde inte textbearbetningen. Kontrollera modellens svar och serverns utmatningsgräns.')
        raw = choice['message']['content']
    except (KeyError, TypeError, IndexError, AttributeError):
        raise HTTPException(502, 'AI-leverantören gav ett ogiltigt strukturerat svar. Försök igen.') from None
    return validated_text(raw)
