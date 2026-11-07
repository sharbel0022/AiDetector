"""Provider usage and local budget accounting; no live API credentials needed."""
import asyncio
import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from ai.contracts import RewriteRequest
from ai.providers import generate
from backend.config import Settings
from backend.limits import SharedLimits
from backend.main import create_app
from ai.usage import load_price_table, provider_usage


def response_for(provider, raw='{"text":"A careful revised sentence."}', **extra):
    if provider == 'openai':
        result = {'status': 'completed', 'model': 'gpt-4.1-mini-2025-04-14',
                  'usage': {'input_tokens': 100, 'output_tokens': 30, 'total_tokens': 130,
                            'input_tokens_details': {'cached_tokens': 40}},
                  'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': raw}]}]}
    elif provider == 'compatible':
        result = {'model': 'gpt-4.1-mini',
                  'usage': {'prompt_tokens': 100, 'completion_tokens': 30, 'total_tokens': 130,
                            'prompt_tokens_details': {'cached_tokens': 40}},
                  'choices': [{'finish_reason': 'stop', 'message': {'content': raw}}]}
    else:
        result = {'model': 'local:latest', 'prompt_eval_count': 100, 'eval_count': 30,
                  'done': True, 'done_reason': 'stop', 'message': {'content': raw}}
    result.update(extra)
    return result


def run_provider(provider, data):
    settings = Settings(provider=provider, model='gpt-4.1-mini', openai_key='test-only',
                        compatible_url='https://provider.example/v1', compatible_key='test-only')
    def handler(request):
        if request.method == 'GET':
            return httpx.Response(200, json={'id': settings.model})
        return httpx.Response(200, json=data)
    return asyncio.run(generate(settings, RewriteRequest(text='A careful source sentence.', language='en'),
                                'A careful source sentence.', httpx.MockTransport(handler)))


@pytest.mark.parametrize('provider', ['openai', 'compatible', 'ollama'])
def test_generation_remains_a_string_and_keeps_actual_provider_counters(provider):
    result = run_provider(provider, response_for(provider))
    assert isinstance(result, str)
    assert result == 'A careful revised sentence.'
    usage = result.usage
    assert usage['provider'] == provider
    assert usage['model'] == response_for(provider)['model']
    assert (usage['input_tokens'], usage['output_tokens'], usage['total_tokens']) == (100, 30, 130)
    assert usage['latency_ms'] >= 0
    assert usage['recorded_at'].endswith('Z')
    assert usage['cached_input_tokens'] == (None if provider == 'ollama' else 40)
    if provider == 'openai':
        assert usage['cost']['estimated_amount'] == pytest.approx(.000076)
        assert usage['cost']['pricing_version']
        assert usage['cost']['status'] == 'estimated'
    else:
        assert usage['cost']['estimated_amount'] is None
        assert usage['cost']['status'] == ('not_applicable' if provider == 'ollama' else 'unknown')


@pytest.mark.parametrize('provider', ['openai', 'compatible', 'ollama'])
def test_usage_is_preserved_when_billed_response_has_invalid_text(provider):
    with pytest.raises(HTTPException) as caught:
        run_provider(provider, response_for(provider, raw='not valid json'))
    assert caught.value.status_code == 502
    assert caught.value.usage['total_tokens'] == 130


@pytest.mark.parametrize('usage', [None, {}, {'input_tokens': True, 'output_tokens': -1, 'total_tokens': '10'},
                                  {'input_tokens': 100, 'output_tokens': 30, 'total_tokens': 130}])
def test_missing_or_invalid_usage_never_fabricates_cached_tokens_or_cost(usage):
    result = run_provider('openai', response_for('openai', usage=usage))
    assert result.usage['cached_input_tokens'] is None
    assert result.usage['cost']['estimated_amount'] is None
    if not usage or 'input_tokens' not in usage or usage['input_tokens'] is True:
        assert result.usage['input_tokens'] is None
        assert result.usage['total_tokens'] is None


def test_unknown_response_model_has_unknown_price():
    result = run_provider('openai', response_for('openai', model='unknown-future-model'))
    assert result.usage['model'] == 'unknown-future-model'
    assert result.usage['cost']['estimated_amount'] is None


def test_currency_budget_fails_closed_for_unpriced_model(tmp_path):
    calls = []
    settings = Settings(provider='openai', model='unpriced', openai_key='test-only',
                        state_db=str(tmp_path / 'state.db'), daily_cost_budget_usd=.1)
    with TestClient(create_app(settings, transport=httpx.MockTransport(lambda r: calls.append(r)))) as client:
        result = client.post('/api/rewrite', json={'text': 'A careful source sentence.'})
    assert result.status_code == 503
    assert calls == []


