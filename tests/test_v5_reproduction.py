"""Numerical portability must not weaken model/data integrity or release gates."""
import copy
import json
import math
from pathlib import Path
import subprocess
import sys

import pytest

from ai.detector.linear import canonical, digest


@pytest.fixture
def artifact():
    return json.loads(Path('models/v5/detector.json').read_text())


def rebind(value):
    """Construct a self-consistent fixture using the training artifact contract."""
    for level, evidence in value['evidence'].items():
        evidence['modelSha256'] = digest(value[level + 'Model'])
        evidence['thresholdsSha256'] = digest(value[level + 'Thresholds'])
        calibration = value[level + 'Calibration']
        evidence['calibrationSha256'] = digest(calibration) if calibration else None
        evidence['lineageAudit']['bindingSha256'] = digest({
            key: item for key, item in evidence.items() if key != 'lineageAudit'})
    value['modelVersion'] = ('textlab-v5-' + digest(value['documentModel'])[:12] + '-' +
                             value['lineageAudit']['datasetCanonicalSha256'][:8])
    value['artifactSha256'] = digest({key: item for key, item in value.items()
                                      if key != 'artifactSha256'})
    return value


def compare(tmp_path, reference, candidate):
    # The observable CLI contract is also the CI contract: JSON and nonzero on failure.
    paths = [tmp_path / 'reference.json', tmp_path / 'candidate.json']
    for path, value in zip(paths, (reference, candidate), strict=True):
        path.write_text(canonical(value) + '\n')
    completed = subprocess.run([sys.executable, '-m', 'tools.check_v5_reproduction',
                                *map(str, paths)], capture_output=True, text=True)
    assert completed.stdout, completed.stderr
    report = json.loads(completed.stdout)
    assert completed.returncode == (0 if report['passed'] else 1), completed.stderr
    return report


def test_tiny_rebound_float_changes_are_accepted_and_measured(tmp_path, artifact):
    candidate = copy.deepcopy(artifact)
    for values, key in ((candidate['documentModel']['coefficients'], 0),
                        (candidate['documentModel']['blocks'][0]['idf'], 0),
                        (candidate['documentThresholds'], 'aiMin'),
                        (candidate['evidence']['document']['predictions'][0], 'score')):
        values[key] = math.nextafter(values[key], math.inf)
    report = compare(tmp_path, artifact, rebind(candidate))
    assert report['passed'] is True
    assert report['numericComparison']['changedFloatCount'] == 4
    assert 0 < report['numericComparison']['maximumAbsoluteDifference'] < 1e-12
    assert report['checks']['gatesEqual'] is True
    assert report['reference']['artifactSha256'] != report['candidate']['artifactSha256']
    assert all(report['checks'].values())


@pytest.mark.parametrize('mutation', ['coefficient', 'vocabulary', 'dataset', 'count',
                                      'type', 'structure', 'unlisted_hash'])
def test_material_or_exact_contract_changes_are_rejected(tmp_path, artifact, mutation):
    candidate = copy.deepcopy(artifact)
    if mutation == 'coefficient':
        candidate['documentModel']['coefficients'][0] += 1e-6
    elif mutation == 'vocabulary':
        vocabulary = candidate['documentModel']['blocks'][0]['vocabulary']
        first, second = list(vocabulary)[:2]
        vocabulary[first], vocabulary[second] = vocabulary[second], vocabulary[first]
    elif mutation == 'dataset':
        for audit in (candidate['lineageAudit'], candidate['evidence']['document']['lineageAudit']):
            audit['datasetCanonicalSha256'] = 'f' * 64
    elif mutation == 'count':
        candidate['evidence']['document']['metrics']['classCounts']['human'] += 1
    elif mutation == 'type':
        metrics = candidate['evidence']['document']['metrics']
        metrics['total'] = float(metrics['total'])
    elif mutation == 'structure':
        candidate['eligibility']['extra'] = None
    else:
        candidate['lineageAudit']['splits']['test']['canonicalRowsSha256'] = 'f' * 64
        candidate['evidence']['document']['lineageAudit']['splits']['test']['canonicalRowsSha256'] = 'f' * 64
    report = compare(tmp_path, artifact, rebind(candidate))
    assert report['passed'] is False
    assert report['checks']['structureAndValuesEqualWithinTolerance'] is False


@pytest.mark.parametrize('path', [
    ('artifactSha256',), ('modelVersion',),
    ('evidence', 'document', 'modelSha256'),
    ('evidence', 'document', 'thresholdsSha256'),
    ('evidence', 'document', 'calibrationSha256'),
    ('evidence', 'document', 'lineageAudit', 'bindingSha256'),
])
def test_even_identical_artifacts_with_invalid_ignored_bindings_are_rejected(tmp_path, artifact, path):
    parent = artifact
    for key in path[:-1]:
        parent = parent[key]
    parent[path[-1]] = 'invalid-binding'
    if path != ('artifactSha256',):
        artifact['artifactSha256'] = digest({key: value for key, value in artifact.items()
                                             if key != 'artifactSha256'})
    report = compare(tmp_path, artifact, artifact)
    assert report['passed'] is False
    assert report['checks']['referenceIntegrity'] is False
    assert report['checks']['candidateIntegrity'] is False


def test_tolerated_numeric_change_cannot_change_gate_reasons(tmp_path, artifact):
    intervals = artifact['evidence']['document']['metrics']['intervals95']
    intervals['falsePositiveRate'][1] = 0.05
    rebind(artifact)
    candidate = copy.deepcopy(artifact)
    candidate['evidence']['document']['metrics']['intervals95']['falsePositiveRate'][1] = math.nextafter(0.05, math.inf)
    report = compare(tmp_path, artifact, rebind(candidate))
    assert report['passed'] is False
    assert report['checks']['structureAndValuesEqualWithinTolerance'] is True
    assert report['checks']['gatesEqual'] is False


def test_tolerated_numeric_change_cannot_change_prediction_category(tmp_path, artifact):
    artifact['evidence']['document']['predictions'][0]['score'] = artifact['documentThresholds']['aiMin']
    rebind(artifact)
    candidate = copy.deepcopy(artifact)
    candidate['evidence']['document']['predictions'][0]['score'] = math.nextafter(candidate['documentThresholds']['aiMin'], -math.inf)
    report = compare(tmp_path, artifact, rebind(candidate))
    assert report['passed'] is False
    assert report['checks']['predictionCategoriesEqual'] is False


def test_calibration_fitting_dataset_hash_is_never_ignored(tmp_path, artifact):
    artifact['documentCalibration'] = {'method': 'platt', 'slope': 1.0, 'intercept': 0.0,
        'fitting': {'split': 'calibration', 'classCounts': {'human': 2, 'ai': 2},
                    'scoredRowsSha256': 'a' * 64}}
    rebind(artifact)
    candidate = copy.deepcopy(artifact)
    candidate['documentCalibration']['fitting']['scoredRowsSha256'] = 'b' * 64
    report = compare(tmp_path, artifact, rebind(candidate))
    assert report['passed'] is False
    assert report['checks']['structureAndValuesEqualWithinTolerance'] is False
