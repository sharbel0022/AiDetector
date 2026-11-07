"""Offline V4 comparison: train-only fit, validation-only choice, reused diagnostics.

The existing audited character baseline is immutable. Two fixed alternatives use
word TF-IDF or combined word/character TF-IDF with the same logistic classifier.
All test results are historical development diagnostics, not a new holdout. The
known modern-human failures are replayed only after selection, for the frozen
baseline alone. No fitted model is exported or connected to the application.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import importlib.metadata
import json
from pathlib import Path
import platform
import sys
import warnings

if __package__:
    from . import model_evaluate as evaluation
    from . import train_baseline
else:
    import model_evaluate as evaluation
    import train_baseline

ROOT = evaluation.ROOT
BASELINE = 'audited_char_3_5'
ALTERNATIVES = ('word_1_2', 'word_char_1_2_3_5')
CANDIDATE_ORDER = (BASELINE, *ALTERNATIVES)
MAX_VALIDATION_FPR = .05
WORD_CONFIG = {'analyzer': 'word', 'ngram_range': [1, 2], 'token_pattern': r'(?u)\b\w\w+\b', 'max_features': 10_000}
CHAR_CONFIG = {'analyzer': 'char', 'ngram_range': [3, 5], 'max_features': 20_000}
COMMON_CONFIG = {'lowercase': True, 'min_df': 2, 'sublinear_tf': True, 'norm': 'l2', 'smooth_idf': True}
CLASSIFIER_CONFIG = {'C': 1.0, 'solver': 'liblinear', 'class_weight': 'balanced', 'random_state': 42, 'max_iter': 1000}


@dataclass
class FittedCandidate:
    name: str
    features: object
    classifier: object
    vectorizers: list
    config: dict
    training: dict


def fit_candidate(name, rows):
    """Only this function fits alternatives; it rejects every non-training row."""
    if name not in ALTERNATIVES:
        raise ValueError(f'Unknown fixed alternative: {name}')
    if not rows or any(row.get('split') != 'train' for row in rows):
        raise ValueError('Fitting requires only the train split')
    rows = train_baseline.check_class_counts(rows, 'train')
    from sklearn.exceptions import ConvergenceWarning
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import FeatureUnion, Pipeline
    from sklearn.preprocessing import Normalizer

    configs = [WORD_CONFIG] if name == 'word_1_2' else [WORD_CONFIG, CHAR_CONFIG]
    vectorizers = []
    for config in configs:
        options = {**COMMON_CONFIG, **config, 'ngram_range': tuple(config['ngram_range'])}
        vectorizers.append((config['analyzer'], TfidfVectorizer(**options)))
    if len(vectorizers) == 1:
        features = vectorizers[0][1]
    else:
        # Equal block weight, then global L2 normalization keeps regularization
        # comparable with either individual L2-normalized representation.
        features = Pipeline([('union', FeatureUnion(vectorizers)), ('normalize', Normalizer(norm='l2'))])
    matrix = features.fit_transform([row['text'] for row in rows])
    classifier = LogisticRegression(**CLASSIFIER_CONFIG)
    with warnings.catch_warnings():
        warnings.simplefilter('error', ConvergenceWarning)
        classifier.fit(matrix, [int(row['label'] == 'ai') for row in rows])
    return FittedCandidate(
        name, features, classifier, vectorizers,
        {'vectorizers': [{**COMMON_CONFIG, **config} for config in configs],
         'combination': 'equal-block-weights-then-global-l2' if len(configs) > 1 else 'single-l2-block',
         'classifier': {'name': 'LogisticRegression', **CLASSIFIER_CONFIG}},
        evaluation.development_footprint(rows, 'train'),
    )


def fitted_details(candidate):
    weights = {
        'vectorizers': [{
            'name': name, 'vocabulary': {term: int(index) for term, index in vectorizer.vocabulary_.items()},
            'idf': vectorizer.idf_.tolist(),
        } for name, vectorizer in candidate.vectorizers],
        'coefficients': candidate.classifier.coef_[0].tolist(),
        'intercept': float(candidate.classifier.intercept_[0]),
    }
    return {'name': candidate.name, 'config': candidate.config, 'training': candidate.training,
            'featureCount': int(candidate.classifier.coef_.shape[1]),
            'weightsSha256': evaluation.sha256(evaluation.canonical(weights)),
            'scoreSemantics': 'uncalibrated_logistic_margin'}


def score_candidate(candidate, records, analyses):
    matrix = candidate.features.transform([row['text'] for row in records])
    margins = candidate.classifier.decision_function(matrix)
    populated = matrix.getnnz(axis=1)
    results = []
    for row, analysis, margin, count in zip(records, analyses, margins, populated, strict=True):
        if row['source_id'] != analysis['source_id']:
            raise ValueError('Audit rows are not aligned')
        reasons = list(analysis['abstentionReasons'])
        if not count:
            reasons.append('out_of_vocabulary')
        results.append({key: row.get(key) for key in ('source_id', 'split', 'label', 'language', 'genre', 'source_group_id', 'author_id', 'document_id')} |
                       {'model': row.get('model') or '(human)', 'words': analysis['words'],
                        'score': None if reasons else float(margin), 'abstentionReasons': reasons})
    return results


def choose_candidate(candidates):
    """Choose on validation operating results; never compare unscaled margins."""
    if not candidates or len({item['name'] for item in candidates}) != len(candidates):
        raise ValueError('Candidate names must be nonempty and unique')
    for item in candidates:
        if item['name'] not in CANDIDATE_ORDER or item['validation'].get('selectionSplit') != 'validation':
            raise ValueError('Candidate selection requires only validation results')
    eligible = [item for item in candidates if item['validation']['metrics']['falsePositiveRate'] is not None
                and item['validation']['metrics']['falsePositiveRate'] <= MAX_VALIDATION_FPR]
    if not eligible:
        raise ValueError('No candidate satisfies the observed validation human FPR constraint')
    chosen = max(eligible, key=lambda item: (
        item['validation']['metrics']['recallAllAI'],
        -item['validation']['metrics']['falsePositiveRate'],
        item['validation']['metrics']['coverage'],
        -CANDIDATE_ORDER.index(item['name']),
    ))
    return {
        'name': chosen['name'], 'selectionSplit': 'validation', 'maxObservedHumanFPR': MAX_VALIDATION_FPR,
        'objective': 'maximize recallAllAI subject to observed validation human FPR <= 0.05',
        'tieBreak': ['lower observed human FPR', 'higher coverage', 'predeclared preference: existing baseline, word, combined'],
        'predeclaredCandidateOrder': list(CANDIDATE_ORDER), 'testUsedForSelection': False,
        'modernHumanUsedForSelection': False, 'productionApproved': False,
        'warning': 'This small reused validation set cannot establish low population FPR or a generalizable winning model.',
    }


def _historical_diagnostic(scored, threshold):
    return {**evaluation.heldout_report(scored, threshold),
            'evidenceUse': 'historical-development-diagnostic', 'independentEvidence': False,
            'usedForSelection': False,
            'warning': 'The existing test split was already inspected in V3. These are reused historical diagnostics, not new independent results.'}


def compare_run(records, artifact, fixture=False):
    evaluation.validate_artifact(artifact)
    pairs_by_split = {split: [row for row in records if row['split'] == split] for split in ('train', 'validation', 'test')}
    # The frozen baseline may only be compared against its actual development
    # corpus. Test text is deliberately excluded from this equality check.
    for stage, split in [('fitting', 'train'), ('thresholdSelection', 'validation')]:
        if evaluation.development_footprint(pairs_by_split[split], split) != artifact['developmentProvenance'][stage]:
            raise ValueError(f'Frozen baseline {stage} provenance differs from comparison corpus')
    audit = evaluation.audit_records(records, fixture=fixture)
    evaluation.assert_unseen_test(artifact, records)
    pairs = list(zip(records, audit['analyses'], strict=True))
    train = [row for row, analysis in pairs if row['split'] == 'train' and analysis['eligible']]
    validation = [row for row, _ in pairs if row['split'] == 'validation']
    validation_analyses = [analysis for row, analysis in pairs if row['split'] == 'validation']
    train_baseline.check_class_counts(train, 'train')
    train_baseline.check_class_counts([row for row, analysis in pairs if row['split'] == 'validation' and analysis['eligible']], 'validation')
    threshold = artifact['selection']['threshold']
    baseline_validation = evaluation.score_records(validation, validation_analyses, artifact)
    baseline_weights = {key: artifact[key] for key in ('vocabulary', 'idf', 'coefficients', 'intercept')}
    candidates = [{
        'name': BASELINE, 'config': artifact['config'], 'training': artifact['developmentProvenance']['fitting'],
        'featureCount': len(artifact['vocabulary']), 'weightsSha256': evaluation.sha256(evaluation.canonical(baseline_weights)),
        'scoreSemantics': artifact['scoreSemantics'], 'source': 'existing-audited-frozen-artifact',
        'validation': {**artifact['selection'], 'metrics': evaluation.summarize(baseline_validation, threshold),
                       'thresholdSource': 'preserved-from-audited-artifact'},
    }]
    fitted = []
    for name in ALTERNATIVES:
        candidate = fit_candidate(name, train)
        scores = score_candidate(candidate, validation, validation_analyses)
        candidates.append({**fitted_details(candidate), 'source': 'train-only-fit',
                           'validation': evaluation.select_threshold(scores, MAX_VALIDATION_FPR)})
        fitted.append(candidate)
    # Freeze the winner and every threshold before any test margin is computed.
    selection = choose_candidate(candidates)
    test = [row for row, _ in pairs if row['split'] == 'test']
    test_analyses = [analysis for row, analysis in pairs if row['split'] == 'test']
    candidates[0]['historicalTestDiagnostics'] = _historical_diagnostic(evaluation.score_records(test, test_analyses, artifact), threshold)
    for candidate, details in zip(fitted, candidates[1:], strict=True):
        details['historicalTestDiagnostics'] = _historical_diagnostic(score_candidate(candidate, test, test_analyses), details['validation']['threshold'])
    return {
        'schemaVersion': 'textlab-offline-comparison-v4',
        'status': 'synthetic-engineering-fixture' if fixture else 'exploratory-historical-development-comparison',
        'qualityEvidence': False, 'productionApproved': False, 'calibration': evaluation.CALIBRATION,
        'datasetAudit': audit['dataset'], 'candidateSelection': selection, 'candidates': candidates,
        'protocol': {
            'fitSplit': 'train', 'thresholdSplit': 'validation', 'candidateSelectionSplit': 'validation',
            'evaluatedSplit': 'test', 'testEvidenceUse': 'historical-development-diagnostic',
            'testIsNewIndependentHoldout': False, 'modernHumanUse': 'frozen-baseline-regression-only-after-selection',
            'calibrationDecision': 'No calibration fitted: no separate group-disjoint calibration data; the reused validation corpus is too small.',
            'eligibility': 'Unchanged browser language, >=80 words, >=4 sentences; zero-vector rows abstain.',
        },
        'reproducibility': {
            'datasetCanonicalSha256': evaluation.sha256(evaluation.canonical(records)),
            'baselineArtifactCanonicalSha256': evaluation.sha256(evaluation.canonical(artifact)),
            'validationProvenance': evaluation.development_footprint(validation, 'validation'),
            'environment': {'python': platform.python_version(), 'node': audit['node'],
                            'dependencies': {name: importlib.metadata.version(name) for name in ('scikit-learn', 'numpy', 'scipy', 'joblib', 'threadpoolctl')}},
            'codeSha256': {str(path.relative_to(ROOT)): evaluation.sha256(path.read_bytes()) for path in (
                Path(__file__), Path(evaluation.__file__), Path(train_baseline.__file__),
                ROOT / 'tools/evaluate.mjs', ROOT / 'sites/src/analyzer.mjs')},
        },
        'limitations': [
            'Existing train, validation and test material has already informed development. No new independent quality claim is supported.',
            'Historical human books versus contemporary generated prose confound era, genre, spelling, topic and publisher with labels.',
            'Only two generator models and very few source families are represented. Excerpts within source groups are dependent.',
            'The validation FPR constraint is empirical. Observation-level Wilson intervals ignore source dependence.',
            'Logistic margins rank examples; they are not calibrated authorship probabilities. No production classifier is activated.',
            'Known modern-human regression examples must never tune feature choice, coefficients, threshold, or the candidate winner.',
            'Fresh, group-disjoint contemporary data and a frozen evaluation plan are required for a future independent assessment.',
        ],
    }


def modern_human_regression(artifact, records, historical):
    """Replay prior human errors only; no alternative model enters this function."""
    if not records or any(row.get('label') != 'human' or row.get('split') != 'test' for row in records):
        raise ValueError('Modern regression requires the existing human test rows')
    evaluation.validate_artifact(artifact)
    evaluation.assert_unseen_test(artifact, records)
    audit = evaluation.audit_records(records)
    scored = evaluation.score_records(records, audit['analyses'], artifact)
    threshold = artifact['selection']['threshold']
    old = historical['trained']
    if threshold != old['overall']['threshold']:
        raise ValueError('Modern regression threshold differs from historical frozen baseline')
    old_scores = {row['source_id']: row['score'] for row in old['predictions']}
    all_match = {row['source_id']: row['score'] for row in scored} == old_scores
    if not all_match:
        raise ValueError('Modern human margins differ from the preserved historical regression')
    result = _historical_diagnostic(scored, threshold)
    # A human-only corpus cannot estimate binary precision/recall/F1/AUROC;
    # retain FPR and coverage for every slice, without misleading binary metrics.
    summaries = [result['overall']]
    for slices in ('byLanguage', 'byGenre', 'byLength', 'byModel'):
        summaries.extend(result[slices].values())
    for metrics in summaries:
        metrics.update({key: None for key in ('accuracyAssessed', 'precision', 'recallAssessed', 'recallAllAI', 'falseNegativeRate', 'f1', 'auroc')})
        metrics['intervals95']['accuracyAssessed'] = None
    return {**result, 'baseline': BASELINE, 'allHistoricalMarginsMatch': all_match,
            'falsePositiveSourceIds': sorted(row['source_id'] for row in scored if row['score'] is not None and row['score'] >= threshold),
            'sourceAuditGap': historical.get('sourceAuditGap'),
            'warning': 'Previously inspected eight human-labelled Wikipedia excerpts. Human origin is historical-publication inference; bots and contributor identity are not excluded. Collection gaps and topic dependence remain. No tuning or new independent evidence.'}


def write_report(path, report):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as output:
        output.write(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', default='data/pilot/corpus.jsonl')
    parser.add_argument('--baseline', default='models/experimental/pilot-v1-audited/model.json')
    parser.add_argument('--modern-human', default='data/modern-human/corpus.jsonl')
    parser.add_argument('--modern-report', default='data/modern-human/report.json')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        if Path(args.output).exists():
            raise ValueError('Output path exists; preserve evidence and choose a new output path')
        records = evaluation.load_records(args.data)
        artifact = json.loads(Path(args.baseline).read_text(encoding='utf-8'))
        report = compare_run(records, artifact)
        # Only load the known error corpus after selection is fixed.
        report['modernHumanRegression'] = modern_human_regression(
            artifact, evaluation.load_records(args.modern_human), json.loads(Path(args.modern_report).read_text(encoding='utf-8')),
        )
        report['reproducibility']['inputFileSha256'] = {str(path): evaluation.sha256(Path(path).read_bytes()) for path in (args.data, args.baseline, args.modern_human, args.modern_report)}
        report['reproducibility']['command'] = '.venv/bin/python tools/compare_classifiers.py --output <new-output.json>'
        write_report(args.output, report)
        print(json.dumps({'output': str(args.output), 'selection': report['candidateSelection'],
                          'candidates': [{'name': item['name'], 'validation': item['validation']['metrics']['confusion'],
                                          'historicalTest': item['historicalTestDiagnostics']['overall']} for item in report['candidates']],
                          'modernHumanFalsePositives': report['modernHumanRegression']['falsePositiveSourceIds']}, ensure_ascii=False, indent=2, allow_nan=False))
    except (ValueError, OSError, ImportError, Warning) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
