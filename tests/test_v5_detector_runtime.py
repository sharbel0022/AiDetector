"""Risk-focused checks for safe JSON inference, independent gates and source spans."""
import copy
import json
import math

import pytest

from ai.detector.runtime import analyze_v5
from ai.detector.linear import margin, validate_model
from ai.detector.evidence import gate_results
from ai.detector.linear import digest


TEXT = ('The people who work with us have been reading this report and discussing what it means. '
        'We have some questions about the results because they are different from what we expected. '
        'Each person should be able to explain their view before we decide which steps to take. '
        'When we have read the evidence we can discuss how this work will affect our team. '
        'There are more details in the report that we would like to understand before the meeting. '
        'These questions are part of our work and we will return to them with the team.')


def tiny_model():
    return {'kind': 'tfidf_logistic', 'blocks': [{'analyzer': 'char', 'ngramRange': [3, 5],
            'vocabulary': {'the': 0, 'and': 1}, 'idf': [1., 2.]}],
            'coefficients': [1., -1.], 'intercept': .1, 'normalization': 'block-l2-then-global-l2'}


def test_safe_json_linear_score_and_validation():
    model = tiny_model()
    validate_model(model)
    assert margin(model, 'the') == pytest.approx(1.1)
    assert margin(model, 'unseen') is None
    for key, value in [('coefficients', [math.nan, 1.]), ('intercept', True)]:
        damaged = {**model, key: value}
        with pytest.raises(ValueError):
            validate_model(damaged)
    damaged = copy.deepcopy(model)
    damaged['blocks'][0]['vocabulary']['and'] = 0
    with pytest.raises(ValueError):
        validate_model(damaged)


def test_missing_or_malformed_model_fails_closed(tmp_path):
    path = tmp_path / 'model.json'
    for content in (None, '{', '{"schemaVersion":"anything","documentValidated":true}', 'null'):
        if content is not None:
            path.write_text(content)
        result = analyze_v5(TEXT, model_path=path)
        assert result['styleIndex'] is not None
        assert result['detector']['status'] == 'model_unavailable'
        assert result['detector']['documentProbability'] is None
        assert result['detector']['aiMarkedPercent'] is None
        assert result['detector']['analyzedWords'] == 0
        assert result['detector']['excludedWords'] == result['wordCount']
        assert all(s['category'] == 'unassessed' for s in result['segments'])


def test_utf16_spans_word_partition_and_auto_language():
    source = '😀 Åsa läser ”The report”.\n' + TEXT + '\n42 O’Neill 𝕥est'
    result = analyze_v5(source)
    assert result['languageAssessment']['requested'] == 'auto'
    assert result['languageAssessment']['detected'] == 'en'
    assert result['languageAssessment']['status'] == 'supported'
    encoded = source.encode('utf-16-le')
    previous = 0
    for segment in result['segments']:
        assert isinstance(segment['id'], str)
        assert segment['start'] >= previous
        assert segment['end'] > segment['start']
        assert encoded[2*segment['start']:2*segment['end']].decode('utf-16-le') == segment['text']
        previous = segment['end']
    assert sum(s['wordCount'] for s in result['segments']) == result['wordCount']
    detector = result['detector']
    assert detector['analyzedWords'] + detector['excludedWords'] == result['wordCount']
    assert detector['flaggedWords'] == detector['flaggedSegments'] == 0


def test_mismatch_short_unsupported_and_limit_are_not_probabilities():
    for text, language in [(TEXT, 'sv'), ('one word', 'auto'), ('這是一個句子。' * 30, 'auto')]:
        result = analyze_v5(text, language)
        assert result['detector']['documentProbability'] is None
        assert result['detector']['aiMarkedPercent'] is None
    with pytest.raises(ValueError):
        analyze_v5('😀' * 6000 + 'a')
    with pytest.raises(ValueError):
        analyze_v5(TEXT, 'fr')


def test_validation_booleans_are_not_evidence():
    forged = {'documentValidated': True, 'calibrationValidated': True,
              'segmentValidated': True, 'segmentCalibrationValidated': True,
              'evidence': {'document': {'passed': True}, 'segment': {'passed': True}}}
    gates = gate_results(forged)
    assert not any(gates[name]['passed'] for name in ('document', 'calibration', 'segment', 'segmentCalibration'))


def test_checked_in_model_never_exposes_historical_margin_as_probability():
    result = analyze_v5(TEXT)
    detector = result['detector']
    assert detector['modelVersion'] is not None
    assert detector['status'] == 'unverified'
    assert detector['documentProbability'] is None
    assert detector['aiMarkedPercent'] is None
    assert detector['calibrationStatus'] == 'unavailable'
    assert not detector['documentValidated']
    assert not detector['calibrationValidated']
    assert not detector['segmentValidated']
    assert not detector['segmentCalibrationValidated']
    assert 'margin' not in json.dumps(result)


