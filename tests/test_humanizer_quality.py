"""Bounded challenge checks must catch known wrong claims, not grade prose style."""
from tools.humanizer_quality import assess_case, load_cases, mode_summary
import json
import sys

import pytest
import tools.humanizer_quality as quality


def development_en():
    return next(case for case in load_cases() if case['id'] == 'development-en')


def test_challenge_oracles_accept_source_and_safe_local_edit():
    case = development_en()
    assert assess_case(case, case['text'])['all_bounded_checks_pass'] is True
    output = case['text'].replace('For the purpose of keeping a clear record, ', 'To keep a clear record, ')
    assert assess_case(case, output)['all_bounded_checks_pass'] is True


def test_challenge_oracle_rejects_actor_date_swap_despite_exact_values():
    case = development_en()
    output = case['text'].replace('3 May 2025', 'TEMP').replace('7 May 2025', '3 May 2025').replace('TEMP', '7 May 2025')
    result = assess_case(case, output)
    assert result['exact_values_preserved'] is True
    assert result['all_bounded_checks_pass'] is False


def test_challenge_oracles_catch_negation_unit_hedge_and_causal_changes():
    case = development_en()
    for before, after in [('did not approve', 'approved'), ('may reduce', 'reduces'), ('12 mg', '12 g'), ('and energy use fell', 'so energy use fell')]:
        result = assess_case(case, case['text'].replace(before, after))
        assert result['all_bounded_checks_pass'] is False, (before, result)


def test_all_frozen_sources_pass_their_own_bounded_checks():
    cases = load_cases()
    assert {case['split'] for case in cases} == {'development', 'heldout'}
    assert {case['language'] for case in cases} == {'sv', 'en'}
    for case in cases:
        assert assess_case(case, case['text'])['all_bounded_checks_pass'] is True, case['id']


def test_unchanged_and_identical_modes_are_not_counted_as_mode_evidence():
    rows = [{'case_id': 'a', 'mode': mode, 'http_status': 200, 'output': 'Original.', 'input': 'Original.'}
            for mode in ['natural', 'simple', 'professional', 'academic', 'concise', 'detailed']]
    result = mode_summary(rows)
    assert result['unchanged_count'] == 6
    assert result['by_source']['a']['distinct_successful_outputs'] == 1
    assert result['by_source']['a']['all_six_modes_distinct'] is False


@pytest.mark.parametrize('quantity', ['112 mg', '-12 mg', '12 mg/kg', '12 mg/dl', '12 mg / kg', '12 mg·kg', '12 mg^2', '12 mgs'])
def test_assessor_rejects_quantity_prefixes_signs_and_compound_units(quantity):
    case = development_en()
    result = assess_case(case, case['text'].replace('12 mg', quantity))
    assert result['exact_values_preserved'] is False
    assert result['all_bounded_checks_pass'] is False


def test_existing_output_is_refused_before_any_provider_connection(tmp_path, monkeypatch):
    destination = tmp_path / 'existing.json'
    destination.write_text('{"immutable": true}', encoding='utf-8')
    def forbidden_connection(*args, **kwargs):
        raise AssertionError('Provider connection occurred before existing-output refusal')
    monkeypatch.setattr(quality.httpx, 'Client', forbidden_connection)
    monkeypatch.setattr(sys, 'argv', ['humanizer_quality.py', '--label', 'duplicate', '--output', str(destination)])
    with pytest.raises(SystemExit) as raised:
        quality.main()
    assert raised.value.code == 2
    assert destination.read_text(encoding='utf-8') == '{"immutable": true}'


def test_reassessment_reads_recorded_outputs_without_overwriting_or_inference(tmp_path, monkeypatch):
    case = development_en()
    stored = {'tool_sha256': 'historical-tool', 'models': [{'model': 'recorded-model', 'rewrites': [{
        'case_id': case['id'], 'split': case['split'], 'language': 'en', 'mode': 'natural',
        'http_status': 200, 'input': case['text'], 'output': case['text'].replace('12 mg', '12 mg/kg'),
        'assessment': {'all_bounded_checks_pass': True}}]}]}
    source = tmp_path / 'source.json'
    source.write_text(json.dumps(stored), encoding='utf-8')
    before = source.read_bytes()
    def forbidden_connection(*args, **kwargs):
        raise AssertionError('Reassessment made a provider connection')
    monkeypatch.setattr(quality.httpx, 'Client', forbidden_connection)
    result = quality.reassess_reports([source])
    assert result['rows'][0]['assessment']['all_bounded_checks_pass'] is False
    assert result['source_reports'][0]['tool_sha256'] == 'historical-tool'
    assert source.read_bytes() == before
