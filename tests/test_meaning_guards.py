"""Fail closed on a bounded set of meaning changes; do not claim entailment."""
import json
import sqlite3

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.main import PreservationError, Settings, create_app, protect_text, restore_text


@pytest.mark.parametrize('quantity', ['12 mg', '4 °C', '8 kWh', '250 kr', '3.5 kg', '15 %'])
def test_recognized_quantity_keeps_number_and_unit_in_one_anchor(quantity):
    text = f'The recorded amount was {quantity} during the trial.'
    protected, mapping = protect_text(text)
    assert quantity in mapping.values()
    assert restore_text(protected, mapping, text) == text


@pytest.mark.parametrize(('source', 'candidate'), [
    ('The sample weighed 12 mg.', 'The sample weighed 12 g.'),
    ('The sample contained 12 items.', 'The sample contained 12 mg items.'),
    ('The sample weighed 12 mg.', 'The sample weighed 12 mg/kg.'),
])
def test_unit_changes_and_added_units_are_rejected(source, candidate):
    # No anchors here: exercise the post-restore check independently of masking.
    with pytest.raises(PreservationError):
        restore_text(candidate, {}, source)


@pytest.mark.parametrize(('source', 'candidate'), [
    ('The treatment may reduce pain.', 'The treatment reduces pain.'),
    ('The team did not approve the draft.', 'The team approved the draft.'),
    ('The device reduced use.', 'The device did not reduce use.'),
    ('Behandlingen kan möjligen minska smärtan.', 'Behandlingen minskar smärtan.'),
    ('Teamet godkände inte utkastet.', 'Teamet godkände utkastet.'),
    ('The sample must stay below the limit.', 'The sample may stay below the limit.'),
    ('The team tested it, and use fell.', 'The team tested it, resulting in lower use.'),
])
def test_obvious_polarity_uncertainty_and_obligation_changes_are_rejected(source, candidate):
    with pytest.raises(PreservationError):
        restore_text(candidate, {}, source)


@pytest.mark.parametrize(('source', 'candidate'), [
    ('The treatment may reduce pain.', 'The treatment might ease pain.'),
    ('The team did not approve it.', "The team didn't approve it."),
    ('The device reduced energy use.', 'The device cut energy consumption.'),
    ('Teamet godkände inte utkastet.', 'Teamet godkände ej utkastet.'),
    ('The sample must stay below the limit.', 'The sample is required to stay below the limit.'),
    ('The report states "It may not work".', 'The report says "It may not work".'),
    ('The test caused the failure.', 'The test led to the failure.'),
])
def test_safe_local_paraphrases_are_not_blocked_by_marker_checks(source, candidate):
    assert restore_text(candidate, {}, source) == candidate


def test_provider_keeps_names_dates_quantities_and_quotes_opaque():
    def handler(request):
        data = json.loads(request.content)
        user = json.loads(data['messages'][-1]['content'])
        assert 'Alice Smith' not in user['text']
        assert '2 May 2025' not in user['text']
        assert '12 mg' not in user['text']
        assert '"Keep exact"' not in user['text']
        return httpx.Response(200, json={'done': True, 'done_reason': 'stop', 'message': {
            'content': json.dumps({'text': user['text'].replace('For clarity, ', '')})}})
    settings = Settings()
    with TestClient(create_app(settings, transport=httpx.MockTransport(handler))) as client:
        response = client.post('/api/rewrite', json={'text': 'For clarity, Alice Smith recorded 12 mg on 2 May 2025 and said "Keep exact".', 'language': 'en'})
        assert response.status_code == 200, response.text
        assert response.json()['text'] == 'Alice Smith recorded 12 mg on 2 May 2025 and said "Keep exact".'
        assert response.json()['preservation']['semantic_equivalence_verified'] is False


def test_changed_negation_is_not_returned_as_success():
    def handler(request):
        text = json.loads(json.loads(request.content)['messages'][-1]['content'])['text']
        return httpx.Response(200, json={'done': True, 'done_reason': 'stop', 'message': {
            'content': json.dumps({'text': text.replace('did not approve', 'approved')})}})
    with TestClient(create_app(Settings(), transport=httpx.MockTransport(handler))) as client:
        response = client.post('/api/rewrite', json={'text': 'The team did not approve the draft.', 'language': 'en'})
        assert response.status_code == 502
        assert 'approved the draft' not in response.text