def evidence_fixture():
    """In-memory contract fixture only; this is never corpus/quality evidence."""
    from tools.train_v5 import report_slices
    model = tiny_model()
    thresholds = {'aiMin': .5, 'humanMax': -.5, 'selectionSplit': 'validation'}
    calibration = {'method': 'platt', 'slope': 4., 'intercept': 0.,
                   'fitting': {'split': 'calibration', 'classCounts': {'human': 100, 'ai': 100}}}
    rows = [{'source_id': f'{lang}-{label}-{index}', 'source_group_id': f'{lang}-{label}-{index}',
             'label': label, 'language': lang, 'genre': 'engineering-fixture', 'model': '(fixture)',
             'score': 2. if label == 'ai' else -2., 'words': 100}
            for lang in ('sv', 'en') for label in ('human', 'ai') for index in range(200)]
    artifact = {'documentModel': model, 'segmentModel': model,
                'documentThresholds': thresholds, 'segmentThresholds': thresholds,
                'documentCalibration': calibration, 'segmentCalibration': calibration, 'evidence': {}}
    for level in ('document', 'segment'):
        evidence = {**report_slices(rows, thresholds, calibration),
                    'evidenceUse': 'fresh-independent-holdout', 'testFrozenBeforeEvaluation': True,
                    'modelSha256': digest(model), 'thresholdsSha256': digest(thresholds),
                    'calibrationSha256': digest(calibration)}
        evidence['lineageAudit'] = {'passed': True, 'independentSplits': True, 'bindingSha256': digest(evidence)}
        artifact['evidence'][level] = evidence
    return artifact


@pytest.mark.parametrize(('field', 'value'), [
    ('coverage', 1.1), ('coverage', -1.),
    ('classCounts', {'human': 400.5, 'ai': 400}),
    ('familiesByLabel', {'human': 1000, 'ai': 400}),
    ('confusion', {'tp': 400, 'fp': -1, 'tn': 401, 'fn': 0}),
    ('recallAssessed', 1.1), ('falsePositiveRate', -.01),
])
def test_malformed_metric_ranges_counts_cannot_open_gate(field, value):
    artifact = evidence_fixture()
    assert gate_results(artifact)['document']['passed']
    artifact['evidence']['document']['metrics'][field] = value
    evidence = artifact['evidence']['document']
    evidence['lineageAudit']['bindingSha256'] = digest({k: v for k, v in evidence.items() if k != 'lineageAudit'})
    assert not gate_results(artifact)['document']['passed']


def test_invalid_intervals_and_calibration_errors_are_rejected():
    for changed in ({'falsePositiveRate': [-.2, -.1]}, {'recallAssessed': [1.1, 1.2]},
                    {'precision': [.99, .9]}):
        artifact = evidence_fixture()
        artifact['evidence']['segment']['metrics']['intervals95'].update(changed)
        assert not gate_results(artifact)['segment']['passed']
    for error in (-.1, math.inf, math.nan):
        artifact = evidence_fixture()
        artifact['evidence']['document']['metrics']['calibration']['ece10'] = error
        assert not gate_results(artifact)['calibration']['passed']


def test_missing_segment_model_does_not_disable_valid_document_evidence():
    artifact = evidence_fixture()
    artifact['segmentModel'] = artifact['segmentThresholds'] = artifact['segmentCalibration'] = None
    artifact['evidence'].pop('segment')
    gates = gate_results(artifact)
    assert gates['document']['passed'] and gates['calibration']['passed']
    assert not gates['segment']['passed'] and not gates['segmentCalibration']['passed']


def test_mixed_requires_validated_segments_and_uses_word_weighted_share(monkeypatch):
    from ai.detector import runtime
    artifact = evidence_fixture()
    artifact['modelVersion'] = 'test-only-not-quality-evidence'
    artifact['segmentCalibration'] = None
    gates = gate_results(artifact)
    assert gates['document']['passed'] and gates['calibration']['passed']
    assert gates['segment']['passed'] and not gates['segmentCalibration']['passed']
    monkeypatch.setattr(runtime, 'load_artifact', lambda path=None: (artifact, gates))
    monkeypatch.setattr(runtime, 'margin', lambda model, text: 2. if text.startswith('The people') else -2.)
    result = runtime.analyze_v5(TEXT)
    detector = result['detector']
    assert detector['category'] == 'mixed'
    assert detector['documentProbability'] is not None
    assert all(segment['probability'] is None for segment in result['segments'])
    assert detector['flaggedWords'] == result['segments'][0]['wordCount']
    assert detector['aiMarkedPercent'] == pytest.approx(100*detector['flaggedWords']/detector['analyzedWords'])
    gates['segment']['passed'] = False
    result = runtime.analyze_v5(TEXT)
    assert result['detector']['category'] != 'mixed'
    assert result['detector']['aiMarkedPercent'] is None
    assert all(segment['category'] == 'unassessed' for segment in result['segments'])
