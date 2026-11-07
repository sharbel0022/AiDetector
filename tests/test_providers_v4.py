"""Provider boundaries: configuration, paid calls, sanitized failures and bounds."""
import asyncio
import json

import httpx
import pytest
from fastapi import HTTPException

from ai.contracts import RewriteRequest
from ai.providers import configuration_error, generate, generation_body
from backend.config import Settings


SOURCE = 'Det här är en text med svenska tecken: åäö och en emoji 🌍.'
MISSING = 'OpenAI är inte konfigurerat. Lägg till OPENAI_API_KEY och OPENAI_MODEL i serverns .env.'


def configured(**overrides):
    return Settings(**dict({'provider': 'openai', 'model': 'test-model', 'openai_key': 'secret-server-key'}, **overrides))


def response(text=SOURCE, **changes):
    data = {'status': 'completed', 'output': [{'type': 'message', 'content': [
        {'type': 'output_text', 'text': json.dumps({'text': text}, ensure_ascii=False)}]}]}
    data.update(changes)
    return data


def run(settings, handler, **kwargs):
    return asyncio.run(generate(settings, RewriteRequest(text=SOURCE), SOURCE,
                                httpx.MockTransport(handler), **kwargs))


@pytest.mark.parametrize('overrides', [{'model': ''}, {'openai_key': ''}, {'model': ' ', 'openai_key': ' '}])
def test_missing_openai_configuration_never_contacts_network(overrides):
    settings = configured(**overrides)
    assert configuration_error(settings) == MISSING
    def network(request):
        pytest.fail('Unconfigured OpenAI must not contact the network')
    with pytest.raises(HTTPException) as error:
        run(settings, network)
    assert error.value.status_code == 503
    assert error.value.detail == MISSING


def test_missing_compatible_key_never_contacts_network():
    settings = configured(provider='compatible', compatible_url='https://model.example/v1', compatible_key='')
    def network(request):
        pytest.fail('Unconfigured compatible provider must not contact the network')
    assert 'AI_COMPATIBLE_KEY' in configuration_error(settings)
    with pytest.raises(HTTPException) as error:
        run(settings, network)
    assert error.value.status_code == 503


def test_responses_protocol_unicode_and_success_only_model_cache():
    settings = configured()
    calls = []
    def network(request):
        calls.append((request.method, request.url.path))
        assert request.headers['Authorization'] == 'Bearer secret-server-key'
        assert request.url.host == 'api.openai.com'
        if request.method == 'GET':
            return httpx.Response(200, json={'id': 'test-model', 'object': 'model'})
        body = json.loads(request.content)
        assert body['model'] == 'test-model'
        assert body['store'] is False
        assert body['max_output_tokens'] == 128
        assert json.loads(body['input'])['text'] == SOURCE
        assert body['text']['format']['strict'] is True
        assert body['text']['format']['schema']['additionalProperties'] is False
        return httpx.Response(200, json=response())
    assert run(settings, network, output_tokens=128) == SOURCE
    assert run(settings, network, output_tokens=128) == SOURCE
    assert calls == [('GET', '/v1/models/test-model'), ('POST', '/v1/responses'), ('POST', '/v1/responses')]


@pytest.mark.parametrize('status,expected,word', [(401, 503, 'API-nyckeln'), (403, 503, 'behörighet'),
                                               (404, 503, 'modellen'), (429, 429, 'gräns'), (500, 502, 'tillfälligt'),
                                               (400, 502, 'JSON-schema'), (422, 502, 'JSON-schema')])
@pytest.mark.parametrize('stage', ['metadata', 'generation'])
def test_upstream_errors_are_distinct_sanitized_and_not_retried(status, expected, word, stage):
    calls = []
    def network(request):
        calls.append(request.method)
        if request.method == 'GET' and stage == 'generation':
            return httpx.Response(200, json={'id': 'test-model'})
        return httpx.Response(status, text='secret-server-key PRIVATE USER TEXT', headers={'Retry-After': '20'})
    with pytest.raises(HTTPException) as error:
        run(configured(), network)
    assert error.value.status_code == expected
    assert word in error.value.detail
    assert 'secret-server-key' not in str(error.value)
    assert 'PRIVATE USER TEXT' not in str(error.value)
    assert calls == (['GET', 'POST'] if stage == 'generation' else ['GET'])
    if status == 429:
        assert error.value.headers['Retry-After'] == '20'


