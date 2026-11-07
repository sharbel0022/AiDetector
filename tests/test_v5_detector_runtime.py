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


def rebind_evidence(evidence):
    evidence['lineageAudit']['bindingSha256'] = digest({
        key: value for key, value in evidence.items() if key != 'lineageAudit'
    })


@pytest.mark.parametrize(('level', 'calibration_gate'), [
    ('document', 'calibration'), ('segment', 'segmentCalibration'),
])
@pytest.mark.parametrize('scope', ['overall', 'sv', 'en'])
def test_binary_assessed_cannot_exceed_assessed(level, calibration_gate, scope):
    artifact = evidence_fixture()
    assert gate_results(artifact)[level]['passed']
    evidence = artifact['evidence'][level]
    metrics = evidence['metrics'] if scope == 'overall' else evidence['byLanguage'][scope]
    metrics['assessed'] = metrics['binaryAssessed'] * 7 // 10
    metrics['coverage'] = .7
    rebind_evidence(evidence)
    gates = gate_results(artifact)
    assert not gates[level]['passed']
    assert not gates[calibration_gate]['passed']
    other_level = 'segment' if level == 'document' else 'document'
    assert gates[other_level]['passed']


@pytest.mark.parametrize(('level', 'calibration_gate'), [
    ('document', 'calibration'), ('segment', 'segmentCalibration'),
])
@pytest.mark.parametrize('scope', ['overall', 'sv', 'en'])
def test_calibration_without_evaluated_records_cannot_open_probability_gate(level, calibration_gate, scope):
    artifact = evidence_fixture()
    assert gate_results(artifact)[calibration_gate]['passed']
    evidence = artifact['evidence'][level]
    metrics = evidence['metrics'] if scope == 'overall' else evidence['byLanguage'][scope]
    metrics['calibration'] = {'count': 0, 'ece10': 0., 'brier': 0., 'bins': []}
    rebind_evidence(evidence)
    gates = gate_results(artifact)
    assert gates[level]['passed']
    assert not gates[calibration_gate]['passed']
    other_gate = 'segmentCalibration' if level == 'document' else 'calibration'
    assert gates[other_gate]['passed']


@pytest.mark.parametrize(('path', 'value'), [
    (('count',), 799),
    (('count',), 800.0),
    (('count',), True),
    (('bins',), []),
    (('bins',), {}),
    (('bins',), [{}]),
    (('bins', 0, 'count'), 0),
    (('bins', 0, 'count'), -1),
    (('bins', 0, 'count'), 399),
    (('bins', 0, 'count'), 400.0),
    (('bins', 0, 'lower'), -.1),
    (('bins', 0, 'lower'), .01),
    (('bins', 0, 'upper'), 1.1),
    (('bins', 0, 'upper'), .2),
    (('bins', 0, 'meanProbability'), -.01),
    (('bins', 0, 'meanProbability'), 1.01),
    (('bins', 0, 'meanProbability'), .2),
    (('bins', 0, 'meanProbability'), False),
    (('bins', 0, 'observedAiFraction'), -.01),
    (('bins', 0, 'observedAiFraction'), 1.01),
    (('bins', 0, 'observedAiFraction'), False),
    (('ece10',), 0.),
])
def test_contradictory_calibration_summaries_fail_closed_after_rebinding(path, value):
    artifact = evidence_fixture()
    assert gate_results(artifact)['calibration']['passed']
    evidence = artifact['evidence']['document']
    target = evidence['metrics']['calibration']
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    rebind_evidence(evidence)
    gates = gate_results(artifact)
    assert gates['document']['passed']
    assert not gates['calibration']['passed']


def test_duplicate_calibration_bins_fail_closed_even_when_counts_and_ece_match():
    artifact = evidence_fixture()
    evidence = artifact['evidence']['document']
    bins = evidence['metrics']['calibration']['bins']
    bins[1] = copy.deepcopy(bins[0])
    rebind_evidence(evidence)
    gates = gate_results(artifact)
    assert gates['document']['passed']
    assert not gates['calibration']['passed']


@pytest.mark.parametrize(('level', 'calibration_gate'), [
    ('document', 'calibration'), ('segment', 'segmentCalibration'),
])
def test_calibration_bins_cannot_claim_fractional_ai_observations(level, calibration_gate):
    artifact = evidence_fixture()
    evidence = artifact['evidence'][level]
    for metrics in [evidence['metrics'], *evidence['byLanguage'].values()]:
        for bucket in metrics['calibration']['bins']:
            bucket['observedAiFraction'] = bucket['meanProbability']
        metrics['calibration']['ece10'] = 0.
    rebind_evidence(evidence)
    gates = gate_results(artifact)
    assert gates[level]['passed']
    assert not gates[calibration_gate]['passed']


@pytest.mark.parametrize('scope', ['overall', 'sv', 'en'])
def test_calibration_bins_must_match_assessed_ai_truth_count(scope):
    from tools.model_evaluate import wilson
    artifact = evidence_fixture()
    evidence = artifact['evidence']['document']
    metrics = evidence['metrics'] if scope == 'overall' else evidence['byLanguage'][scope]
    calibration = metrics['calibration']
    first, last = calibration['bins']
    first['observedAiFraction'] = 1 / first['count']
    first['observedAiFractionInterval95'] = wilson(1, first['count'])
    calibration['ece10'] = (first['observedAiFraction'] - first['meanProbability'] +
                            1 - last['meanProbability']) / 2
    rebind_evidence(evidence)
    gates = gate_results(artifact)
    assert gates['document']['passed']
    assert not gates['calibration']['passed']


@pytest.mark.parametrize(('field', 'value'), [
    ('lower', -.01), ('lower', .01), ('upper', 1.01), ('upper', .02),
    ('n', 399), ('n', 400.), ('n', True),
])
def test_calibration_bin_wilson_intervals_must_match_observed_counts(field, value):
    artifact = evidence_fixture()
    evidence = artifact['evidence']['document']
    evidence['metrics']['calibration']['bins'][0]['observedAiFractionInterval95'][field] = value
    rebind_evidence(evidence)
    gates = gate_results(artifact)
    assert gates['document']['passed']
    assert not gates['calibration']['passed']


def test_calibration_bins_require_the_reported_wilson_interval():
    artifact = evidence_fixture()
    evidence = artifact['evidence']['document']
    del evidence['metrics']['calibration']['bins'][0]['observedAiFractionInterval95']
    rebind_evidence(evidence)
    assert not gate_results(artifact)['calibration']['passed']


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
