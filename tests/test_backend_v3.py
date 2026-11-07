"""Behavioral regressions for v3; provider doubles replace network I/O only."""
import asyncio
import hashlib
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.main import Settings, create_app, protect_text, restore_text, PreservationError

TEXT = 'Alice Smith paid 250 kr on 2 November 2026. See [Smith, 2026] and https://example.org.'


def config(**values):
    settings = Settings()
    for key, value in values.items():
        setattr(settings, key, value)
    return settings


def provider(request):
    if request.method == 'GET':
        assert request.url.path.startswith('/v1/models/')
        assert not request.content
        return httpx.Response(200, json={'id': request.url.path.rsplit('/', 1)[-1]})
    body = json.loads(request.content)
    if request.url.path.endswith('/responses'):
        source = json.loads(body['input'])['text']
        return httpx.Response(200, json={'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': json.dumps({'text': source})}]}]})
    source = json.loads(body['messages'][-1]['content'])['text']
    if request.url.path.endswith('/chat/completions'):
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps({'text': source})}}]})
    return httpx.Response(200, json={'done': True, 'done_reason': 'stop', 'message': {'content': json.dumps({'text': source})}})


def app_client(settings=None, handler=provider):
    return TestClient(create_app(settings or config(), transport=httpx.MockTransport(handler)))


@pytest.mark.parametrize('tone', ['natural', 'simple', 'professional', 'academic', 'concise', 'detailed'])
def test_six_modes_reach_provider_with_distinct_editing_instruction(tone):
    def handler(request):
        body = json.loads(request.content)
        assert json.loads(body['messages'][-1]['content'])['tone'] == tone
        assert 'Mode guidance:' in body['messages'][0]['content']
        return provider(request)
    with app_client(handler=handler) as client:
        response = client.post('/api/rewrite', json={'text': TEXT, 'tone': tone})
        assert response.status_code == 200, response.text
        assert response.json()['preservation']['semantic_equivalence_verified'] is False


def test_names_dates_single_quotes_and_explicit_terms_are_opaque():
    text = "Åsa Öberg met Alice Smith on 2 November 2026 and said 'Keep this exact'. BrandName remains."
    with app_client() as client:
        response = client.post('/api/rewrite', json={'text': text, 'protected_terms': ['BrandName']})
        assert response.status_code == 200, response.text
        assert response.json()['text'] == text
        assert response.json()['protected_count'] >= 5


def test_proper_names_and_word_dates_are_hidden_from_model():
    protected, mapping = protect_text(TEXT)
    assert 'Alice Smith' not in protected
    assert '2 November 2026' not in protected
    assert restore_text(protected, mapping, TEXT) == TEXT


@pytest.mark.parametrize('suffix', [' https://invented.example', ' [invented reference]', ' "invented quotation"'])
def test_new_protected_fact_categories_are_rejected(suffix):
    protected, mapping = protect_text(TEXT)
    with pytest.raises(PreservationError):
        restore_text(protected + suffix, mapping, TEXT)


def test_explicit_term_must_exist_without_echoing_source():
    with app_client() as client:
        response = client.post('/api/rewrite', json={'text': 'PRIVATE source text', 'protected_terms': ['absent']})
        assert response.status_code == 422
        assert 'PRIVATE' not in response.text


def test_openai_configuration_alone_is_not_ready():
    with app_client(config(provider='openai', model='inaccessible-model', openai_key='private-key'), lambda request: httpx.Response(403, text='private error')) as client:
        result = client.get('/api/provider-status').json()
        assert result['ready'] is False
        assert result['verified'] is False
        assert 'private' not in json.dumps(result)


def test_ollama_installed_but_generation_fails_is_not_ready():
    def unavailable(request):
        if request.method == 'GET':
            return httpx.Response(200, json={'models': [{'name': 'qwen2.5:7b'}]})
        return httpx.Response(500)
    with app_client(handler=unavailable) as client:
        assert client.get('/api/provider-status').json()['ready'] is False


def test_ready_means_successful_configured_model_generation_cached():
    requests = []
    def handler(request):
        requests.append(request)
        return provider(request)
    with app_client(config(provider='openai', model='actual-configured-model', openai_key='key'), handler) as client:
        first = client.get('/api/provider-status').json()
        second = client.get('/api/provider-status').json()
        assert first['ready'] is True and first['verified'] is True
        assert second['ready'] is True
        assert len(requests) == 2
        assert requests[0].method == 'GET'
        assert requests[1].method == 'POST'
        assert json.loads(requests[1].content)['model'] == 'actual-configured-model'
        assert json.loads(requests[1].content)['max_output_tokens'] <= 128


