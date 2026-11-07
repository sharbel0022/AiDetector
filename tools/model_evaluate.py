"""JSON-only scoring/evaluation for the offline experimental detector.

Margins are ranking scores, never calibrated authorship probabilities. This module
uses only the Python standard library; the strict dataset/eligibility audit calls
the same Node implementation as the descriptive benchmark.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = 'textlab-char-tfidf-logreg-v2'
PROVENANCE_SCHEMA = 'textlab-development-provenance-v1'
IDENTITY_FIELDS = {'source_id': 'sourceIds', 'document_id': 'documentIds', 'author_id': 'authors', 'source_group_id': 'sourceGroups'}
CALIBRATION = {'available': False, 'reason': 'No separate group-disjoint calibration corpus; logistic margins are not authorship probabilities.'}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def sha256(value):
    return hashlib.sha256(value if isinstance(value, bytes) else value.encode('utf-8')).hexdigest()


def load_records(path):
    path = Path(path)
    if not path.is_file():
        raise ValueError(f'Dataset file does not exist: {path}')
    if path.stat().st_size > 10_000_000:
        raise ValueError('Dataset exceeds 10 MB')
    try:
        return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    except (ValueError, UnicodeError) as error:
        raise ValueError(f'Invalid UTF-8 JSONL dataset: {error}') from error


def audit_records(records, fixture=False):
    script = """
