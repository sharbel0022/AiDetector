"""Authenticated HTTP boundary for TextLab's central AI service."""
from __future__ import annotations

import asyncio
import hmac
import hashlib
import re
import sqlite3
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.datastructures import MutableHeaders

from ai.ai import AIService
from ai.contracts import DetectRequest, ModelText, RewriteRequest
from ai.humanizer.prompts import SYSTEM, MODES, SCHEMA
from ai.humanizer.rewrite import make_diff
from ai.humanizer.validation import PreservationError, TOKEN, protect_text, restore_text
from ai.providers import configuration_error, generate, generation_body
from backend.config import Settings
from backend.limits import SharedLimits

# The imported V3 helpers remain available here for existing offline tools and
# regression tests. Their implementation has a single home in the ai package.

class BodyLimit:
    """Bound actual ASGI bytes, including chunked bodies; do not trust Content-Length."""
    def __init__(self, app, limit=100000, timeout=10):self.app,self.limit,self.timeout=app,limit,timeout
    async def __call__(self,scope,receive,send):
        if scope['type']!='http' or scope['method'] not in ('POST','PUT','PATCH'):
            return await self.app(scope,receive,send)
        messages=[]; size=0
        try:
            async with asyncio.timeout(self.timeout):
                while True:
                    message=await receive()
                    if message['type']=='http.disconnect':return
                    size+=len(message.get('body',b''))
                    if size>self.limit:
                        return await JSONResponse({'detail':'För stor begäran.'},413)(scope,receive,send)
                    messages.append(message)
                    if not message.get('more_body',False):break
        except TimeoutError:
            return await JSONResponse({'detail': 'Begäran tog för lång tid.'},408)(scope,receive,send)
        pending=iter(messages)
        async def replay():
            try:return next(pending)
            except StopIteration:return await receive()
        await self.app(scope,replay,send)