def test_compatible_provider_uses_server_url_and_bounded_schema():
    def handler(request):
        body = json.loads(request.content)
        assert str(request.url) == 'https://model.example/v1/chat/completions'
        assert request.headers['authorization'] == 'Bearer server-key'
        assert body['response_format']['json_schema']['strict'] is True
        assert body['max_tokens'] == 500
        return provider(request)
    settings = config(provider='compatible', model='configured-model', compatible_url='https://model.example/v1', compatible_key='server-key', max_output_tokens=500)
    with app_client(settings, handler) as client:
        assert client.post('/api/rewrite', json={'text': TEXT}).status_code == 200


def multiuser(tmp_path, **overrides):
    values = dict(auth_mode='multiuser', state_db=str(tmp_path / 'quotas.sqlite3'),
                  user_token_hashes={'alice': hashlib.sha256(b'a' * 40).hexdigest(), 'bob': hashlib.sha256(b'b' * 40).hexdigest()})
    values.update(overrides)
    return config(**values)


@pytest.mark.parametrize('changes', [{'state_db': ''}, {'user_token_hashes': {}}, {'user_token_hashes': {'alice': 'plaintext-token'}}])
def test_public_auth_configuration_fails_closed(tmp_path, changes):
    with pytest.raises(ValueError):
        create_app(multiuser(tmp_path, **changes))


def test_public_per_user_auth_and_rate_limits_shared_across_workers(tmp_path):
    settings = multiuser(tmp_path, requests_per_minute=1)
    with app_client(settings) as worker_a, app_client(settings) as worker_b:
        assert worker_a.post('/api/rewrite', json={'text': TEXT}).status_code == 401
        assert worker_a.post('/api/rewrite', json={'text': TEXT}, headers={'Authorization': 'Bearer wrong'}).status_code == 401
        assert worker_a.post('/api/rewrite', json={'text': TEXT}, headers={'Authorization': 'Bearer ' + 'a' * 40}).status_code == 200
        limited = worker_b.post('/api/rewrite', json={'text': TEXT}, headers={'Authorization': 'Bearer ' + 'a' * 40})
        assert limited.status_code == 429
        assert limited.headers['retry-after']
        assert worker_b.post('/api/rewrite', json={'text': TEXT}, headers={'Authorization': 'Bearer ' + 'b' * 40}).status_code == 200
    stored = (tmp_path / 'quotas.sqlite3').read_bytes()
    assert b'Alice Smith' not in stored
    assert b'a' * 40 not in stored


def test_shared_daily_budget_reserves_before_upstream_cost(tmp_path):
    settings = multiuser(tmp_path, daily_token_budget=1)
    def never(request):
        pytest.fail('exhausted budget must not contact provider')
    with app_client(settings, never) as client:
        result = client.post('/api/rewrite', json={'text': TEXT}, headers={'Authorization': 'Bearer ' + 'a' * 40})
        assert result.status_code == 429


def test_bounded_upstream_response_is_rejected():
    def oversized(request):
        response = provider(request).json()
        response['metadata'] = 'x' * 1000
        return httpx.Response(200, json=response)
    with app_client(config(max_provider_bytes=256), oversized) as client:
        assert client.post('/api/rewrite', json={'text': TEXT}).status_code == 502


def test_actual_body_limit_is_configurable_and_applies_before_parse():
    with app_client(config(max_body_bytes=256)) as client:
        assert client.post('/api/rewrite', content='x' * 257).status_code == 413


def test_remote_compatible_http_is_rejected():
    with pytest.raises(ValueError):
        create_app(config(provider='compatible', compatible_url='http://unsafe.example/v1'))


def test_multiuser_ignores_forged_forwarded_address(tmp_path):
    settings = multiuser(tmp_path, requests_per_minute=1)
    headers = {'Authorization': 'Bearer ' + 'a' * 40, 'X-Forwarded-For': '192.0.2.1'}
    with app_client(settings) as client:
        assert client.post('/api/rewrite', json={'text': TEXT}, headers=headers).status_code == 200
        headers['X-Forwarded-For'] = '192.0.2.2'
        assert client.post('/api/rewrite', json={'text': TEXT}, headers=headers).status_code == 429