import fs from 'node:fs';
import {validateDataset} from './tools/evaluate.mjs';
import {analyzeText} from './sites/src/analyzer.mjs';
try {
  const {records, fixture} = JSON.parse(fs.readFileSync(0, 'utf8'));
  const dataset = validateDataset(records, {fixture});
  const analyses = records.map(row => {
    const a = analyzeText(row.text, row.language);
    return {source_id: row.source_id, styleScore: a.styleIndex, words: a.wordCount,
      eligible: a.styleIndex !== null, abstentionReasons: a.abstentionReasons};
  });
  console.log(JSON.stringify({dataset, analyses, node: process.version}));
} catch(error) { console.error(error.message); process.exitCode = 1; }
"""
    try:
        result = subprocess.run(['node', '--input-type=module', '-e', script], input=canonical({'records': records, 'fixture': fixture}),
                                cwd=ROOT, text=True, encoding='utf-8', capture_output=True, timeout=120, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError(f'Node dataset audit failed: {error}') from error
    if result.returncode:
        raise ValueError(f'Node dataset audit rejected corpus: {result.stderr.strip()}')
    return json.loads(result.stdout)


def _finite(number):
    return isinstance(number, (int, float)) and not isinstance(number, bool) and math.isfinite(number)


def validate_weights(artifact):
    if not isinstance(artifact, dict) or artifact.get('schemaVersion') != SCHEMA:
        raise ValueError('Legacy/unsupported JSON model schema: audited development provenance is required')
    vocabulary = artifact.get('vocabulary')
    if not isinstance(vocabulary, dict) or not 1 <= len(vocabulary) <= 20_000:
        raise ValueError('Invalid vocabulary size')
    if any(not isinstance(key, str) or not 3 <= len(key) <= 5 for key in vocabulary):
        raise ValueError('Invalid character ngram')
    if any(not isinstance(index, int) or isinstance(index, bool) for index in vocabulary.values()) or set(vocabulary.values()) != set(range(len(vocabulary))):
        raise ValueError('Vocabulary indices must be unique and contiguous')
    for field in ['idf', 'coefficients']:
        values = artifact.get(field)
        if not isinstance(values, list) or len(values) != len(vocabulary):
            raise ValueError(f'{field} length does not match vocabulary')
        if any(not _finite(value) for value in values):
            raise ValueError(f'{field} must contain finite numbers')
    if any(value <= 0 for value in artifact['idf']) or not _finite(artifact.get('intercept')):
        raise ValueError('Invalid finite intercept or positive idf weights')
    if artifact.get('scoreSemantics') != 'uncalibrated_logistic_margin' or artifact.get('calibration', {}).get('available') is not False:
        raise ValueError('Unsupported score or calibration semantics')
    return artifact


def normalized_text_hash(text):
    """Fingerprint NFKC/lowercase lexical tokens independently of punctuation."""
    tokens, token = [], []
    for character in unicodedata.normalize('NFKC', text).lower():
        category = unicodedata.category(character)[0]
        if category in ('L', 'N') or (category == 'M' and token):
            token.append(character)
        elif token:
            tokens.append(''.join(token))
            token = []
    if token:
        tokens.append(''.join(token))
    return sha256(' '.join(tokens))


def development_footprint(rows, split):
    if not rows or any(row.get('split') != split for row in rows):
        raise ValueError(f'Development provenance requires only {split} rows')
    footprint = {'split': split, 'rowCount': len(rows), 'rowsSha256': sha256(canonical(rows)),
                 'normalizedTextSha256': sorted({normalized_text_hash(row['text']) for row in rows})}
    for field, key in IDENTITY_FIELDS.items():
        if any(not isinstance(row.get(field), str) or not row[field].strip() for row in rows):
            raise ValueError(f'Development provenance missing {field}')
        footprint[key] = sorted({row[field] for row in rows})
    return footprint


def _audit_binding(artifact):
    provenance = {key: value for key, value in artifact['developmentProvenance'].items() if key != 'bindingSha256'}
    weights = {key: artifact[key] for key in ('vocabulary', 'idf', 'coefficients', 'intercept')}
    return sha256(canonical({'schemaVersion': artifact['schemaVersion'], 'developmentProvenance': provenance,
                             'training': artifact['training'], 'selection': artifact['selection'],
                             'datasetSha256': artifact['datasetSha256'], 'configSha256': artifact['configSha256'],
                             'weightsSha256': sha256(canonical(weights))}))


def attach_development_provenance(artifact, training_rows, validation_rows):
    """Bind the quarantine of both development stages to weights/config/threshold.

    This checksum detects corruption; it is not an authenticated signature or an
    independent verification of source identities supplied by the corpus.
    """
    artifact['developmentProvenance'] = {'schemaVersion': PROVENANCE_SCHEMA,
                                          'fitting': development_footprint(training_rows, 'train'),
                                          'thresholdSelection': development_footprint(validation_rows, 'validation')}
    artifact['developmentProvenance']['bindingSha256'] = _audit_binding(artifact)
    return validate_artifact(artifact)


def validate_artifact(artifact):
    validate_weights(artifact)
    provenance = artifact.get('developmentProvenance')
    if not isinstance(provenance, dict) or provenance.get('schemaVersion') != PROVENANCE_SCHEMA:
        raise ValueError('Missing or unsupported development provenance audit')
    try:
        if artifact['configSha256'] != sha256(canonical(artifact['config'])):
            raise ValueError('Invalid audit config binding')
        if not re.fullmatch(r'[0-9a-f]{64}', artifact['datasetSha256']):
            raise ValueError('Invalid audit dataset hash')
        if artifact['selection']['selectionSplit'] != 'validation' or not _finite(artifact['selection']['threshold']):
            raise ValueError('Invalid threshold-selection provenance')
        for stage, split in [('fitting', 'train'), ('thresholdSelection', 'validation')]:
            footprint = provenance[stage]
            count = footprint['rowCount']
            if not isinstance(count, int) or isinstance(count, bool) or count < 1 or footprint['split'] != split:
                raise ValueError('Invalid development provenance row count/split')
            for field in (*IDENTITY_FIELDS.values(), 'normalizedTextSha256'):
                values = footprint[field]
                if not isinstance(values, list) or not values or len(values) > count or any(not isinstance(value, str) or not value.strip() for value in values) or values != sorted(set(values)):
                    raise ValueError(f'Invalid development provenance {field}')
            if len(footprint['sourceIds']) != count:
                raise ValueError('Invalid development provenance sourceIds/count')
            if not re.fullmatch(r'[0-9a-f]{64}', footprint['rowsSha256']) or any(not re.fullmatch(r'[0-9a-f]{64}', value) for value in footprint['normalizedTextSha256']):
                raise ValueError('Invalid development provenance text/row hashes')
        if provenance.get('bindingSha256') != _audit_binding(artifact):
            raise ValueError('Development provenance binding mismatch: artifact was changed')
    except (KeyError, TypeError) as error:
        raise ValueError('Incomplete development provenance audit') from error
    return artifact


def assert_unseen_test(artifact, records):
    validate_artifact(artifact)
    for stage in ('fitting', 'thresholdSelection'):
        footprint = artifact['developmentProvenance'][stage]
        for row in records:
            if row.get('split') != 'test':
                continue
            for field, key in IDENTITY_FIELDS.items():
                if not isinstance(row.get(field), str) or not row[field].strip():
                    raise ValueError(f'Missing test {field}')
                if row[field] in footprint[key]:
                    raise ValueError(f'Test {field} overlaps {stage} development provenance: {row[field]}')
            if normalized_text_hash(row['text']) in footprint['normalizedTextSha256']:
                raise ValueError(f'Test text overlaps {stage} development provenance')


def score_text(artifact, text):
    """Reproduce sklearn char3–5/sublinear-TF/L2 scoring without pickle or sklearn."""
    # Fitting must score validation before its development audit can be sealed.
    # This weights-only primitive cannot produce a held-out evaluation report.
    validate_weights(artifact)
    if not isinstance(text, str) or len(text) > 12_000:
        raise ValueError('Text must be a string of at most 12000 characters')
    normalized = re.sub(r'\s\s+', ' ', text.lower())
    counts = Counter(normalized[i:i + size] for size in (3, 4, 5) for i in range(len(normalized) - size + 1))
    features = [(artifact['vocabulary'][key], 1 + math.log(count)) for key, count in counts.items() if key in artifact['vocabulary']]
    weighted = [(index, value * artifact['idf'][index]) for index, value in features]
    norm = math.sqrt(math.fsum(value * value for _, value in weighted))
    # A zero-vector gets the intercept, matching sklearn; the report explicitly
    # marks a zero-vector as an abstention rather than using this fallback.
    return artifact['intercept'] + (math.fsum(artifact['coefficients'][index] * value for index, value in weighted) / norm if norm else 0)


def has_features(artifact, text):
    normalized = re.sub(r'\s\s+', ' ', text.lower())
    return any(normalized[i:i + size] in artifact['vocabulary'] for size in (3, 4, 5) for i in range(len(normalized) - size + 1))


def ratio(a, b):
    return a / b if b else None


def wilson(successes, n):
    if not n:
        return None
    z = 1.959963984540054
    p = successes / n
    denominator = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denominator
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return {'lower': max(0, center - margin), 'upper': min(1, center + margin), 'n': n,
            'method': 'Wilson observation-level; repeated source groups violate independence and can make this interval too narrow'}


def summarize(rows, threshold):
    if not _finite(threshold):
        raise ValueError('Threshold must be finite')
    confusion = dict(tp=0, fp=0, tn=0, fn=0)
    abstentions = dict(human=0, ai=0, **{'ai-edited': 0})
    edited = dict(total=0, assessed=0, flagged=0)
    for row in rows:
        label, score = row['label'], row['score']
        if label not in abstentions or (score is not None and not _finite(score)):
            raise ValueError('Invalid label or nonfinite score')
        if label == 'ai-edited':
            edited['total'] += 1
        if score is None:
            abstentions[label] += 1
        elif label == 'ai-edited':
            edited['assessed'] += 1
            edited['flagged'] += score >= threshold
        else:
            confusion[('tp' if score >= threshold else 'fn') if label == 'ai' else ('fp' if score >= threshold else 'tn')] += 1
    tp, fp, tn, fn = (confusion[key] for key in ['tp', 'fp', 'tn', 'fn'])
    assessed = len(rows) - sum(abstentions.values())
    positives = [row['score'] for row in rows if row['label'] == 'ai' and row['score'] is not None]
    negatives = [row['score'] for row in rows if row['label'] == 'human' and row['score'] is not None]
    auroc = (sum((a > h) + .5 * (a == h) for a in positives for h in negatives) / (len(positives) * len(negatives))) if positives and negatives else None
    return {'total': len(rows), 'assessed': assessed, 'binaryAssessed': tp + fp + tn + fn,
            'abstained': sum(abstentions.values()), 'abstentionsByLabel': abstentions, 'coverage': ratio(assessed, len(rows)),
            'threshold': threshold, 'confusion': confusion,
            'humanFalsePositives': {'count': fp, 'assessedDenominator': fp + tn, 'allHumanDenominator': fp + tn + abstentions['human']},
            'accuracyAssessed': ratio(tp + tn, tp + fp + tn + fn), 'precision': ratio(tp, tp + fp),
            'recallAssessed': ratio(tp, tp + fn), 'recallAllAI': ratio(tp, tp + fn + abstentions['ai']),
            'falsePositiveRate': ratio(fp, fp + tn), 'falseNegativeRate': ratio(fn, tp + fn),
            'f1': ratio(2 * tp, 2 * tp + fp + fn), 'auroc': auroc, 'aiEdited': edited,
            'intervals95': {'falsePositiveRate': wilson(fp, fp + tn), 'recallAssessed': wilson(tp, tp + fn),
                            'accuracyAssessed': wilson(tp + tn, tp + fp + tn + fn), 'coverage': wilson(assessed, len(rows))},
            'calibration': CALIBRATION,
            'evidenceWarning': 'Exploratory corpus only. Observation-level intervals ignore source dependence; no production reliability claim.'}


def select_threshold(rows, max_human_fpr=.05):
    if not rows or any(row.get('split') != 'validation' for row in rows):
        raise ValueError('Threshold selection requires only the validation split')
    if not _finite(max_human_fpr) or not 0 <= max_human_fpr < 1:
        raise ValueError('max_human_fpr must be in [0, 1)')
    binary = [row for row in rows if row['label'] in ('human', 'ai') and row['score'] is not None]
    if any(not any(row['label'] == label for row in binary) for label in ('human', 'ai')):
        raise ValueError('Threshold selection needs assessed human and ai validation rows')
    scores = sorted({row['score'] for row in binary})
    candidates = scores + [math.nextafter(scores[-1], math.inf)]
    choices = []
    for threshold in candidates:
        metrics = summarize(rows, threshold)
        if metrics['falsePositiveRate'] <= max_human_fpr:
            # Lowest threshold among equal operating results avoids an arbitrary
            # one-class ceiling; the nextafter candidate permits no flags.
            choices.append((metrics['recallAllAI'], -metrics['falsePositiveRate'], -threshold, threshold, metrics))
    _, _, _, threshold, metrics = max(choices, key=lambda choice: choice[:3])
    return {'threshold': threshold, 'selectionSplit': 'validation',
            'objective': 'maximize recallAllAI subject to observed validation human FPR <= configured maximum',
            'maxObservedHumanFPR': max_human_fpr, 'tieBreak': 'lower observed human FPR, then lower threshold',
            'metrics': metrics, 'warning': 'The FPR constraint is empirical, not a statistical upper bound. Small validation groups cannot establish a low population FPR.'}


def heldout_report(rows, threshold):
    test = [row for row in rows if row.get('split') == 'test']
    if not test:
        raise ValueError('A held-out test split is mandatory')
    def slices(key):
        values = sorted({key(row) for row in test})
        return {value: summarize([row for row in test if key(row) == value], threshold) for value in values}
    human = [row for row in test if row['label'] == 'human']
    groups = sorted({row['source_group_id'] for row in human})
    assessed_groups = [group for group in groups if any(row['source_group_id'] == group and row['score'] is not None for row in human)]
    flagged_groups = [group for group in assessed_groups if any(row['source_group_id'] == group and row['score'] is not None and row['score'] >= threshold for row in human)]
    return {'evaluatedSplit': 'test', 'overall': summarize(test, threshold),
            'byLanguage': slices(lambda row: row['language']), 'byGenre': slices(lambda row: row['genre']),
            'byLength': slices(lambda row: 'short' if row['words'] < 80 else 'medium' if row['words'] < 300 else 'long'),
            'byModel': slices(lambda row: row['model']),
            'testSourceGroups': len({row['source_group_id'] for row in test}),
            'humanSourceGroups': {'total': len(groups), 'assessed': len(assessed_groups), 'withAnyFalsePositive': len(flagged_groups),
                                  'rateWithAnyFalsePositive': ratio(len(flagged_groups), len(assessed_groups)),
                                  'interval95': wilson(len(flagged_groups), len(assessed_groups)),
                                  'estimand': 'Fraction of source groups with at least one assessed human excerpt flagged; distinct from excerpt-level FPR.',
                                  'warning': 'Convenience sample of source groups. Interval assumes independent exchangeable groups; no population guarantee.'},
            'predictions': test}


def score_records(records, analyses, artifact):
    result = []
    for row, analysis in zip(records, analyses, strict=True):
        if row['source_id'] != analysis['source_id']:
            raise ValueError('Audit rows are not aligned')
        reasons = list(analysis['abstentionReasons'])
        if not has_features(artifact, row['text']):
            reasons.append('out_of_vocabulary')
        result.append({key: row.get(key) for key in ['source_id', 'split', 'label', 'language', 'genre', 'source_group_id', 'author_id', 'document_id']} |
                      {'model': row.get('model') or '(human)', 'words': analysis['words'],
                       'score': None if reasons else score_text(artifact, row['text']), 'abstentionReasons': reasons})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', required=True)
    parser.add_argument('--model', required=True)
    parser.add_argument('--fixture', action='store_true')
    args = parser.parse_args()
    try:
        path = Path(args.model)
        if path.stat().st_size > 10_000_000:
            raise ValueError('Model exceeds 10 MB')
        artifact = validate_artifact(json.loads(path.read_text(encoding='utf-8')))
        threshold = artifact.get('selection', {}).get('threshold')
        if not _finite(threshold):
            raise ValueError('Frozen validation threshold is missing')
        records = load_records(args.data)
        audit = audit_records(records, fixture=args.fixture)
        assert_unseen_test(artifact, records)
        report = heldout_report(score_records(records, audit['analyses'], artifact), threshold)
        report.update({'modelSha256': sha256(path.read_bytes()), 'datasetSha256': sha256(Path(args.data).read_bytes()),
                       'status': 'exploratory-pilot-not-production', 'calibration': CALIBRATION})
        print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    except (ValueError, OSError, KeyError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
