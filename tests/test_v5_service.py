"""V5 public service contracts, with real detector and only provider HTTP doubled."""
import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from ai.ai import AIService
from backend.config import Settings
from backend.main import create_app


ENGLISH = (
    'The people who work with us have been reading this report and discussing what it means. '
    'We have some questions about the results because they are different from what we expected. '
    'Each person should be able to explain their view before we decide which steps to take. '
    'When we have read the evidence we can discuss how this work will affect our team. '
    'There are more details in the report that we would like to understand before the meeting. '
    'These questions are part of our work and we will return to them with the team.'
)


def forbidden_provider(_request):
    raise AssertionError('Detector must never send text to a generative provider')


def test_auto_language_and_detector_contract_are_available_through_authenticated_api():
    with TestClient(create_app(Settings(), httpx.MockTransport(forbidden_provider))) as client:
        response = client.post('/api/detect', json={'text': ENGLISH, 'language': 'auto'})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['languageAssessment']['detected'] == 'en'
    assert data['languageAssessment']['status'] == 'supported'
    assert data['styleIndex'] is not None
    detector = data['detector']
    assert detector['documentProbability'] is None
    assert detector['aiMarkedPercent'] is None
    assert detector['documentValidated'] is False
    assert detector['calibrationValidated'] is False
    assert detector['segmentValidated'] is False
    assert detector['segmentCalibrationValidated'] is False
    assert detector['category'] in ('uncertain', 'insufficient')
    assert all(segment['category'] == 'unassessed' for segment in data['segments'])


def test_auto_is_the_default_for_both_python_and_http_detection():
    direct = asyncio.run(AIService(Settings()).detect(ENGLISH))
    with TestClient(create_app(Settings())) as client:
        data = client.post('/api/detect', json={'text': ENGLISH}).json()
    for result in (direct, data):
        assert result['languageAssessment']['detected'] == 'en'
        assert result['languageAssessment']['status'] == 'supported'
        assert result['languageAssessment']['requested'] == 'auto'


def test_manual_language_mismatch_remains_visible_and_cannot_produce_confidence():
    with TestClient(create_app(Settings())) as client:
        data = client.post('/api/detect', json={'text': ENGLISH, 'language': 'sv'}).json()
    assert data['languageAssessment']['status'] == 'mismatch'
    assert data['styleIndex'] is None
    assert data['detector']['documentProbability'] is None
    assert data['detector']['aiMarkedPercent'] is None


def test_detector_segments_reconstruct_utf16_slices_at_the_http_boundary():
    source = '😀 Åsa läser ”The report”.\n' + ENGLISH
    with TestClient(create_app(Settings())) as client:
        response = client.post('/api/detect', json={'text': source, 'language': 'auto'})
    assert response.status_code == 200
    data = response.json()
    encoded = source.encode('utf-16-le')
    previous = 0
    assert data['segments']
    for segment in data['segments']:
        assert segment['start'] >= previous
        assert segment['end'] > segment['start']
        assert encoded[2 * segment['start']:2 * segment['end']].decode('utf-16-le') == segment['text']
        previous = segment['end']


@pytest.mark.parametrize('extra', [
    {'model_path': '/tmp/untrusted-model.json'},
    {'documentValidated': True},
    {'model': 'expensive-client-selected-model'},
])
def test_detector_cannot_accept_client_selected_models_or_validation_claims(extra):
    with TestClient(create_app(Settings())) as client:
        response = client.post('/api/detect', json={'text': ENGLISH, **extra})
    assert response.status_code == 422
    assert 'untrusted-model' not in response.text


def test_detector_remote_authentication_runs_before_json_parsing():
    with TestClient(create_app(Settings()), client=('203.0.113.21', 9876)) as client:
        response = client.post('/api/detect', content='PRIVATE malformed text',
                               headers={'Content-Type': 'application/json'})
    assert response.status_code == 403
    assert 'PRIVATE' not in response.text


def test_humanizer_keeps_actual_usage_when_restoring_protected_original_text():
    class MeteredText(str):
        usage = {
            'provider': 'ollama', 'model': 'fixture-local',
            'recorded_at': '2026-11-07T12:00:00Z', 'latency_ms': 14.5,
            'input_tokens': 11, 'output_tokens': 7, 'total_tokens': 18,
            'cached_input_tokens': None,
            'cost': {'currency': 'USD', 'estimated_amount': None,
                     'pricing_version': None, 'status': 'not_applicable'},
        }

    async def generation(_payload, protected, _timeout, _cap=None):
        return MeteredText(protected)

    source = '  Åsa Öberg betalade 125 kr. Originalet är sparat.\n'
    result = asyncio.run(AIService(Settings(model='fixture-local'), generate_fn=generation).humanize(source))
    assert result['text'] == source
    assert result['unchanged'] is True
    assert result['usage']['input_tokens'] == 11
    assert result['usage']['output_tokens'] == 7
    assert result['usage']['total_tokens'] == 18
    assert result['usage']['cost']['estimated_amount'] is None
    assert source not in json.dumps(result['usage'])


def test_legacy_injected_provider_without_usage_is_explicitly_unavailable():
    async def generation(_payload, protected, _timeout, _cap=None):
        return protected

    result = asyncio.run(AIService(Settings(), generate_fn=generation).humanize('Det här är originalet.'))
    assert result['usage'] is None
    assert result['review_required'] is True
