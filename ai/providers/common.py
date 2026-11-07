"""Bounded HTTP and structured text validation shared by provider adapters."""
from __future__ import annotations

import json
import re

import httpx
from fastapi import HTTPException
from pydantic import ValidationError

from ai.contracts import ModelText


def upstream_error(status: int, provider: str, retry_after: str = '') -> HTTPException:
    """Never expose an upstream body, URL, credential or request content."""
    name = 'OpenAI' if provider == 'openai' else 'AI-leverantören'
    key_name = 'OPENAI_API_KEY' if provider == 'openai' else 'serverns API-nyckel'
    model_name = 'OPENAI_MODEL' if provider == 'openai' else 'serverns modellinställning'
    if status == 401:
        return HTTPException(503, f'{name} avvisade API-nyckeln. Kontrollera {key_name} i serverns .env.')
    if status == 403:
        return HTTPException(503, f'{name} nekade åtkomst. Kontrollera API-nyckelns behörighet till projektet och modellen.')
    if status == 404:
        return HTTPException(503, f'{name}-modellen eller slutpunkten är inte tillgänglig. Kontrollera {model_name} och kontots modellåtkomst.')
    if status == 429:
        seconds = retry_after if re.fullmatch(r'[0-9]{1,4}', retry_after) and 1 <= int(retry_after) <= 3600 else '30'
        return HTTPException(429, f'{name} har nått en anropsgräns eller förbrukningsgräns. Vänta och kontrollera kontots kvot och fakturering.', headers={'Retry-After': seconds})
    if status in (400, 422):
        return HTTPException(502, f'{name} kunde inte behandla begäran. Kontrollera att den valda modellen stöder API-formatet och strikt JSON-schema.')
    return HTTPException(502, f'{name} är tillfälligt otillgänglig eller gav ett ogiltigt svar. Försök igen senare.')


async def request_json(client, settings, method, url, *, headers=None, body=None) -> dict:
    """Read at most the server byte limit, including decoded streaming bodies."""
    try:
        async with client.stream(method, url, headers=headers, json=body) as response:
            if response.status_code < 200 or response.status_code >= 300:
                raise upstream_error(response.status_code, settings.provider, response.headers.get('Retry-After', ''))
            chunks = bytearray()
            async for chunk in response.aiter_bytes():
                if len(chunks) + len(chunk) > settings.max_provider_bytes:
                    raise HTTPException(502, 'AI-leverantörens svar överskred serverns storleksgräns.')
                chunks.extend(chunk)
        data = json.loads(chunks)
        if not isinstance(data, dict):
            raise ValueError('Expected an object')
        return data
    except httpx.TimeoutException:
        raise HTTPException(504, 'AI-leverantören svarade inte i tid. Försök igen eller kontrollera serverns tidsgräns.') from None
    except httpx.ConnectError:
        raise HTTPException(503, 'Det gick inte att ansluta till AI-leverantören. Kontrollera serverns anslutning och leverantörens tillgänglighet.') from None
    except (httpx.HTTPError, ValueError, UnicodeError):
        raise HTTPException(502, 'AI-leverantören gav ett ogiltigt svar. Försök igen senare.') from None


def validated_text(raw: str) -> str:
    try:
        if not isinstance(raw, str):
            raise ValueError('Expected text')
        result = ModelText.model_validate_json(raw, strict=True).text
        if not result.strip():
            raise ValueError('Empty text')
        return result
    except (ValidationError, ValueError, TypeError):
        raise HTTPException(502, 'AI-leverantören gav inte ett giltigt strukturerat textsvar. Försök igen.') from None
