"""The application AI boundary: providers never decide validation or access policy.

HTTP callers inject the backend's quota- and disconnect-aware generation function.
Direct Python callers are trusted server-side callers; credentials remain in Settings.
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from fastapi import HTTPException
from pydantic import ValidationError

from ai.contracts import DetectRequest, ModelText, RewriteRequest, utf16_length
from ai.humanizer.rewrite import make_diff
from ai.humanizer.validation import PreservationError, protect_text, restore_text
from ai.providers import configuration_error, generate
from backend.config import Settings

Generate = Callable[[RewriteRequest, str, float, int | None], Awaitable[str]]

REVIEW_WARNING = (
    'Skyddade textdelar och kända tal med enheter har kontrollerats exakt. '
    'Begränsade kontroller söker ändrade markörer för negation, osäkerhet, '
    'skyldighet och orsak; de verifierar inte betydelsen. Namn identifieras '
    'med heuristik och valda exakta ord. Granska fakta, relationer, nyanser '
    'och tillagda påståenden; semantisk likvärdighet är inte verifierad.'
)


class AIService:
    """Coordinate descriptive analysis, protected editing and model readiness."""

    def __init__(self, settings: Settings | None = None, transport=None,
                 generate_fn: Generate | None = None):
        self.settings = settings or Settings()
        self.transport = transport
        self._generate_fn = generate_fn

    async def _generate(self, payload: RewriteRequest, protected: str,
                        timeout: float, cap: int | None = None) -> str:
        error = configuration_error(self.settings)
        if error:
            raise HTTPException(503, error)
        if self._generate_fn is not None:
            return await self._generate_fn(payload, protected, timeout, cap)
        async with asyncio.timeout(timeout):
            return await generate(self.settings, payload, protected, self.transport, cap)

    async def detect(self, text: str, language: str = 'auto') -> dict[str, Any]:
        # Local classifier inference never sends source text to a model provider.
        # Move bounded CPU work off the event loop; the runtime independently
        # gates document, calibrated-probability and segment-share presentation.
        from ai.detector.runtime import analyze_v5
        try:
            payload = DetectRequest(text=text, language=language)
        except ValidationError:
            raise HTTPException(422, 'Analys kräver 1–12 000 tecken och automatiskt språkval, svenska eller engelska.') from None
        return await asyncio.to_thread(analyze_v5, payload.text, payload.language,
                                       model_path=self.settings.detector_model_path)

    async def humanize(self, text: str, language: str = 'sv', tone: str = 'natural',
                       protected_terms: list[str] | None = None) -> dict[str, Any]:
        try:
            payload = RewriteRequest(text=text, language=language, tone=tone,
                                     protected_terms=protected_terms or [])
        except ValidationError:
            raise HTTPException(422, 'Ogiltig text, språk, tonläge eller skyddade textdelar.') from None
        if utf16_length(payload.text) > self.settings.max_input_chars:
            raise HTTPException(422, f'AI-omskrivning tillåter högst {self.settings.max_input_chars} tecken på den här servern.')
        try:
            protected, mapping = protect_text(payload.text, payload.protected_terms)
        except PreservationError:
            raise HTTPException(422, 'Kontrollera att skyddade ord finns i texten och ta bort __TL_-markörer.') from None
        if len(protected) > 24000:
            raise HTTPException(422, 'Texten innehåller för många skyddade uppgifter. Dela upp den i mindre delar.')
        try:
            output = await self._generate(payload, protected, self.settings.request_timeout)
            # Providers attach actual usage before any restoration/normalization
            # turns the str-compatible result into a plain string. Trusted legacy
            # injected generators may omit it; absence must never become zero.
            usage = getattr(output, 'usage', None)
            output = restore_text(output, mapping, payload.text)
            # Restored quotes/terms can be longer than their placeholders. Apply
            # the browser's UTF-16 output contract to the final returned text.
            output = ModelText(text=output).text
        except PreservationError:
            raise HTTPException(502, 'Modellen ändrade skyddade uppgifter, enheter eller betydelsebärande markörer. Omskrivningen stoppades; originalet är oförändrat.') from None
        except (httpx.TimeoutException, TimeoutError):
            raise HTTPException(504, 'Modellen svarade inte i tid.') from None
        except httpx.ConnectError:
            raise HTTPException(503, 'AI-servern kunde inte nås. Kontrollera Ollama eller serverinställningarna.') from None
        except (httpx.HTTPError, ValueError, KeyError, TypeError, IndexError):
            raise HTTPException(502, 'AI-tjänsten returnerade inget giltigt, fullständigt svar. Kontrollera serverns modellkonfiguration.') from None

        unchanged = output.strip() == payload.text.strip()
        if unchanged:
            # Avoid presenting a trim-only edit as a meaningful improvement.
            output = payload.text
        return {
            'text': output, 'provider': self.settings.provider, 'model': self.settings.model,
            'usage': usage,
            'diff': make_diff(payload.text, output), 'protected_count': len(mapping),
            'unchanged': unchanged,
            'explanation': ('Modellen lämnade texten oförändrad. Originalet har behållits exakt; '
                            'ingen språkförbättring eller betydelsekontroll är verifierad.'
                            if unchanged else 'Ett redigeringsförslag finns. Jämför det med originalet och granska betydelsen.'),
            'review_required': True,
            'preservation': {
                'exact_values_checked': True, 'semantic_equivalence_verified': False,
                'names': 'heuristic_and_explicit_terms',
                'meaning_risk_checks': 'bounded_markers_scope_anchor_order_timeline_and_units',
            },
            'warning': REVIEW_WARNING,
        }

    async def provider_status(self) -> dict[str, Any]:
        result = {'provider': self.settings.provider, 'model': self.settings.model,
                  'configured': configuration_error(self.settings) is None,
                  'ready': False, 'verified': False}
        try:
            sample = RewriteRequest(text='This is a readiness check.', language='en')
            await self._generate(sample, sample.text,
                                 min(self.settings.readiness_timeout, self.settings.request_timeout), 128)
            return {**result, 'ready': True, 'verified': True,
                    'message': 'Den konfigurerade modellen har svarat med ett giltigt testsvar. Kvalitet och betydelse är inte verifierade.'}
        except HTTPException as exc:
            if exc.status_code in (429, 499):
                raise
            return {**result, 'message': exc.detail}
        except (httpx.HTTPError, TimeoutError, ValueError, KeyError, TypeError, IndexError):
            return {**result, 'message': 'Den konfigurerade modellen kunde inte generera ett giltigt testsvar i tid. Kontrollera modell, åtkomst och server.'}