def test_shared_ledger_is_principal_scoped_text_free_and_retains_unknown_reservations(tmp_path):
    path = str(tmp_path / 'state.db')
    limits = SharedLimits(path)
    settings = Settings(state_db=path)
    lease = limits.reserve('alice', 500, settings, 10)
    limits.complete(lease, None, 'failed')
    usage = SharedLimits(path).summary('alice', settings)
    assert usage['requests'] == 1
    assert usage['total_tokens'] is None
    assert usage['reservations']['tokens'] == 500
    assert usage['reservations']['pending_requests'] == 0
    assert usage['reservations']['unreported_requests'] == 1
    assert SharedLimits(path).summary('bob', settings)['requests'] == 0
    with sqlite3.connect(path) as db:
        columns = [row[1] for row in db.execute('PRAGMA table_info(usage_events)')]
        assert not {'text', 'prompt', 'output', 'token', 'credential'}.intersection(columns)


def test_usage_endpoint_requires_auth_and_accounts_for_rejected_rewrites(tmp_path):
    def handler(request):
        if request.method == 'GET':
            return httpx.Response(200, json={'id': 'gpt-4.1-mini'})
        # A syntactically valid response that fails post-generation meaning checks.
        return httpx.Response(200, json=response_for('openai', raw='{"text":"The team approved the draft."}'))
    settings = Settings(provider='openai', model='gpt-4.1-mini', openai_key='test-only',
                        auth_mode='multiuser', state_db=str(tmp_path / 'state.db'),
                        user_token_hashes={u: hashlib.sha256(k.encode()).hexdigest() for u, k in [('alice', 'a'), ('bob', 'b')]})
    with TestClient(create_app(settings, transport=httpx.MockTransport(handler))) as client:
        assert client.get('/api/usage').status_code == 401
        assert client.post('/api/rewrite', headers={'Authorization': 'Bearer a'},
                           json={'text': 'The team did not approve the draft.', 'language': 'en'}).status_code == 502
        usage = client.get('/api/usage', headers={'Authorization': 'Bearer a'}).json()
        assert usage['requests'] == 1
        assert usage['total_tokens'] == 130
        assert usage['estimated_cost']['amount'] == pytest.approx(.000076)
        assert client.get('/api/usage', headers={'Authorization': 'Bearer b'}).json()['requests'] == 0


def test_atomic_currency_and_token_reservations_across_connections(tmp_path):
    settings = Settings(state_db=str(tmp_path / 'state.db'), max_concurrent=100,
                        daily_token_budget=10000, global_daily_token_budget=10000,
                        daily_cost_budget_usd=.01, global_daily_cost_budget_usd=.01)
    stores = [SharedLimits(settings.state_db) for _ in range(8)]
    def reserve(store):
        try:
            return store.reserve('alice', 100, settings, 10, cost_nanos=4_000_000)
        except HTTPException as exc:
            return exc.status_code
    with ThreadPoolExecutor(max_workers=8) as pool:
        result = list(pool.map(reserve, stores))
    assert sum(isinstance(item, str) for item in result) == 2
    assert result.count(429) == 6


def test_reconciliation_is_idempotent_and_unknown_calls_cannot_refund_budget(tmp_path):
    settings = Settings(state_db=str(tmp_path / 'state.db'))
    store = SharedLimits(settings.state_db)
    lease = store.reserve('alice', 500, settings, 10, cost_nanos=1_000_000)
    usage = provider_usage('openai', response_for('openai'), 12)
    store.complete(lease, usage, 'provider_success')
    store.complete(lease, None, 'failed')
    result = store.summary('alice', settings)
    assert result['budget']['charged_tokens'] == 130
    assert result['budget']['charged_cost_usd'] == pytest.approx(.000076)
    assert result['reservations']['tokens'] == 0
    unknown = store.reserve('alice', 500, settings, 10, cost_nanos=1_000_000)
    store.complete(unknown, None, 'cancelled')
    result = store.summary('alice', settings)
    assert result['budget']['charged_tokens'] == 630
    assert result['budget']['charged_cost_usd'] == pytest.approx(.001076)
    assert result['reservations']['tokens'] == 500
    assert result['estimated_cost']['unknown_requests'] == 1


def test_expired_worker_lease_does_not_refund_unreported_work(tmp_path, monkeypatch):
    import backend.limits as module
    now = 1_700_000_000
    monkeypatch.setattr(module.time, 'time', lambda: now)
    settings = Settings(state_db=str(tmp_path / 'state.db'), daily_token_budget=500)
    store = SharedLimits(settings.state_db)
    store.reserve('alice', 500, settings, 10)
    now += 30
    resumed = SharedLimits(settings.state_db)
    result = resumed.summary('alice', settings)
    assert result['reservations']['tokens'] == 500
    assert result['reservations']['pending_requests'] == 0
    assert result['reservations']['unreported_requests'] == 1
    with pytest.raises(HTTPException) as error:
        resumed.reserve('alice', 1, settings, 10)
    assert error.value.status_code == 429


