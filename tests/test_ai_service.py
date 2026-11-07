"""V4 application boundaries: real orchestration, only model HTTP is replaced."""
import asyncio
import importlib.util
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.main import Settings, create_app


TEXT = 'Åsa Öberg betalade 125 kr den 7 november 2026. Källan [12] säger ”klart”.'


def echo(request):
    body = json.loads(request.content)
    text = json.loads(body['messages'][-1]['content'])['text']
    return httpx.Response(200, json={
        'done': True, 'done_reason': 'stop', 'message': {'content': json.dumps({'text': text})},
    })


def test_unchanged_text_is_preserved_exactly_and_explained():
    source = '  ' + TEXT + '\n'
    with TestClient(create_app(Settings(), httpx.MockTransport(echo))) as client:
        response = client.post('/api/rewrite', json={'text': source})
    assert response.status_code == 200
    data = response.json()
    assert data['text'] == source
    assert data['unchanged'] is True
    assert 'original' in data['explanation'].lower()
    assert data['review_required'] is True
    assert data['preservation']['semantic_equivalence_verified'] is False
    assert data['diff'] == [{'kind': 'equal', 'text': source}]


def test_central_service_supports_the_same_safe_humanizer_contract():
    assert importlib.util.find_spec('ai') is not None, 'Central AI package must be importable'
    from ai.ai import AIService
    service = AIService(Settings(), transport=httpx.MockTransport(echo))
    result = asyncio.run(service.humanize(TEXT, language='sv', tone='academic'))
    assert result['text'] == TEXT
    assert result['unchanged'] is True
    assert result['preservation']['exact_values_checked'] is True
    assert result['preservation']['semantic_equivalence_verified'] is False


def test_detector_api_is_offline_and_short_text_abstains():
    calls = []
    def forbidden(request):
        calls.append(request)
        raise AssertionError('Style analysis must not send source to a model')
    with TestClient(create_app(Settings(), httpx.MockTransport(forbidden))) as client:
        response = client.post('/api/detect', json={'text': 'En kort svensk text.', 'language': 'sv'})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['styleIndex'] is None
    assert data['authorship'] == 'undetermined'
    assert data['uncertainty']['probabilityAvailable'] is False
    assert 'too_short' in data['abstentionReasons']
    assert calls == []


def test_detector_requires_remote_auth_before_consuming_input():
    with TestClient(create_app(Settings()), client=('203.0.113.15', 9000)) as client:
        response = client.post('/api/detect', content='private malformed JSON')
    assert response.status_code == 403
    assert 'private malformed' not in response.text


@pytest.mark.parametrize('path,text', [
    ('/api/detect', '😀' * 6001),
    ('/api/rewrite', '😀' * 4001),
    ('/api/detect', 'invalid\ud800 source'),
    ('/api/rewrite', 'invalid\ud800 source'),
])
def test_unicode_limits_and_invalid_surrogates_are_client_errors(path, text):
    calls = []
    def forbidden(request):
        calls.append(request)
        raise AssertionError('Invalid input must be rejected before provider access')
    with TestClient(create_app(Settings(), httpx.MockTransport(forbidden))) as client:
        response = client.post(path, content=json.dumps({'text': text, 'language': 'sv'}),
                               headers={'Content-Type': 'application/json'})
    assert response.status_code == 422
    assert calls == []


def test_lower_server_input_limit_is_reported_and_enforced_before_model_call():
    settings = Settings()
    settings.max_input_chars = 20
    calls = []
    def handler(request):
        calls.append(request)
        return echo(request)
    with TestClient(create_app(settings, httpx.MockTransport(handler))) as client:
        assert client.get('/api/health').json()['max_input_chars'] == 20
        response = client.post('/api/rewrite', json={'text': 'x' * 21})
    assert response.status_code == 422
    assert calls == []


@pytest.mark.parametrize('limit', [0, 9, 8001, True])
def test_invalid_configured_input_limit_fails_closed(limit):
    settings = Settings()
    settings.max_input_chars = limit
    with pytest.raises(ValueError):
        create_app(settings)


def test_provider_status_explains_missing_openai_configuration_without_http():
    calls = []
    def forbidden(request):
        calls.append(request)
        raise AssertionError('Missing config must not make a provider request')
    with TestClient(create_app(Settings(provider='openai', model='', openai_key=''), httpx.MockTransport(forbidden))) as client:
        response = client.get('/api/provider-status')
    assert response.status_code == 200
    data = response.json()
    assert data['ready'] is False and data['verified'] is False
    assert 'OPENAI_API_KEY' in data['message'] and 'OPENAI_MODEL' in data['message']
    assert calls == []


@pytest.mark.parametrize('quote,repetitions', [('calm words ' * 200, 1150), ('😀 ' * 1000, 1050)])
def test_restored_protected_text_cannot_exceed_browser_output_limit(quote, repetitions):
    from ai.contracts import ModelText, utf16_length
    source = 'Here is a quotation: "' + quote + '".'
    calls = []
    def oversized_after_restore(request):
        body = json.loads(request.content)
        protected = json.loads(body['messages'][-1]['content'])['text']
        output = protected + ' gentle prose' * repetitions
        # The provider response itself is valid. Restoring the long quote is
        # what crosses the UTF-16 contract shared with the browser.
        assert ModelText(text=output).text == output
        assert utf16_length(source + ' gentle prose' * repetitions) > 16000
        calls.append(request)
        return httpx.Response(200, json={'done': True, 'message': {'content': json.dumps({'text': output})}})
    with TestClient(create_app(Settings(), httpx.MockTransport(oversized_after_restore))) as client:
        response = client.post('/api/rewrite', json={'text': source, 'language': 'en', 'tone': 'detailed'})
    assert len(calls) == 1
    assert response.status_code == 502
    assert source not in response.text


@pytest.mark.parametrize('quote', ['calm words ' * 200, '😀 ' * 1000])
def test_restored_output_at_exact_utf16_limit_remains_valid(quote):
    from ai.contracts import utf16_length
    source = 'Here is a quotation: "' + quote + '".'
    suffix = ' ' + 'x' * (16000 - utf16_length(source) - 1)
    def exactly_at_limit(request):
        body = json.loads(request.content)
        protected = json.loads(body['messages'][-1]['content'])['text']
        return httpx.Response(200, json={'done': True, 'message': {'content': json.dumps({'text': protected + suffix})}})
    with TestClient(create_app(Settings(), httpx.MockTransport(exactly_at_limit))) as client:
        response = client.post('/api/rewrite', json={'text': source, 'language': 'en', 'tone': 'detailed'})
    assert response.status_code == 200, response.text
    assert response.json()['text'] == source + suffix
    assert utf16_length(response.json()['text']) == 16000
