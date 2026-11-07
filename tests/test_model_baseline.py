"""Experimental baseline regressions; constructed rows are engineering fixtures only."""
import copy
import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def modules():
    from tools import model_evaluate, train_baseline
    return model_evaluate, train_baseline


def training_rows():
    rows = []
    for label, topic in [('human', 'harbour lantern weather sailors'), ('ai', 'algorithm matrix vector computation')]:
        for i in range(4):
            rows.append({'text': f'The {topic} was discussed. We considered {topic} carefully. ' * (i + 2),
                         'label': label, 'split': 'train', 'source_id': f'{label}-{i}',
                         'document_id': f'{label}-document-{i // 2}',
                         'source_group_id': f'{label}-group-{i // 2}', 'author_id': f'{label}-author-{i // 2}'})
    return rows


def corpus_fixture():
    """Every row has distinct five-token shingles; labels are purely assigned."""
    rows = []
    for split, count in [('train', 4), ('validation', 2), ('test', 2)]:
        for label in ('human', 'ai'):
            for index in range(count):
                source_id = f'{split}-{label}-{index}'
                term = f'{label}{split}{index}'
                sentence = f'The {term} and our {term} were {term} because the {term} was {term} with our {term} and we {term} have the {term}. '
                rows.append({'source_id': source_id, 'text': sentence * 4, 'label': label, 'split': split,
                             'source_group_id': source_id, 'document_id': source_id, 'author_id': source_id,
                             'language': 'en', 'genre': 'constructed', 'model': None if label == 'human' else 'constructed',
                             'provenance': {'kind': 'synthetic-fixture', 'source': 'repository:test_model_baseline.py',
                                            'rights': {'status': 'verified', 'basis': 'owned', 'evidence': 'Constructed test fixture.'},
                                            'label': {'method': 'fixture-assignment', 'evidence': 'Assigned engineering labels, not detector evidence.'}}})
    return rows


