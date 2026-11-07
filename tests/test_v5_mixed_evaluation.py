"""Mixed replay must measure source alignment without inventing validation."""
import copy
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def sources():
    read = lambda name: [json.loads(line) for line in (ROOT / name).read_text().splitlines()]
    return read('data/v5-mixed-regression/corpus.jsonl'), read('data/pilot/corpus.jsonl')


def test_mixed_runtime_replay_has_exact_origins_and_unavailable_quality_metrics():
    from tools.evaluate_mixed_v5 import evaluate_mixed
    mixed, parents = sources()
    result = evaluate_mixed(mixed, parents)
    assert result['qualityEvidence'] is False
    assert result['sourceSplit'] == 'test'
    assert result['documents'] == 8
    assert result['existingSourceFamilies'] == 4
    assert result['independentSourceFamiliesAdded'] == 0
    assert result['alignment']['sourceExact'] is True
    assert result['alignment']['crossOriginSegments'] == 0
    assert result['alignment']['originWords'] == result['alignment']['runtimeWords']
    assert result['metrics']['classificationCoverage'] == 0
    for key in ('segmentPrecision', 'humanFalsePositiveRate', 'markedShareMeanAbsoluteError'):
        assert result['metrics'][key] is None
    for record in result['records']:
        assert record['detectorMarkedShare'] is None
        assert record['segmentValidated'] is False
        assert 0 < record['knownConstructionAiShare'] < 100


@pytest.mark.parametrize('change', ['text', 'origin', 'source_split'])
def test_mixed_replay_rejects_changed_sources_or_mislabelled_derivatives(change):
    from tools.evaluate_mixed_v5 import evaluate_mixed
    mixed, parents = sources()
    bad = copy.deepcopy(mixed)
    if change == 'text':
        bad[0]['text'] += ' changed'
    elif change == 'origin':
        bad[0]['segments'][0]['origin'] = 'ai'
    else:
        bad[0]['sourceSplit'] = 'test'
    with pytest.raises(ValueError, match='construction'):
        evaluate_mixed(bad, parents)
