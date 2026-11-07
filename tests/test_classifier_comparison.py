"""Offline comparison guards against selecting on reused test or regression data."""
import copy
import json
from pathlib import Path

import pytest

from tools import compare_classifiers as comparison
from tools import model_evaluate as evaluation
from tools import train_baseline


ROOT = Path(__file__).resolve().parents[1]


def fixture_rows():
    rows = []
    for split, count in [('train', 4), ('validation', 2), ('test', 2)]:
        for label in ('human', 'ai'):
            for index in range(count):
                identity = f'{split}-{label}-{index}'
                noun = f'{label}{split}{index}'
                sentence = f'The {noun} and our {noun} were {noun} because the {noun} was {noun} with our {noun} and we {noun} have the {noun}. '
                rows.append({
                    'source_id': identity, 'text': sentence * 4, 'label': label, 'split': split,
                    'source_group_id': identity, 'document_id': identity, 'author_id': identity,
                    'language': 'en', 'genre': 'constructed', 'model': None if label == 'human' else 'constructed',
                    'provenance': {'kind': 'synthetic-fixture', 'source': 'repository:test_classifier_comparison.py',
                                   'rights': {'status': 'verified', 'basis': 'owned', 'evidence': 'Constructed engineering fixture.'},
                                   'label': {'method': 'fixture-assignment', 'evidence': 'Assigned test labels, not accuracy evidence.'}},
                })
    return rows


@pytest.fixture(scope='module')
def fixture_baseline():
    rows = fixture_rows()
    artifact, _ = train_baseline.train_run(rows, evaluation.canonical(rows).encode(), fixture=True)
    return rows, artifact


def test_alternatives_refuse_nontraining_rows_before_fitting():
    rows = fixture_rows()
    for name in comparison.ALTERNATIVES:
        with pytest.raises(ValueError, match='train split'):
            comparison.fit_candidate(name, rows)


def test_alternative_vocabulary_and_fit_provenance_use_only_training_rows():
    train = [row for row in fixture_rows() if row['split'] == 'train']
    for name in comparison.ALTERNATIVES:
        candidate = comparison.fit_candidate(name, train)
        details = comparison.fitted_details(candidate)
        assert details['training']['split'] == 'train'
        assert set(details['training']['sourceIds']) == {row['source_id'] for row in train}
        assert details['featureCount'] > 0
        assert len(details['weightsSha256']) == 64
        names = candidate.features.get_feature_names_out()
        assert not any('sentinelholdout' in value for value in names)
        before = details['weightsSha256']
        candidate.features.transform(['sentinelholdout sentinelholdout'])
        assert comparison.fitted_details(candidate)['weightsSha256'] == before


def test_reused_test_changes_cannot_change_model_fitting_threshold_or_winner(fixture_baseline):
    rows, artifact = fixture_baseline
    first = comparison.compare_run(rows, artifact, fixture=True)
    changed = copy.deepcopy(rows)
    for row in changed:
        if row['split'] == 'test':
            row['text'] = row['text'].replace('because', 'sentinelholdout')
    second = comparison.compare_run(changed, artifact, fixture=True)
    assert first['candidateSelection'] == second['candidateSelection']
    for left, right in zip(first['candidates'], second['candidates'], strict=True):
        assert left['training'] == right['training']
        assert left['weightsSha256'] == right['weightsSha256']
        assert left['validation'] == right['validation']
        assert left['historicalTestDiagnostics']['independentEvidence'] is False
        metrics = left['historicalTestDiagnostics']['overall']
        assert {'precision', 'recallAssessed', 'f1', 'falsePositiveRate', 'falseNegativeRate', 'auroc', 'coverage'} <= metrics.keys()
    assert first['productionApproved'] is False
    assert first['calibration']['available'] is False


def test_changed_development_corpus_cannot_be_claimed_as_the_frozen_baseline(fixture_baseline):
    rows, artifact = fixture_baseline
    changed = copy.deepcopy(rows)
    changed[0]['text'] += ' An added training detail.'
    with pytest.raises(ValueError, match='fitting provenance'):
        comparison.compare_run(changed, artifact, fixture=True)


def test_candidate_selection_rejects_test_selection_and_uses_declared_tie_break():
    metrics = {'recallAllAI': 1, 'falsePositiveRate': 0, 'coverage': 1}
    candidates = [{'name': name, 'validation': {'selectionSplit': 'validation', 'metrics': metrics}} for name in comparison.CANDIDATE_ORDER]
    assert comparison.choose_candidate(candidates)['name'] == comparison.CANDIDATE_ORDER[0]
    candidates[0]['validation']['selectionSplit'] = 'test'
    with pytest.raises(ValueError, match='validation'):
        comparison.choose_candidate(candidates)


def test_modern_human_regression_preserves_known_false_positives_without_selection():
    artifact = json.loads((ROOT / 'models/experimental/pilot-v1-audited/model.json').read_text())
    rows = evaluation.load_records(ROOT / 'data/modern-human/corpus.jsonl')
    historical = json.loads((ROOT / 'data/modern-human/report.json').read_text())
    result = comparison.modern_human_regression(artifact, rows, historical)
    assert result['usedForSelection'] is False
    assert result['independentEvidence'] is False
    assert result['allHistoricalMarginsMatch'] is True
    assert result['falsePositiveSourceIds'] == ['wikipedia-en-816636789-p2', 'wikipedia-sv-42244645-p2']
    assert result['overall']['humanFalsePositives'] == {'count': 2, 'assessedDenominator': 8, 'allHumanDenominator': 8}
    assert result['overall']['falsePositiveRate'] == .25
    assert result['overall']['coverage'] == 1
    assert result['overall']['auroc'] is None
    for slices in ('byLanguage', 'byGenre', 'byLength', 'byModel'):
        assert all(metrics['f1'] is None for metrics in result[slices].values())


def test_report_writer_refuses_to_replace_existing_evidence(tmp_path):
    path = tmp_path / 'comparison.json'
    path.write_text('historical evidence\n')
    with pytest.raises(FileExistsError):
        comparison.write_report(path, {})
    assert path.read_text() == 'historical evidence\n'