@pytest.mark.parametrize('provider', ['ollama', 'openai', 'compatible'])
def test_quota_covers_actual_large_quoted_source_body_and_output_cap(tmp_path, provider):
    """Removing nested JSON escaping from quota accounting must fail."""
    sent = []
    def handler(request):
        sent.append(request)
        body = json.loads(request.content)
        text = json.loads(body.get('input') or body['messages'][-1]['content'])['text']
        raw = json.dumps({'text': text})
        if provider == 'openai':
            result = {'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': raw}]}]}
        elif provider == 'compatible':
            result = {'choices': [{'finish_reason': 'stop', 'message': {'content': raw}}]}
        else:
            result = {'done': True, 'done_reason': 'stop', 'message': {'content': raw}}
        return httpx.Response(200, json=result)
    database = tmp_path / f'{provider}.sqlite'
    settings = Settings(provider=provider, model='configured-model', openai_key='secret',
                        compatible_url='https://model.example/v1', compatible_key='secret',
                        state_db=str(database), daily_token_budget=1000000, global_daily_token_budget=1000000)
    source = '\\' * 5500 + ' '.join('"' + str(i) + 'å' + '\\' * 20 + '"' for i in range(40))
    with TestClient(create_app(settings, transport=httpx.MockTransport(handler))) as client:
        response = client.post('/api/rewrite', json={'text': source, 'language': 'en'})
        assert response.status_code == 200, response.text
    with sqlite3.connect(database) as connection:
        reserved = connection.execute('SELECT MAX(used) FROM budgets').fetchone()[0]
    assert reserved >= len(sent[0].content) + settings.max_output_tokens


@pytest.mark.parametrize('failure', ['missing', 'duplicate_value', 'duplicate_marker', 'unknown_marker', 'changed_unit', 'changed_name', 'invented_number'])
def test_dictionary_expansion_rejects_missing_duplicate_unknown_and_changed_values(failure):
    source = 'Alice Smith recorded 12 mg on 2 May 2025. Alice Smith saved [Smith, 2025].'
    protected, mapping = protect_text(source)
    key = next(iter(mapping))
    candidates = {
        'missing': source.replace('12 mg', ''),
        'duplicate_value': source + ' Alice Smith',
        'duplicate_marker': protected.replace(key, key + ' ' + key),
        'unknown_marker': source + ' __TL_0123456789abcdef_999__',
        'changed_unit': source.replace('12 mg', '12 g'),
        'changed_name': source.replace('Alice Smith', 'Alicia Smith', 1),
        'invented_number': source + ' 17',
    }
    with pytest.raises(PreservationError):
        restore_text(candidates[failure], mapping, source)


def test_exact_expansion_does_not_use_substrings_as_missing_value_recovery():
    source = 'Ann met Anna. The result was 12 mg and the other result was 12 mg/kg.'
    _, mapping = protect_text(source)
    with pytest.raises(PreservationError):
        restore_text('Anna met Anna. The result was 12 mg/kg and the other result was 12 mg/kg.', mapping, source)


@pytest.mark.parametrize(('source', 'candidate'), [
    ('The change was 12 mg.', 'The change was -12 mg.'),
    ('The change was -12 mg.', 'The change was 12 mg.'),
    ('The change was 12 mg.', 'The change was +12 mg.'),
    ('The change was +12 mg.', 'The change was 12 mg.'),
    ('The change was 12 mg.', 'The change was −12 mg.'),
    ('The change was −12 mg.', 'The change was 12 mg.'),
    ('The change was - 12 mg.', 'The change was 12 mg.'),
    ('The counts were -12 and 15.', 'The counts were 12 and -15.'),
    ('The counts were +12 and 15.', 'The counts were 12 and +15.'),
    ('The changes were -12 mg and 15 mg.', 'The changes were 12 mg and -15 mg.'),
    ('The changes were -12 mg and 12 g.', 'The changes were 12 mg and -12 g.'),
    ('The changes were +12 mg and 12 g.', 'The changes were 12 mg and +12 g.'),
    ('The range was 12–15 mg.', 'The values were 12 and -15 mg.'),
    ('The amount was 12 mg.', 'The amount was 12 mg/dl.'),
    ('The amount was 12 mg.', 'The amount was 12 mg / kg.'),
    ('The amount was 12 mg.', 'The amount was 12 mg^2.'),
    ('The amount was 12 mg.', 'The amount was 12 mg·kg.'),
])
def test_numeric_signs_and_unit_suffix_changes_are_rejected(source, candidate):
    with pytest.raises(PreservationError):
        restore_text(candidate, {}, source)


@pytest.mark.parametrize('source', [
    'The change was -12 mg.', 'The change was −12 mg.', 'The change was +12 mg.',
    'The range was 12–15 mg.', 'The range was 12-15 mg.', 'The range was 12 – 15 mg.',
    'The range was -12–-5 mg.', 'The amount was 12 mg/dl.', 'The amount was 12 mg / kg.',
    'The amount was 12 mg^2.', 'The amount was 12 mg·kg.',
])
def test_unchanged_signed_numbers_ranges_and_compound_units_are_preserved(source):
    assert restore_text(source, {}, source) == source
