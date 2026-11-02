"""Extraction/reconstruction tests use constructed HTML, never source labels."""
import copy
import importlib
import json
from pathlib import Path

import pytest


def collector():
    return importlib.import_module('tools.modern_human_collect')


def test_extraction_preserves_literal_prose_and_excludes_navigation_refs_tables():
    collect = collector()
    html = '<div class="mw-parser-output"><p>Water &amp; air <i>remain</i>.<sup class="reference">[1]</sup></p><table><tr><td><p>Table prose.</p></td></tr></table><div class="hatnote"><p>Other article.</p></div><p>Carbon<sup>14</sup> is here.</p></div>'
    assert collect.extract_paragraphs(html) == ['Water & air remain.', 'Carbon14 is here.']


def test_passages_are_whole_paragraphs_nonoverlapping_and_deterministic():
    collect = collector()
    paragraphs = [' '.join([f'word{i}'] * 100) for i in range(6)]
    source = '\n\n'.join(paragraphs)
    passages = collect.choose_passages(paragraphs)
    assert len(passages) == 2
    assert [passage['words'] for passage in passages] == [200, 200]
    assert passages[0]['end'] <= passages[1]['start']
    for passage in passages:
        assert source[passage['start']:passage['end']] == passage['text']


def test_huge_paragraph_is_not_truncated_or_rewritten_to_make_a_passage():
    collect = collector()
    assert collect.choose_passages(['word ' * 350]) == []


def test_revision_gate_rejects_future_revision_and_missing_identity():
    collect = collector()
    valid = {'pageid': 1, 'title': 'Example', 'revisions': [{'revid': 7, 'timestamp': '2017-01-02T00:00:00Z'}]}
    assert collect.checked_revision({'query': {'pages': {'1': valid}}})['revid'] == 7
    invalid = copy.deepcopy(valid)
    invalid['revisions'][0]['timestamp'] = '2021-01-01T00:00:00Z'
    with pytest.raises(ValueError, match='cutoff'):
        collect.checked_revision({'query': {'pages': {'1': invalid}}})
    invalid['revisions'][0].pop('revid')
    with pytest.raises(ValueError):
        collect.checked_revision({'query': {'pages': {'1': invalid}}})


def test_reconstruction_audit_detects_changed_text_offset_or_source_hash():
    collect = collector()
    paragraphs = [' '.join(['one'] * 100), ' '.join(['two'] * 100)]
    source = '\n\n'.join(paragraphs)
    passage = collect.choose_passages(paragraphs)[0]
    record = {'text': passage['text'], 'source_text_sha256': collect.digest(source.encode()),
              'excerpt_start': passage['start'], 'excerpt_end': passage['end']}
    collect.verify_excerpt(record, source)
    for field, value in [('text', 'Changed'), ('excerpt_start', 1), ('source_text_sha256', 'wrong')]:
        altered = {**record, field: value}
        with pytest.raises(ValueError):
            collect.verify_excerpt(altered, source)


def test_existing_external_report_cannot_be_rescored_or_overwritten(tmp_path):
    collect = collector()
    report = tmp_path / 'report.json'
    report.write_text('frozen', encoding='utf-8')
    with pytest.raises(ValueError, match='already exists'):
        collect.evaluate(tmp_path)
    assert report.read_text(encoding='utf-8') == 'frozen'


def test_frozen_live_corpus_reconstructs_from_archived_pre_cutoff_revisions():
    collect = collector()
    directory = Path(__file__).resolve().parents[1] / 'data/modern-human'
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    assert collect.digest((directory / 'corpus.jsonl').read_bytes()) == manifest['corpusSha256']
    for metadata in (directory / 'raw').glob('*.meta.json'):
        archived = json.loads(metadata.read_text(encoding='utf-8'))
        assert collect.digest((directory / 'raw' / archived['file']).read_bytes()) == archived['sha256']
    for row in [json.loads(line) for line in (directory / 'corpus.jsonl').read_text(encoding='utf-8').splitlines()]:
        assert row['split'] == 'test'
        assert row['label'] == 'human'
        assert row['revision_timestamp'] <= collect.CUTOFF
        collect.verify_excerpt(row, (directory / row['source_text_file']).read_text(encoding='utf-8'))
    snapshot = directory / manifest['collectorSnapshotFile']
    assert collect.digest(snapshot.read_bytes()) == manifest['collectorSha256']
