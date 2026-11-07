"""Leakage and calibration invariants; fixtures verify code, never ML quality."""
import copy

import pytest

from tools.train_v5 import audit_dataset, fit_calibration, calibration_metrics


def row(source, split, family=None, author=None, **extra):
    return {'source_id': source, 'document_id': 'doc-' + source,
            'author_id': author or 'author-' + source, 'source_group_id': family or 'family-' + source,
            'text': 'unique words in document ' + source, 'label': 'human', 'language': 'en',
            'genre': 'test-only-fixture', 'model': None, 'split': split,
            'provenance': {'kind': 'independent', 'source': 'engineering-test',
                           'rights': {'status': 'verified', 'basis': 'owned', 'evidence': 'engineering-test'},
                           'label': {'method': 'verified-source', 'evidence': 'engineering-test'}}, **extra}


@pytest.mark.parametrize('change', [
    {'author_id': 'author-a'}, {'document_id': 'doc-a'}, {'source_group_id': 'family-a'},
    {'related_source_id': 'a'}, {'parent_source_ids': ['a']}, {'paraphrase_group_id': 'paraphrase-a'},
    {'text': 'unique words in document a'},
])
def test_audit_rejects_author_document_family_parent_paraphrase_and_text_leaks(change):
    original = row('a', 'train', paraphrase_group_id='paraphrase-a')
    other = row('b', 'test', **change)
    with pytest.raises(ValueError, match='leakage'):
        audit_dataset([original, other])


def test_audit_rejects_unverified_rights_and_incorrect_hash():
    original = row('a', 'train')
    other = copy.deepcopy(original)
    other['provenance']['rights']['status'] = 'unknown'
    with pytest.raises(ValueError, match='rights'):
        audit_dataset([other])
    with pytest.raises(ValueError, match='hash'):
        audit_dataset([{**original, 'text_sha256': '0' * 64}])


def test_calibration_is_separate_and_reports_actual_probability_error():
    calibration = [{'split': 'calibration', 'label': 'human', 'score': score} for score in (-3, -2, -.5)]
    calibration += [{'split': 'calibration', 'label': 'ai', 'score': score} for score in (.5, 2, 3)]
    fitted = fit_calibration(calibration)
    assert fitted['slope'] > 0
    assert fitted['fitting']['classCounts'] == {'human': 3, 'ai': 3}
    with pytest.raises(ValueError, match='calibration split'):
        fit_calibration([{**record, 'split': 'validation'} for record in calibration])
    assert calibration_metrics([0, 1], [.1, .9])['brier'] == pytest.approx(.01)
    assert calibration_metrics([0, 1], [.1, .9])['ece10'] == pytest.approx(.1)


def test_historical_manifest_cannot_relabel_known_pilot_as_fresh():
    import json
    from pathlib import Path
    records = [json.loads(line) for line in Path('data/pilot/corpus.jsonl').read_text().splitlines()]
    with pytest.raises(ValueError, match='historical'):
        audit_dataset(records, evidence_use='fresh-independent-holdout')


def test_renaming_a_historical_derivative_does_not_make_it_fresh():
    derivative = row('brand-new-id', 'test', parent_source_ids=['pg1342-h1'])
    with pytest.raises(ValueError, match='historical'):
        audit_dataset([derivative], evidence_use='fresh-independent-holdout')


def test_frozen_replay_rejects_development_derivatives():
    import json
    from pathlib import Path
    from tools.evaluate_v5 import assert_independent_from_development
    artifact = json.loads(Path('models/v5/detector.json').read_text())
    with pytest.raises(ValueError, match='derivative'):
        assert_independent_from_development([row('new-name', 'test', parent_source_ids=['pg1342-h1'])], artifact)


def test_output_preservation_is_the_cli_default(tmp_path):
    from tools.train_v5 import main as train_main
    from tools.evaluate_v5 import main as evaluate_main
    output = tmp_path/'detector.json'
    output.write_text('preserve-me')
    with pytest.raises(SystemExit) as error:
        train_main(['--output-dir', str(tmp_path)])
    assert error.value.code == 2
    with pytest.raises(SystemExit) as error:
        evaluate_main(['--data', 'data/pilot/corpus.jsonl', '--output', str(output)])
    assert error.value.code == 2
    assert output.read_text() == 'preserve-me'