def test_global_concurrency_is_shared_between_app_workers(tmp_path):
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        async def slow(request):
            entered.set()
            await release.wait()
            return provider(request)
        settings = multiuser(tmp_path, max_concurrent=1)
        app_a = create_app(settings, transport=httpx.MockTransport(slow))
        app_b = create_app(settings, transport=httpx.MockTransport(slow))
        headers = {'Authorization': 'Bearer ' + 'a' * 40}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app_a), base_url='http://localhost') as a, httpx.AsyncClient(transport=httpx.ASGITransport(app_b), base_url='http://localhost') as b:
            first = asyncio.create_task(a.post('/api/rewrite', json={'text': TEXT}, headers=headers))
            await asyncio.wait_for(entered.wait(), 1)
            try:
                second = await asyncio.wait_for(b.post('/api/rewrite', json={'text': TEXT}, headers=headers), .2)
                assert second.status_code == 429
            finally:
                release.set()
                await first
    asyncio.run(scenario())


def test_generation_deadline_cancels_upstream_task_and_releases_slot(tmp_path):
    cancelled = []
    async def slow(request):
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.append(True)
    settings = multiuser(tmp_path, request_timeout=.03, max_concurrent=1)
    with app_client(settings, slow) as client:
        first = client.post('/api/rewrite', json={'text': TEXT}, headers={'Authorization': 'Bearer ' + 'a' * 40})
        assert first.status_code == 504
    assert cancelled == [True]
    with app_client(settings) as client:
        assert client.post('/api/rewrite', json={'text': TEXT}, headers={'Authorization': 'Bearer ' + 'a' * 40}).status_code == 200


def test_chunked_body_has_deadline_before_model_work():
    async def scenario():
        application = create_app(config(body_timeout=.02))
        sent = []
        async def receive():
            await asyncio.sleep(.1)
            return {'type': 'http.request', 'body': b'{', 'more_body': True}
        async def send(message):
            sent.append(message)
        scope = {'type': 'http', 'http_version': '1.1', 'method': 'POST', 'scheme': 'http', 'path': '/api/rewrite', 'raw_path': b'/api/rewrite', 'query_string': b'', 'headers': [(b'host', b'localhost')], 'client': ('127.0.0.1', 1), 'server': ('localhost', 80)}
        await asyncio.wait_for(application(scope, receive, send), .3)
        assert sent[0]['status'] == 408
    asyncio.run(scenario())


@pytest.mark.parametrize('value', [[], {'status': 'completed', 'output': [None]}, {'done': True, 'message': None}])
def test_wrong_upstream_shapes_fail_safely(value):
    with app_client(handler=lambda request: httpx.Response(200, json=value)) as client:
        response = client.post('/api/rewrite', json={'text': TEXT})
        assert response.status_code == 502
        assert 'Traceback' not in response.text


def test_model_may_not_invent_malformed_reserved_markers():
    protected, mapping = protect_text(TEXT)
    with pytest.raises(PreservationError):
        restore_text(protected + ' __TL_fake__', mapping, TEXT)


@pytest.mark.parametrize('overrides', [
    {'allowed_origins': ('*',)},
    {'allowed_origins': ('null',)},
    {'allowed_origins': ('http://public.example',)},
    {'allowed_hosts': ('*.example',)},
])
def test_production_rejects_unsafe_host_or_origin_configuration(overrides):
    settings = config(environment='production', app_token='a' * 40,
                      allowed_hosts=('app.example',), allowed_origins=('https://app.example',))
    for key, value in overrides.items():
        setattr(settings, key, value)
    with pytest.raises(ValueError):
        create_app(settings)


def test_authenticated_error_responses_keep_allowed_cors_origin():
    with app_client(config(app_token='secret')) as client:
        response = client.post('/api/rewrite', json={'text': TEXT}, headers={'Origin': 'http://127.0.0.1:5173'})
        assert response.status_code == 401
        assert response.headers['access-control-allow-origin'] == 'http://127.0.0.1:5173'


def test_sqlite_unavailable_after_startup_fails_closed(tmp_path):
    import sqlite3
    settings = multiuser(tmp_path)
    with app_client(settings) as client:
        database = sqlite3.connect(settings.state_db, timeout=.1, isolation_level=None)
        try:
            database.execute('BEGIN IMMEDIATE')
            response = client.post('/api/rewrite', json={'text': TEXT}, headers={'Authorization': 'Bearer ' + 'a' * 40})
            assert response.status_code == 503
            assert 'sqlite' not in response.text
        finally:
            database.execute('ROLLBACK')
            database.close()