def test_summary_enforces_retention_without_a_new_generation(tmp_path, monkeypatch):
    import backend.limits as module
    now = 1_700_000_000
    monkeypatch.setattr(module.time, 'time', lambda: now)
    settings = Settings(state_db=str(tmp_path / 'state.db'))
    store = SharedLimits(settings.state_db)
    store.reserve('alice', 500, settings, 10)
    now += 32 * 86400
    assert store.summary('alice', settings)['requests'] == 0
    assert store.db.execute('SELECT count(*) FROM usage_events').fetchone()[0] == 0


def test_derived_total_and_nonfinite_metadata_are_not_trusted(tmp_path):
    usage = provider_usage('ollama', {'prompt_eval_count': 2**53 - 1, 'eval_count': 2}, float('inf'))
    assert usage['total_tokens'] is None
    assert usage['latency_ms'] is None
    settings = Settings(state_db=str(tmp_path / 'state.db'))
    store = SharedLimits(settings.state_db)
    for amount in (float('inf'), float('nan'), -1, 1e100):
        lease = store.reserve('alice', 500, settings, 10, cost_nanos=1_000_000)
        store.complete(lease, {'latency_ms': float('nan'), 'cost': {'currency': 'USD', 'status': 'estimated', 'estimated_amount': amount, 'pricing_version': '2026-11-07.1'}}, 'failed')
    result = store.summary('alice', settings)
    assert result['estimated_cost']['amount'] is None
    assert result['estimated_cost']['unknown_requests'] == 4
    assert result['budget']['charged_tokens'] == 2000
    assert result['budget']['charged_cost_usd'] == .004


@pytest.mark.parametrize('mutation', ['negative', 'nan', 'wrong_currency', 'unofficial_source', 'duplicate'])
def test_price_table_rejects_invalid_or_unattributed_rates(tmp_path, mutation):
    from ai.usage import PRICE_FILE
    data = json.loads(PRICE_FILE.read_text())
    if mutation == 'negative':
        data['models'][0]['input'] = '-1'
    elif mutation == 'nan':
        data['models'][0]['input'] = 'NaN'
    elif mutation == 'wrong_currency':
        data['currency'] = 'SEK'
    elif mutation == 'unofficial_source':
        data['models'][0]['source'] = 'https://unverified.example/pricing'
    else:
        data['models'].append(data['models'][0])
    path = tmp_path / 'prices.json'
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        load_price_table(path)


def test_timeouts_keep_durable_budget_and_log_no_text(tmp_path):
    source = 'Private source text must never be in the usage database.'
    async def handler(request):
        await asyncio.sleep(1)
        return httpx.Response(200, json=response_for('ollama'))
    settings = Settings(state_db=str(tmp_path / 'state.db'), request_timeout=.01)
    with TestClient(create_app(settings, transport=httpx.MockTransport(handler))) as client:
        assert client.post('/api/rewrite', json={'text': source}).status_code == 504
        usage = client.get('/api/usage').json()
    assert usage['requests'] == 1
    assert usage['total_tokens'] is None
    assert usage['reservations']['tokens'] > 0
    assert usage['reservations']['pending_requests'] == 0
    with sqlite3.connect(settings.state_db) as db:
        assert db.execute('SELECT status FROM usage_events').fetchone()[0] == 'timeout'
        assert source not in '\n'.join(db.iterdump())


def test_currency_caps_cannot_treat_prior_unpriced_usage_as_zero(tmp_path):
    settings = Settings(provider='openai', model='unpriced', state_db=str(tmp_path / 'state.db'))
    store = SharedLimits(settings.state_db)
    lease = store.reserve('alice', 100, settings, 10)
    store.complete(lease, None, 'failed')
    settings.daily_cost_budget_usd = .1
    with pytest.raises(HTTPException) as error:
        store.reserve('alice', 100, settings, 10, cost_nanos=1_000_000)
    assert error.value.status_code == 503


def test_v4_budget_migration_preserves_unknown_allowance_and_blocks_new_currency_caps(tmp_path):
    settings = Settings(state_db=str(tmp_path / 'state.db'), daily_cost_budget_usd=.1)
    store = SharedLimits(settings.state_db)
    import time
    day = int(time.time() // 86400)
    principal = hashlib.sha256(b'alice').hexdigest()
    for owner in (principal, 'global'):
        store.db.execute('INSERT INTO budgets VALUES (?, ?, ?)', (owner, day, 500))
    summary = store.summary('alice', settings)
    assert summary['total_tokens'] is None
    assert summary['estimated_cost']['amount'] is None
    assert summary['reservations']['tokens'] == 500
    assert summary['reservations']['legacy_reserved_tokens'] == 500
    with pytest.raises(HTTPException) as error:
        store.reserve('alice', 100, settings, 10, cost_nanos=1_000_000)
    assert error.value.status_code == 503


@pytest.mark.parametrize('path', ['', ':memory:', 'relative.sqlite'])
@pytest.mark.parametrize('cap', ['daily_cost_budget_usd', 'global_daily_cost_budget_usd'])
def test_currency_caps_require_persistent_absolute_shared_storage(path, cap, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match='absolute persistent TEXTLAB_STATE_DB'):
        create_app(Settings(state_db=path, **{cap: .1}))