class SecurityHeaders:
    """Pure ASGI preserves disconnect delivery to the generation cancellation task."""
    def __init__(self, app, authorize):
        self.app, self.authorize = app, authorize

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        async def with_headers(message):
            if message['type'] == 'http.response.start':
                headers = MutableHeaders(scope=message)
                headers.update({'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
                                'Referrer-Policy': 'no-referrer', 'X-Frame-Options': 'DENY',
                                'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
                                'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' https: http://127.0.0.1:* http://localhost:* http://[::1]:*; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"})
            await send(message)
        try:
            if scope['path'] in ('/api/rewrite', '/api/provider-status', '/api/detect') and scope['method'] != 'OPTIONS':
                self.authorize(Request(scope, receive))
        except HTTPException as exc:
            return await JSONResponse({'detail': exc.detail}, exc.status_code, headers=exc.headers)(scope, receive, with_headers)
        await self.app(scope, receive, with_headers)

def create_app(settings: Settings | None = None, transport=None) -> FastAPI:
    s=settings or Settings()
    url=urlparse(s.ollama_url)
    if url.scheme not in ('http','https') or not url.hostname or url.username or url.password:
        raise ValueError('Invalid server-configured Ollama URL')
    if url.scheme=='http' and url.hostname not in ('127.0.0.1','localhost','::1'):
        raise ValueError('Remote Ollama requires HTTPS')
    if s.compatible_url:
        compatible = urlparse(s.compatible_url)
        if compatible.scheme not in ('http','https') or not compatible.hostname or compatible.username or compatible.password or compatible.query or compatible.fragment:
            raise ValueError('Invalid server-configured compatible provider URL')
        if compatible.scheme == 'http' and compatible.hostname not in ('127.0.0.1', 'localhost', '::1'):
            raise ValueError('Remote compatible provider requires HTTPS')
    if s.auth_mode not in ('private', 'multiuser'):
        raise ValueError('Invalid TEXTLAB_AUTH_MODE')
    if s.auth_mode == 'multiuser':
        hashes = s.user_token_hashes
        if not isinstance(hashes, dict) or not hashes or len(hashes) > 10000 or any(not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', key) or not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{64}', value) for key,value in hashes.items()) or len(set(hashes.values())) != len(hashes):
            raise ValueError('Multiuser requires unique per-user SHA-256 token hashes')
        if not s.state_db or not Path(s.state_db).is_absolute():
            raise ValueError('Multiuser requires an absolute shared local TEXTLAB_STATE_DB path')
    if s.environment=='production' and ((s.auth_mode == 'private' and len(s.app_token)<32) or not s.allowed_hosts or '*' in s.allowed_hosts or 'testserver' in s.allowed_hosts or not s.allowed_origins or '*' in s.allowed_origins):
        raise ValueError('Production requires authentication and explicit hosts/origins')
    if s.environment == 'production':
        if any('*' in host or not host.strip() for host in s.allowed_hosts):
            raise ValueError('Production requires explicit hosts')
        for origin in s.allowed_origins:
            parsed = urlparse(origin)
            local = parsed.hostname in ('127.0.0.1', 'localhost', '::1')
            if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path or (parsed.scheme != 'https' and not (local and parsed.scheme == 'http')):
                raise ValueError('Production requires explicit HTTPS origins (HTTP is loopback-only)')
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 1 for value in (s.requests_per_minute, s.max_concurrent, s.daily_token_budget, s.global_daily_token_budget, s.max_body_bytes, s.max_provider_bytes)) or not 16 <= s.max_output_tokens <= 16000 or not .01 <= s.request_timeout <= 300 or not .01 <= s.body_timeout <= 30:
        raise ValueError('Invalid resource limits')
    if not isinstance(s.max_input_chars, int) or isinstance(s.max_input_chars, bool) or not 10 <= s.max_input_chars <= 8000:
        raise ValueError('AI_MAX_INPUT_CHARS must be an integer between 10 and 8000')
    try:
        limits = SharedLimits(s.state_db)
    except (sqlite3.Error, OSError):
        raise ValueError('Shared quota storage is not available') from None
    app=FastAPI(title='TextLab',version='4.0.0',docs_url='/api/docs' if s.environment!='production' else None,redoc_url=None,openapi_url='/api/openapi.json' if s.environment!='production' else None)
    app.add_middleware(BodyLimit, limit=s.max_body_bytes, timeout=s.body_timeout)
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=list(s.allowed_hosts))
    readiness = {'expires': 0, 'result': None}
    readiness_lock = asyncio.Lock()

    def authorize(request: Request):
        host=request.client.host if request.client else ''
        provided=request.headers.get('Authorization','')
        provided = provided[7:] if provided.startswith('Bearer ') else ''
        if s.auth_mode == 'multiuser':
            digest = hashlib.sha256(provided.encode()).hexdigest()
            principal = None
            for user, expected in s.user_token_hashes.items():
                if hmac.compare_digest(digest, expected):
                    principal = user
            if principal is None:
                raise HTTPException(401, 'Ange en giltig personlig åtkomstkod.', headers={'WWW-Authenticate': 'Bearer'})
        elif s.app_token:
            if not hmac.compare_digest(provided.encode('utf-8'),s.app_token.encode('utf-8')):
                raise HTTPException(401,'Ange rätt åtkomstkod under Inställningar.', headers={'WWW-Authenticate': 'Bearer'})
            principal = 'private'
        elif host not in ('127.0.0.1','::1','testclient'):
            raise HTTPException(403,'Extern åtkomst kräver TEXTLAB_TOKEN på servern.')
        else:
            principal = 'local'
        origin=request.headers.get('origin')
        if origin and origin not in s.allowed_origins:
            raise HTTPException(403,'Webbplatsens origin är inte tillåten på servern.')
        try:
            limits.rate(principal, s.requests_per_minute)
        except sqlite3.Error:
            raise HTTPException(503, 'Säker kvotkontroll är tillfälligt otillgänglig.') from None
        request.state.principal = principal

    async def bounded_generate(request, payload, protected, timeout, cap=None):
        # Bound the actual nested JSON body, including source, mode instructions,
        # schema and escaped Unicode/backslashes. The shared
        # builder also serves readiness probes and all provider adapters. Headers
        # and server credentials are never part of this payload or quota storage.
        body = generation_body(s, payload, protected, cap)
        body_bytes = httpx.Request('POST', 'http://localhost', json=body).content
        reserve_tokens = len(body_bytes) + 1024 + (cap or s.max_output_tokens)
        try:
            lease = limits.reserve(request.state.principal, reserve_tokens, s, timeout)
        except sqlite3.Error:
            raise HTTPException(503, 'Säker kvotkontroll är tillfälligt otillgänglig.') from None
        async def disconnected():
            while True:
                if await request.is_disconnected():
                    raise HTTPException(499, 'Anropet avbröts.')
                await asyncio.sleep(.05)
        work = asyncio.create_task(generate(s, payload, protected, transport, cap))
        monitor = asyncio.create_task(disconnected())
        try:
            async with asyncio.timeout(timeout):
                done, _ = await asyncio.wait((work, monitor), return_when=asyncio.FIRST_COMPLETED)
                return await next(iter(done))
        finally:
            for task in (work, monitor):
                if not task.done():
                    task.cancel()
            await asyncio.gather(work, monitor, return_exceptions=True)
            try:
                limits.release(lease)
            except sqlite3.Error:
                # Fail closed until the short lease expires if the database is unavailable.
                pass

    app.add_middleware(SecurityHeaders, authorize=authorize)

    # CORS also wraps errors returned by authentication, before body consumption.
    app.add_middleware(CORSMiddleware,allow_origins=list(s.allowed_origins),allow_methods=['GET','POST'],allow_headers=['Authorization','Content-Type'])

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request,exc):
        return JSONResponse({'detail':'Ogiltig inmatning. Ange 10–8 000 tecken, ett giltigt tonläge och svenska eller engelska.'},422)

    @app.get('/api/health')
    async def health():
        return {'status':'ok','version':'4.0.0','provider':s.provider,'model':s.model,'auth_required':bool(s.app_token) or s.auth_mode == 'multiuser','auth_mode':s.auth_mode,'model_verified':False,'text_storage':False,'max_input_chars':s.max_input_chars,'provider_configured':configuration_error(s) is None}

    @app.get('/api/provider-status')
    async def provider_status(request: Request):
        async with readiness_lock:
            if readiness['result'] is not None and readiness['expires'] > time.monotonic():
                return readiness['result']
            result = await service_for(request).provider_status()
            readiness.update(result=result, expires=time.monotonic() + (60 if result['ready'] else 5))
            return result

    def service_for(request: Request) -> AIService:
        async def guarded(payload, protected, timeout, cap=None):
            return await bounded_generate(request, payload, protected, timeout, cap)
        return AIService(s, transport=transport, generate_fn=guarded)

    @app.post('/api/detect')
    async def detect(payload: DetectRequest, request: Request):
        return await service_for(request).detect(payload.text, payload.language)

    @app.post('/api/rewrite')
    async def rewrite(payload: RewriteRequest, request: Request):
        return await service_for(request).humanize(payload.text, payload.language, payload.tone, payload.protected_terms)

    built=Path(__file__).resolve().parent.parent/'dist'
    if built.is_dir():app.mount('/',StaticFiles(directory=built,html=True),name='frontend')
    return app

app=create_app()
