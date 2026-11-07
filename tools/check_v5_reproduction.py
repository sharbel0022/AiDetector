"""Compare V5 training artifacts across platforms without weakening integrity.

Finite floats may differ by at most 1e-12 + 1e-12 * max(abs(a), abs(b)).
Types, structure, integers, strings, vocabulary, data identities and gates must
match exactly. Only the enumerated derived identities below are exempt from
cross-file equality; each is independently recomputed before comparison.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai.detector.linear import calibrated_probability, digest, finite
from ai.detector.runtime import load_artifact

ABSOLUTE_TOLERANCE = 1e-12
RELATIVE_TOLERANCE = 1e-12
DERIVED_PATHS = {('artifactSha256',), ('modelVersion',)} | {
    ('evidence', level, key)
    for level in ('document', 'segment')
    for key in ('modelSha256', 'thresholdsSha256', 'calibrationSha256')
} | {('evidence', level, 'lineageAudit', 'bindingSha256')
     for level in ('document', 'segment')}


def pointer(path):
    return '/' + '/'.join(str(item).replace('~', '~0').replace('/', '~1') for item in path)


def _require_equal(actual, expected, path):
    if type(actual) is not type(expected) or actual != expected:
        raise ValueError(f'Invalid derived identity at {pointer(path)}')


def _load_validated(path):
    # The runtime enforces bounded JSON, unique keys, safe numerical models and
    # the canonical artifact hash. Its release gates may legitimately be false.
    artifact, gates = load_artifact(path)
    dataset_hash = artifact['lineageAudit']['datasetCanonicalSha256']
    if not isinstance(dataset_hash, str) or not re.fullmatch(r'[0-9a-f]{64}', dataset_hash):
        raise ValueError('Invalid dataset identity')
    version = 'textlab-v5-' + digest(artifact['documentModel'])[:12] + '-' + dataset_hash[:8]
    _require_equal(artifact['modelVersion'], version, ('modelVersion',))
    for level in ('document', 'segment'):
        model = artifact[level + 'Model']
        thresholds = artifact[level + 'Thresholds']
        calibration = artifact[level + 'Calibration']
        if model is None:
            if thresholds is not None or calibration is not None or level in artifact['evidence']:
                raise ValueError(f'Unexpected {level} evidence without its model')
            continue
        evidence = artifact['evidence'][level]
        prefix = ('evidence', level)
        _require_equal(evidence['modelSha256'], digest(model), prefix + ('modelSha256',))
        if (not isinstance(thresholds, dict) or
                not finite(thresholds.get('aiMin')) or not finite(thresholds.get('humanMax')) or
                thresholds['humanMax'] >= thresholds['aiMin'] or
                thresholds.get('selectionSplit') != 'validation'):
            raise ValueError(f'Invalid {level} thresholds')
        _require_equal(evidence['thresholdsSha256'], digest(thresholds), prefix + ('thresholdsSha256',))
        if calibration is not None:
            calibrated_probability(calibration, 0.0)
        _require_equal(evidence['calibrationSha256'], digest(calibration) if calibration is not None else None,
                       prefix + ('calibrationSha256',))
        _require_equal(evidence['lineageAudit']['bindingSha256'],
                       digest({key: value for key, value in evidence.items() if key != 'lineageAudit'}),
                       prefix + ('lineageAudit', 'bindingSha256'))
    summary = {'path': str(path), 'fileSha256': hashlib.sha256(Path(path).read_bytes()).hexdigest(),
               'artifactSha256': artifact['artifactSha256'], 'modelVersion': artifact['modelVersion'],
               'documentModelSha256': digest(artifact['documentModel']),
               'segmentModelSha256': digest(artifact['segmentModel']) if artifact['segmentModel'] is not None else None,
               'gates': gates}
    return artifact, summary


def _prediction_categories(artifact):
    result = {}
    for level in ('document', 'segment'):
        if artifact[level + 'Model'] is None:
            continue
        thresholds = artifact[level + 'Thresholds']
        result[level] = []
        for prediction in artifact['evidence'][level]['predictions']:
            score = prediction['score']
            if score is not None and not finite(score):
                raise ValueError(f'Invalid {level} prediction score')
            category = ('unassessed' if score is None else 'ai_like' if score >= thresholds['aiMin']
                        else 'human_like' if score <= thresholds['humanMax'] else 'uncertain')
            result[level].append((prediction['source_id'], category))
    return result


def compare_artifacts(reference_path, candidate_path):
    stats = {'comparedFloatCount': 0, 'changedFloatCount': 0,
             'maximumAbsoluteDifference': 0.0, 'maximumAbsoluteDifferencePath': None,
             'maximumRelativeDifference': 0.0, 'maximumRelativeDifferencePath': None}
    checks = {'referenceIntegrity': False, 'candidateIntegrity': False,
              'structureAndValuesEqualWithinTolerance': False, 'gatesEqual': False,
              'predictionCategoriesEqual': False}
    report = {'schemaVersion': 'textlab-v5-reproduction-check-1', 'passed': False,
              'tolerance': {'absolute': ABSOLUTE_TOLERANCE, 'relative': RELATIVE_TOLERANCE,
                            'rule': 'abs(a-b) <= absolute + relative * max(abs(a), abs(b))'},
              'independentlyValidatedDerivedPaths': sorted(pointer(path) for path in DERIVED_PATHS),
              'checks': checks, 'numericComparison': stats, 'differenceCount': 0, 'errors': []}
    artifacts = {}
    for name, path in (('reference', reference_path), ('candidate', candidate_path)):
        try:
            artifacts[name], report[name] = _load_validated(path)
            checks[name + 'Integrity'] = True
        except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError) as error:
            report['errors'].append({'artifact': name, 'error': str(error)})
    if len(artifacts) != 2:
        return report

    def mismatch(path, reason):
        report['differenceCount'] += 1
        if len(report['errors']) < 20:
            report['errors'].append({'path': pointer(path), 'error': reason})

    def compare(left, right, path=()):
        if type(left) is not type(right):
            mismatch(path, 'JSON types differ')
        elif isinstance(left, dict):
            if left.keys() != right.keys():
                mismatch(path, 'Object keys differ')
            for key in sorted(left.keys() & right.keys()):
                compare(left[key], right[key], path + (key,))
        elif isinstance(left, list):
            if len(left) != len(right):
                mismatch(path, 'Array lengths differ')
            for index, (a, b) in enumerate(zip(left, right)):
                compare(a, b, path + (index,))
        elif isinstance(left, float):
            if not math.isfinite(left) or not math.isfinite(right):
                mismatch(path, 'Nonfinite number')
                return
            stats['comparedFloatCount'] += 1
            difference = abs(left - right)
            scale = max(abs(left), abs(right))
            relative = difference / scale if scale else 0.0
            if difference:
                stats['changedFloatCount'] += 1
            if difference > stats['maximumAbsoluteDifference']:
                stats['maximumAbsoluteDifference'] = difference
                stats['maximumAbsoluteDifferencePath'] = pointer(path)
            if relative > stats['maximumRelativeDifference']:
                stats['maximumRelativeDifference'] = relative
                stats['maximumRelativeDifferencePath'] = pointer(path)
            if difference > ABSOLUTE_TOLERANCE + RELATIVE_TOLERANCE * scale:
                mismatch(path, 'Float difference exceeds tolerance')
        elif path not in DERIVED_PATHS and left != right:
            mismatch(path, 'Exact value differs')

    compare(artifacts['reference'], artifacts['candidate'])
    checks['structureAndValuesEqualWithinTolerance'] = report['differenceCount'] == 0
    checks['gatesEqual'] = report['reference']['gates'] == report['candidate']['gates']
    try:
        checks['predictionCategoriesEqual'] = (_prediction_categories(artifacts['reference']) ==
                                               _prediction_categories(artifacts['candidate']))
    except (ValueError, TypeError, KeyError) as error:
        report['errors'].append({'error': str(error)})
    for key in ('gatesEqual', 'predictionCategoriesEqual'):
        if not checks[key]:
            report['errors'].append({'error': key + ' failed'})
    report['passed'] = all(checks.values())
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference', type=Path)
    parser.add_argument('candidate', type=Path)
    args = parser.parse_args(argv)
    report = compare_artifacts(args.reference, args.candidate)
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