@pytest.mark.parametrize('text,names', [
    ('Alice met Bob in Stockholm yesterday.', ['Alice', 'Bob', 'Stockholm']),
    ('Åsa träffade Erik i Göteborg i går.', ['Åsa', 'Erik', 'Göteborg']),
])
def test_conservative_single_proper_name_candidates_are_protected(text, names):
    protected, mapping = protect_text(text)
    assert all(name not in protected for name in names)
    assert restore_text(protected, mapping, text) == text


def test_compatible_null_choice_fails_safely():
    settings = config(provider='compatible', model='model', compatible_key=('x' * 8), compatible_url='https://example.org/v1')
    with app_client(settings, lambda request: httpx.Response(200, json={'choices': [None]})) as client:
        assert client.post('/api/rewrite', json={'text': TEXT}).status_code == 502


def test_ollama_can_disable_reasoning_to_fit_readiness_budget():
    def no_thinking(request):
        body = json.loads(request.content)
        if body.get('think') is not False:
            return httpx.Response(200, json={'done': True, 'done_reason': 'length', 'message': {'content': '', 'thinking': 'budget exhausted'}})
        return provider(request)
    with app_client(config(ollama_think=False), no_thinking) as client:
        result = client.get('/api/provider-status').json()
        assert result['ready'] is True
        assert result['verified'] is True


def test_daily_reservation_includes_json_escaped_prompt_bytes(tmp_path):
    settings = multiuser(tmp_path, daily_token_budget=20000)
    with app_client(settings) as client:
        result = client.post('/api/rewrite', json={'text': '\\' * 7500}, headers={'Authorization': 'Bearer ' + 'a' * 40})
        assert result.status_code == 429


def test_common_sentence_starters_remain_editable_with_names_protected():
    source = 'Teamet träffade Åsa. Mer information följer. Syftet är tydligt. More information follows.'
    protected, mapping = protect_text(source)
    assert 'Teamet' in protected and 'Mer' in protected and 'Syftet' in protected and 'More' in protected
    assert 'Åsa' not in protected
    assert restore_text(protected, mapping, source) == source


def test_disconnect_cancels_model_and_releases_shared_slot(tmp_path):
    async def scenario():
        entered, cancelled = asyncio.Event(), asyncio.Event()
        async def slow(request):
            entered.set()
            try:
                await asyncio.sleep(10)
            finally:
                cancelled.set()
        settings = multiuser(tmp_path, max_concurrent=1)
        application = create_app(settings, transport=httpx.MockTransport(slow))
        sent, body_sent = [], False
        async def receive():
            nonlocal body_sent
            if not body_sent:
                body_sent = True
                return {'type': 'http.request', 'body': json.dumps({'text': TEXT}).encode(), 'more_body': False}
            await entered.wait()
            return {'type': 'http.disconnect'}
        async def send(message):
            sent.append(message)
        scope = {'type': 'http', 'http_version': '1.1', 'method': 'POST', 'scheme': 'http', 'path': '/api/rewrite', 'raw_path': b'/api/rewrite', 'query_string': b'', 'headers': [(b'host', b'localhost'), (b'content-type', b'application/json'), (b'authorization', b'Bearer ' + b'a' * 40)], 'client': ('127.0.0.1', 1), 'server': ('localhost', 80)}
        await asyncio.wait_for(application(scope, receive, send), .5)
        assert cancelled.is_set()
        assert sent[0]['status'] == 499
        async with httpx.AsyncClient(transport=httpx.ASGITransport(create_app(settings, transport=httpx.MockTransport(provider))), base_url='http://localhost') as client:
            result = await client.post('/api/rewrite', json={'text': TEXT}, headers={'Authorization': 'Bearer ' + 'a' * 40})
            assert result.status_code == 200
    asyncio.run(scenario())


def test_live_smoke_reports_all_cases_and_exits_nonzero_on_failure(tmp_path, monkeypatch):
    from tools import live_model_checks as live
    real_create_app = create_app
    monkeypatch.setattr(live, 'create_app', lambda settings: real_create_app(settings, transport=httpx.MockTransport(lambda request: httpx.Response(503))))
    output = tmp_path / 'live-results.json'
    monkeypatch.setattr('sys.argv', ['live_model_checks.py', '--models', 'fixture-model', '--modes', 'natural', 'simple', '--languages', 'en', '--output', str(output)])
    with pytest.raises(SystemExit) as error:
        live.main()
    assert error.value.code == 1
    report = json.loads(output.read_text(encoding='utf-8'))
    assert len(report['models'][0]['rewrites']) == 2
    assert all(result['http_status'] == 502 for result in report['models'][0]['rewrites'])
    assert report['models'][0]['readiness']['ready'] is False
