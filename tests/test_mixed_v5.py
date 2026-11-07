"""Exact mixed-origin diagnostics must preserve lineage, not invent new evidence."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from tools import mixed_v5


def row(identifier, label, text, **overrides):
    return {
        'source_id': identifier, 'label': label, 'text': text,
        'text_sha256': hashlib.sha256(text.encode()).hexdigest(),
        'author_id': 'author-a' if label == 'human' else 'commission-a',
        'document_id': 'document-a' if label == 'human' else 'generation-a',
        'source_group_id': 'family-a', 'language': 'sv', 'split': 'test',
        'genre': 'technical-fixture', 'model': None if label == 'human' else 'fixture-generator',
        'provenance': {'status': 'synthetic-test-only', 'source': 'unit test'},
        **overrides,
    }


def test_mixed_diagnostic_preserves_exact_unicode_origins_and_counts_words_once():
    records = [row('human-a', 'human', 'Åsa läser. 😀'),
               row('ai-a', 'ai', 'Här finns tre ord.')]
    result = mixed_v5.compose_mixed(records)
    assert len(result) == 1
    mixed = result[0]
    assert mixed['text'] == 'Åsa läser. 😀\n\nHär finns tre ord.'
    assert mixed['knownAiWordShare'] == pytest.approx(100 * 4 / 6)
    assert mixed['qualityEvidence'] is False
    assert mixed['independentSourceFamiliesAdded'] == 0
    assert mixed['sourceSplit'] == 'test'
    assert mixed['purpose'] == 'historical_segment_regression'
    assert mixed['segments'][0]['start'] == 0
    assert mixed['segments'][0]['end'] == 14
    assert mixed['segments'][1]['start'] == 16
    encoded = mixed['text'].encode('utf-16-le')
    for segment, original in zip(mixed['segments'], records, strict=True):
        assert encoded[2 * segment['start']:2 * segment['end']].decode('utf-16-le') == original['text']
        assert segment['parentSourceId'] == original['source_id']
        assert segment['parentTextSha256'] == original['text_sha256']
    assert mixed['analyzableWords'] == 6
    assert mixed['knownAiWords'] == 4


@pytest.mark.parametrize('field,value', [('split', 'train'), ('language', 'en')])
def test_mixed_diagnostic_rejects_inconsistent_family_partition_or_language(field, value):
    records = [row('human-a', 'human', 'Här är originalet.'),
               row('ai-a', 'ai', 'Detta är en generering.', **{field: value})]
    with pytest.raises(ValueError):
        mixed_v5.compose_mixed(records)


def test_mixed_diagnostic_rejects_changed_source_bytes_and_missing_origin():
    human = row('human-a', 'human', 'Här är originalet.')
    ai = row('ai-a', 'ai', 'Detta är en generering.')
    human['text'] += ' Ändrat.'
    with pytest.raises(ValueError, match='hash'):
        mixed_v5.compose_mixed([human, ai])
    with pytest.raises(ValueError, match='origin'):
        mixed_v5.compose_mixed([row('edited', 'ai_edited', 'En redigerad text.')])


def test_derivatives_never_create_independent_groups_or_promote_old_test_to_new_holdout():
    records = [row('human-a', 'human', 'Här är originalet.'),
               row('ai-a', 'ai', 'Detta är den första genereringen.'),
               row('ai-b', 'ai', 'Detta är den andra genereringen.', model='another-fixture')]
    result = mixed_v5.compose_mixed(records)
    assert len(result) == 2
    assert {r['source_group_id'] for r in result} == {'family-a'}
    assert {r['sourceSplit'] for r in result} == {'test'}
    assert all(r['qualityEvidence'] is False for r in result)
    assert all(r['independentSourceFamiliesAdded'] == 0 for r in result)
    assert len({r['id'] for r in result}) == 2


def test_same_human_author_cannot_cross_source_partitions():
    records = [row('human-a', 'human', 'En första källa.'),
               row('ai-a', 'ai', 'Den första genereringen.'),
               row('human-b', 'human', 'En andra källa.', source_group_id='family-b',
                   document_id='document-b', split='train')]
    with pytest.raises(ValueError, match='partition'):
        mixed_v5.compose_mixed(records)


def test_cli_reproduces_archived_compositions_and_refuses_overwrite(tmp_path):
    root = Path(__file__).resolve().parents[1]
    output = tmp_path / 'mixed'
    command = [sys.executable, 'tools/mixed_v5.py', '--output', str(output)]
    completed = subprocess.run(command, cwd=root, capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stderr
    actual = (output / 'corpus.jsonl').read_bytes()
    assert actual == (root / 'data/v5-mixed-regression/corpus.jsonl').read_bytes()
    manifest = json.loads((output / 'manifest.json').read_text())
    assert manifest['documents'] == 24
    assert manifest['byLanguage'] == {'en': 12, 'sv': 12}
    assert manifest['independentSourceFamiliesAdded'] == 0
    assert manifest['corpusSha256'] == hashlib.sha256(actual).hexdigest()
    repeated = subprocess.run(command, cwd=root, capture_output=True, text=True, check=False)
    assert repeated.returncode != 0
    assert 'Output exists' in repeated.stderr
    assert (output / 'corpus.jsonl').read_bytes() == actual
