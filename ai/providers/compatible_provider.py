"""Explicitly configured OpenAI-compatible Chat Completions adapter."""
import time

from fastapi import HTTPException

from ai.humanizer.prompts import SCHEMA
from ai.providers.common import metered_response, request_json, validated_text
from ai.usage import GenerationResult


def generation_body(settings, instructions, user, cap) -> dict:
    return {'model': settings.model, 'stream': False, 'max_tokens': cap,
            'messages': [{'role': 'system', 'content': instructions}, {'role': 'user', 'content': user}],
            'response_format': {'type': 'json_schema', 'json_schema': {'name': 'rewrite', 'strict': True, 'schema': SCHEMA}}}


async def generate(client, settings, body) -> str:
    headers = {'Authorization': f'Bearer {settings.compatible_key}'}
    started = time.perf_counter()
    data = await request_json(client, settings, 'POST', settings.compatible_url.rstrip('/') + '/chat/completions', headers=headers, body=body)
    with metered_response('compatible', data, (time.perf_counter() - started) * 1000) as usage:
        try:
            choice = data['choices'][0]
            if choice.get('finish_reason') != 'stop' or choice['message'].get('refusal'):
                raise HTTPException(502, 'AI-leverantören slutförde inte textbearbetningen. Kontrollera modellens svar och serverns utmatningsgräns.')
            raw = choice['message']['content']
        except (KeyError, TypeError, IndexError, AttributeError):
            raise HTTPException(502, 'AI-leverantören gav ett ogiltigt strukturerat svar. Försök igen.') from None
        return GenerationResult(validated_text(raw), usage)