def test_cli_trains_no_model_when_dataset_is_missing(tmp_path):
    result = subprocess.run([sys.executable, 'tools/train_baseline.py', '--data', str(tmp_path / 'missing.jsonl'),
                             '--output', str(tmp_path / 'model')], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode != 0
    assert 'Dataset file' in result.stderr
    assert not (tmp_path / 'model').exists()


def test_selection_requires_validation_and_prioritizes_human_false_positives():
    evaluate, _ = modules()
    rows = [{'split': 'validation', 'label': label, 'score': score}
            for label, score in [('human', .1), ('human', .9), ('ai', .8), ('ai', 1.0)]]
    selection = evaluate.select_threshold(rows)
    assert selection['threshold'] == 1.0
    assert selection['metrics']['confusion'] == {'tp': 1, 'fp': 0, 'tn': 2, 'fn': 1}
    assert selection['selectionSplit'] == 'validation'
    with pytest.raises(ValueError, match='validation'):
        evaluate.select_threshold([{**row, 'split': 'test'} for row in rows])


def test_selection_can_abstain_from_all_positive_flags():
    evaluate, _ = modules()
    result = evaluate.select_threshold([{'split': 'validation', 'label': 'human', 'score': 2.0},
                                        {'split': 'validation', 'label': 'ai', 'score': 1.0}])
    assert result['threshold'] > 2.0
    assert result['metrics']['confusion'] == {'tp': 0, 'fp': 0, 'tn': 1, 'fn': 1}


def test_metrics_keep_human_denominators_abstentions_and_tied_ranks():
    evaluate, _ = modules()
    rows = [{'label': label, 'score': score} for label, score in
            [('human', 0), ('human', 1), ('human', None), ('ai', 1), ('ai', 2), ('ai', None)]]
    result = evaluate.summarize(rows, 1)
    assert result['confusion'] == {'tp': 2, 'fp': 1, 'tn': 1, 'fn': 0}
    assert result['humanFalsePositives'] == {'count': 1, 'assessedDenominator': 2, 'allHumanDenominator': 3}
    assert result['abstentionsByLabel'] == {'human': 1, 'ai': 1, 'ai-edited': 0}
    assert result['auroc'] == .875
    assert result['f1'] == .8
    assert result['recallAllAI'] == 2 / 3
    assert result['intervals95']['falsePositiveRate']['n'] == 2
    assert result['calibration']['available'] is False


def test_empty_class_metrics_remain_unknown():
    evaluate, _ = modules()
    result = evaluate.summarize([{'label': 'human', 'score': None}], 0)
    assert result['falsePositiveRate'] is None
    assert result['auroc'] is None
    assert result['accuracyAssessed'] is None


def test_training_rejects_holdout_rows_and_insufficient_class_groups():
    _, train = modules()
    rows = training_rows()
    with pytest.raises(ValueError, match='train split'):
        train.fit_baseline([{**rows[0], 'split': 'test'}, *rows[1:]])
    with pytest.raises(ValueError, match='at least 4'):
        train.fit_baseline(rows[:3] + rows[4:])
    for row in rows:
        row['source_group_id'] = row['label']
    with pytest.raises(ValueError, match='source groups'):
        train.fit_baseline(rows)


def test_safe_json_export_matches_sklearn_margin_and_excludes_heldout_vocabulary():
    evaluate, train = modules()
    artifact, vectorizer, classifier = train.fit_baseline(training_rows())
    texts = ['The harbour weather was carefully discussed.', 'THE algorithm  matrix\n\tvector!', 'Sjö ÅÄÖ résumé.']
    expected = classifier.decision_function(vectorizer.transform(texts))
    # Serialized weights must preserve held-out margins, not merely training predictions.
    exported = json.loads(json.dumps(artifact, allow_nan=False))
    for text, margin in zip(texts, expected):
        assert evaluate.score_text(exported, text) == pytest.approx(float(margin), abs=1e-12)
    assert 'xyz' not in artifact['vocabulary']
    assert artifact['scoreSemantics'] == 'uncalibrated_logistic_margin'
    assert artifact['calibration']['available'] is False


def test_artifact_loader_rejects_nonfinite_or_misaligned_weights():
    evaluate, train = modules()
    artifact, _, _ = train.fit_baseline(training_rows())
    artifact['coefficients'][0] = math.nan
    with pytest.raises(ValueError, match='finite'):
        evaluate.validate_artifact(artifact)
    artifact, _, _ = train.fit_baseline(training_rows())
    artifact['idf'].pop()
    with pytest.raises(ValueError, match='length'):
        evaluate.validate_artifact(artifact)


def test_strict_node_audit_is_reused_and_rejects_duplicates_and_split_leakage():
    evaluate, _ = modules()
    rows = [json.loads(line) for line in (ROOT / 'tools/fixtures/detector.synthetic.jsonl').read_text().splitlines()]
    result = evaluate.audit_records(rows, fixture=True)
    assert result['dataset']['leakage']['passed'] is True
    assert len(result['analyses']) == len(rows)
    duplicate = copy.deepcopy(rows)
    duplicate[-1]['text'] = duplicate[0]['text']
    with pytest.raises(ValueError, match='duplicate'):
        evaluate.audit_records(duplicate, fixture=True)
    leaked = copy.deepcopy(rows)
    leaked[-1]['author_id'] = leaked[0]['author_id']
    with pytest.raises(ValueError, match='Split leakage'):
        evaluate.audit_records(leaked, fixture=True)


def test_test_slices_do_not_include_validation_rows():
    evaluate, _ = modules()
    rows = [{'split': 'test', 'label': 'human', 'score': 0, 'language': 'sv', 'genre': 'letter',
             'words': 100, 'model': '(human)', 'source_group_id': 'h'},
            {'split': 'test', 'label': 'ai', 'score': 2, 'language': 'en', 'genre': 'essay',
             'words': 350, 'model': 'unseen-model', 'source_group_id': 'a'},
            {'split': 'validation', 'label': 'ai', 'score': 100, 'language': 'xx', 'genre': 'leak',
             'words': 1, 'model': 'validation-only', 'source_group_id': 'v'}]
    report = evaluate.heldout_report(rows, 1)
    assert report['overall']['total'] == 2
    assert set(report['byLanguage']) == {'en', 'sv'}
    assert set(report['byLength']) == {'medium', 'long'}
    assert 'validation-only' not in report['byModel']


def test_training_run_keeps_model_and_threshold_frozen_when_test_text_changes():
    _, train = modules()
    records = corpus_fixture()
    first, report = train.train_run(records, json.dumps(records).encode(), fixture=True)
    changed = copy.deepcopy(records)
    for row in changed:
        if row['split'] == 'test':
            row['text'] = row['text'].replace('because', 'xyzheldoutvocabulary')
    second, _ = train.train_run(changed, json.dumps(changed).encode(), fixture=True)
    assert first['vocabulary'] == second['vocabulary']
    assert first['idf'] == second['idf']
    assert first['coefficients'] == second['coefficients']
    assert first['selection'] == second['selection']
    assert report['trained']['overall']['total'] == 4
    assert report['status'] == 'synthetic-engineering-fixture'
    assert report['productionApproved'] is False


def test_training_run_rejects_missing_assessed_validation_class_before_fitting():
    _, train = modules()
    rows = corpus_fixture()
    rows = [row for row in rows if not (row['split'] == 'validation' and row['label'] == 'human')]
    with pytest.raises(ValueError, match='validation needs at least 2 assessed human'):
        train.train_run(rows, json.dumps(rows).encode(), fixture=True)


def test_human_source_group_false_flags_do_not_treat_excerpts_as_independent():
    evaluate, _ = modules()
    rows = [{'split': 'test', 'label': 'human', 'score': score, 'source_group_id': group,
             'language': 'en', 'genre': 'essay', 'words': 100, 'model': '(human)'}
            for group, score in [('a', 2), ('a', 3), ('a', None), ('b', 0), ('c', None)]]
    report = evaluate.heldout_report(rows, 1)
    assert report['humanSourceGroups']['total'] == 3
    assert report['humanSourceGroups']['assessed'] == 2
    assert report['humanSourceGroups']['withAnyFalsePositive'] == 1
    assert report['humanSourceGroups']['rateWithAnyFalsePositive'] == .5
    assert report['humanSourceGroups']['interval95']['n'] == 2


def test_leave_one_model_out_never_fits_or_selects_threshold_on_heldout_model():
    evaluate, train = modules()
    rows = corpus_fixture()
    # Add independent generated rows on the same commissioning source families.
    for row in [row for row in rows if row['label'] == 'ai']:
        row['model'] = 'llama3.2:3b'
        second = copy.deepcopy(row)
        second['source_id'] += '-second'
        second['model'] = 'qwen3.5:4b'
        second['text'] = second['text'].replace('our', 'their')
        rows.append(second)
    audit = evaluate.audit_records(rows, fixture=True)
    diagnostics = train.model_holdout_diagnostics(rows, audit['analyses'])
    assert len(diagnostics) == 2
    for diagnostic in diagnostics:
        assert diagnostic['available'] is True
        assert diagnostic['heldoutModel'] not in diagnostic['fitModels']
        assert diagnostic['heldoutModel'] not in diagnostic['thresholdModels']
        assert set(diagnostic['test']['byModel']) == {'(human)', diagnostic['heldoutModel']}
        assert diagnostic['test']['overall']['total'] == 4


@pytest.fixture(scope='module')
def complete_audited_fixture():
    _, train = modules()
    records = corpus_fixture()
    artifact, _ = train.train_run(records, json.dumps(records).encode(), fixture=True)
    return artifact, records


@pytest.mark.parametrize('model_directory', ['pilot-v1', 'pilot-v1-audited'])
def test_standalone_refuses_legacy_or_relabelled_validation(tmp_path, model_directory):
    records = [json.loads(line) for line in (ROOT / 'data/pilot/corpus.jsonl').read_text(encoding='utf-8').splitlines()]
    records = [{**row, 'split': 'test'} for row in records if row['split'] == 'validation']
    path = tmp_path / 'relabelled-validation.jsonl'
    path.write_text(''.join(json.dumps(row) + '\n' for row in records), encoding='utf-8')
    result = subprocess.run([sys.executable, 'tools/model_evaluate.py', '--data', str(path),
                             '--model', f'models/experimental/{model_directory}/model.json'], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode != 0, 'Legacy artifact must not certify validation rows as held-out test data'
    assert 'provenance' in result.stderr.lower() or 'legacy' in result.stderr.lower()
    assert not result.stdout.strip()


@pytest.mark.parametrize('split', ['train', 'validation'])
@pytest.mark.parametrize('field', ['source_id', 'document_id', 'author_id', 'source_group_id'])
def test_holdout_rejects_every_fitting_and_threshold_identity(complete_audited_fixture, split, field):
    evaluate, _ = modules()
    artifact, records = complete_audited_fixture
    original = next(row for row in records if row['split'] == split)
    candidate = {'split': 'test', 'source_id': 'new-source', 'document_id': 'new-document',
                 'author_id': 'new-author', 'source_group_id': 'new-family',
                 'text': 'Completely separate independent prose for the external audit.'}
    candidate[field] = original[field]
    with pytest.raises(ValueError, match=field):
        evaluate.assert_unseen_test(artifact, [candidate])


def test_holdout_rejects_development_text_even_when_all_ids_are_changed(complete_audited_fixture):
    evaluate, _ = modules()
    artifact, records = complete_audited_fixture
    original = next(row for row in records if row['split'] == 'validation')
    candidate = {'split': 'test', 'source_id': 'new-source', 'document_id': 'new-document',
                 'author_id': 'new-author', 'source_group_id': 'new-family',
                 'text': original['text'].upper().replace('.', ' ! ')}
    with pytest.raises(ValueError, match='text'):
        evaluate.assert_unseen_test(artifact, [candidate])


@pytest.mark.parametrize('tamper', ['provenance', 'weights', 'threshold', 'remove_provenance'])
def test_artifact_rejects_tampered_or_missing_development_audit(complete_audited_fixture, tamper):
    evaluate, _ = modules()
    artifact = copy.deepcopy(complete_audited_fixture[0])
    if tamper == 'provenance':
        artifact.setdefault('developmentProvenance', {}).setdefault('thresholdSelection', {})['sourceIds'] = ['forged']
    elif tamper == 'weights':
        artifact['coefficients'][0] += .01
    elif tamper == 'threshold':
        artifact['selection']['threshold'] += .01
    else:
        artifact.pop('developmentProvenance', None)
    with pytest.raises(ValueError, match='provenance|binding|audit'):
        evaluate.validate_artifact(artifact)


def test_audited_pilot_preserves_frozen_weights_threshold_and_all_test_margins():
    evaluate, _ = modules()
    original_directory = ROOT / 'models/experimental/pilot-v1'
    audited_directory = ROOT / 'models/experimental/pilot-v1-audited'
    original = json.loads((original_directory / 'model.json').read_text(encoding='utf-8'))
    audited = evaluate.validate_artifact(json.loads((audited_directory / 'model.json').read_text(encoding='utf-8')))
    for field in ['config', 'configSha256', 'vocabulary', 'idf', 'coefficients', 'intercept', 'selection']:
        assert audited[field] == original[field], f'Audit correction unexpectedly changed {field}'
    old_report = json.loads((original_directory / 'report.json').read_text(encoding='utf-8'))
    rows = evaluate.load_records(ROOT / 'data/pilot/corpus.jsonl')
    evaluate.assert_unseen_test(audited, rows)
    scores = {row['source_id']: evaluate.score_text(audited, row['text']) for row in rows if row['split'] == 'test'}
    assert len(scores) == 20
    assert scores == {row['source_id']: row['score'] for row in old_report['trained']['predictions']}