@pytest.mark.parametrize('exception,status', [(httpx.ReadTimeout('secret-server-key'), 504),
                                            (httpx.ConnectError('secret-server-key'), 503)])
def test_transport_failures_are_sanitized(exception, status):
    def network(request):
        raise exception
    with pytest.raises(HTTPException) as error:
        run(configured(), network)
    assert error.value.status_code == status
    assert 'secret-server-key' not in str(error.value)


@pytest.mark.parametrize('data', [
    response(status='incomplete', incomplete_details={'reason': 'max_output_tokens'}),
    response(output=[{'type': 'message', 'status': 'incomplete', 'content': [
        {'type': 'output_text', 'text': json.dumps({'text': SOURCE})}]}]),
    response(output=[{'type': 'message', 'content': [{'type': 'refusal', 'refusal': 'private refusal'}]}]),
    response(output=[{'type': 'message', 'content': [{'type': 'output_text', 'text': 'invalid json'}]}]),
    response(output=[{'type': 'message', 'content': [{'type': 'output_text', 'text': '{"text":"valid","extra":true}'}]}]),
    response(output=[{'type': 'message', 'content': [{'type': 'output_text', 'text': '{"text":123}'}]}]),
    response(text=' '), response(text='a' * 16001), response(output=[]),
])
def test_incomplete_refused_or_malformed_output_rejected(data):
    posts = []
    def network(request):
        if request.method == 'GET':
            return httpx.Response(200, json={'id': 'test-model'})
        posts.append(request)
        return httpx.Response(200, json=data)
    with pytest.raises(HTTPException) as error:
        run(configured(), network)
    assert error.value.status_code == 502
    assert 'private refusal' not in error.value.detail
    assert len(posts) == 1


def test_provider_response_bytes_bounded_before_parsing():
    def network(request):
        if request.method == 'GET':
            return httpx.Response(200, json={'id': 'test-model'})
        return httpx.Response(200, content=b'x' * 1001)
    with pytest.raises(HTTPException) as error:
        run(configured(max_provider_bytes=1000), network)
    assert error.value.status_code == 502


def test_metadata_mismatch_blocks_generation_and_is_not_cached():
    calls = []
    def network(request):
        calls.append(request.method)
        return httpx.Response(200, json={'id': 'different-model'})
    settings = configured()
    for _ in range(2):
        with pytest.raises(HTTPException) as error:
            run(settings, network)
        assert error.value.status_code == 502
    assert calls == ['GET', 'GET']


def test_changed_credentials_invalidate_model_cache():
    settings = configured()
    calls = []
    def network(request):
        calls.append(request.method)
        return httpx.Response(200, json={'id': 'test-model'} if request.method == 'GET' else response())
    run(settings, network)
    settings.openai_key = 'different-server-key'
    run(settings, network)
    assert calls == ['GET', 'POST', 'GET', 'POST']


def test_model_access_cache_expires(monkeypatch):
    from ai.providers import openai_provider
    now = [1000.0]
    monkeypatch.setattr(openai_provider.time, 'monotonic', lambda: now[0])
    settings = configured()
    calls = []
    def network(request):
        calls.append(request.method)
        return httpx.Response(200, json={'id': 'test-model'} if request.method == 'GET' else response())
    run(settings, network)
    now[0] += 301
    run(settings, network)
    assert calls == ['GET', 'POST', 'GET', 'POST']


def test_unconfigured_openai_app_starts_and_reports_safe_status():
    from fastapi.testclient import TestClient
    from backend.main import create_app
    def network(request):
        pytest.fail('Health and unconfigured readiness must not contact OpenAI')
    with TestClient(create_app(configured(openai_key=''), transport=httpx.MockTransport(network))) as client:
        health = client.get('/api/health')
        assert health.status_code == 200
        assert health.json()['provider_configured'] is False
        readiness = client.get('/api/provider-status')
        assert readiness.status_code == 200
        assert readiness.json()['ready'] is False
        assert readiness.json()['verified'] is False
        assert readiness.json()['message'] == MISSING


def test_untrusted_rate_limit_header_is_not_reflected():
    with pytest.raises(HTTPException) as error:
        run(configured(), lambda request: httpx.Response(429, headers={'Retry-After': 'secret-server-key'}))
    assert error.value.headers == {'Retry-After': '30'}


def test_cancelled_request_is_not_retried_or_swallowed():
    async def check():
        started = asyncio.Event()
        cancelled = asyncio.Event()
        async def network(request):
            if request.method == 'GET':
                return httpx.Response(200, json={'id': 'test-model'})
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        task = asyncio.create_task(generate(configured(), RewriteRequest(text=SOURCE), SOURCE, httpx.MockTransport(network)))
        await asyncio.wait_for(started.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert cancelled.is_set()
    asyncio.run(check())


def test_environment_provider_model_precedence_and_safe_openai_default(monkeypatch):
    for key in ('AI_MODEL', 'OPENAI_MODEL', 'OLLAMA_MODEL'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('AI_PROVIDER', 'openai')
    assert Settings().model == ''
    monkeypatch.setenv('AI_MODEL', 'legacy')
    assert Settings().model == 'legacy'
    monkeypatch.setenv('OPENAI_MODEL', 'explicit-openai')
    monkeypatch.setenv('OLLAMA_MODEL', 'explicit-ollama')
    assert Settings().model == 'explicit-openai'
    assert Settings(provider='ollama').model == 'explicit-ollama'
    assert Settings(provider='compatible').model == 'legacy'
    assert Settings(model='constructor').model == 'constructor'
    monkeypatch.setenv('OPENAI_MODEL', '')
    assert Settings().model == ''


def test_new_environment_aliases_take_precedence(monkeypatch):
    monkeypatch.setenv('TEXTLAB_ENV', 'production')
    monkeypatch.setenv('APP_ENV', 'production')
    monkeypatch.setenv('TEXTLAB_REQUEST_TIMEOUT', '120')
    monkeypatch.setenv('AI_REQUEST_TIMEOUT', '30')
    monkeypatch.setenv('AI_MAX_INPUT_CHARS', '4096')
    settings = Settings()
    assert settings.environment == 'production'
    assert settings.request_timeout == 30
    assert settings.max_input_chars == 4096


@pytest.mark.parametrize('app_env,legacy_env', [('development', 'production'), ('production', 'development')])
def test_conflicting_environment_aliases_fail_closed(monkeypatch, app_env, legacy_env):
    monkeypatch.setenv('APP_ENV', app_env)
    monkeypatch.setenv('TEXTLAB_ENV', legacy_env)
    with pytest.raises(ValueError, match='APP_ENV.*TEXTLAB_ENV'):
        Settings()


@pytest.mark.parametrize('app_env,legacy_env', [(' PRODUCTION ', 'production'), ('', 'production')])
def test_environment_aliases_are_normalized_without_downgrading(monkeypatch, app_env, legacy_env):
    monkeypatch.setenv('APP_ENV', app_env)
    monkeypatch.setenv('TEXTLAB_ENV', legacy_env)
    assert Settings().environment == 'production'


@pytest.mark.parametrize('environment', ['prodution', '', 'staging'])
def test_unknown_environment_cannot_disable_production_guards(environment):
    with pytest.raises(ValueError, match='environment'):
        Settings(environment=environment)


@pytest.mark.parametrize('limit', [9, 8001, True])
def test_input_limit_is_bounded(limit):
    with pytest.raises(ValueError):
        Settings(max_input_chars=limit)


def test_secrets_are_excluded_from_settings_repr():
    settings = configured(compatible_key='private-compatible', app_token='private-token', user_token_hashes={'user': 'private-hash'})
    for secret in ('secret-server-key', 'private-compatible', 'private-token', 'private-hash'):
        assert secret not in repr(settings)


@pytest.mark.parametrize('provider,cap_field', [('ollama', 'options'), ('openai', 'max_output_tokens'), ('compatible', 'max_tokens')])
def test_output_budget_cannot_exceed_server_limit(provider, cap_field):
    settings = configured(provider=provider, max_output_tokens=256)
    body = generation_body(settings, RewriteRequest(text=SOURCE), SOURCE, output_tokens=500)
    cap = body[cap_field]['num_predict'] if provider == 'ollama' else body[cap_field]
    assert cap == 256
