"""Train the frozen offline pilot; never connect this artifact to production.

Fit vocabulary/IDF/coefficients on train only. Choose the decision threshold on
validation only; score the held-out test once after freezing those choices.
"""
from __future__ import annotations

import argparse
from collections import Counter
import importlib.metadata
import json
from pathlib import Path
import platform
import sys
import warnings

if __package__:
    from . import model_evaluate as evaluation
else:
    import model_evaluate as evaluation

CONFIG = {'analyzer': 'char', 'ngram_range': [3, 5], 'lowercase': True, 'min_df': 2, 'max_features': 20_000,
          'sublinear_tf': True, 'norm': 'l2', 'smooth_idf': True,
          'classifier': 'LogisticRegression', 'C': 1.0, 'solver': 'liblinear', 'class_weight': 'balanced',
          'random_state': 42, 'max_iter': 1000, 'maxObservedValidationHumanFPR': .05,
          'eligibility': 'same frozen analyzer language/minimum80words/minimum4sentences guard as style comparator',
          'minimumAssessedPerClass': {'train': 4, 'validation': 2, 'test': 2},
          'minimumSourceGroupsPerClass': {'train': 2, 'validation': 1, 'test': 1},
          'modelHoldoutDiagnostics': {'models': ['llama3.2:3b', 'qwen3.5:4b'],
                                      'protocol': 'Fit and select using one model; evaluate human plus the other, unseen model. Report both without choosing a winner.'}}


def check_class_counts(rows, split):
    selected = [row for row in rows if row['split'] == split and row['label'] in ('human', 'ai')]
    minimum = CONFIG['minimumAssessedPerClass'][split]
    minimum_groups = CONFIG['minimumSourceGroupsPerClass'][split]
    for label in ('human', 'ai'):
        subset = [row for row in selected if row['label'] == label]
        if len(subset) < minimum:
            raise ValueError(f'{split} needs at least {minimum} assessed {label} examples')
        if len({row['source_group_id'] for row in subset}) < minimum_groups:
            raise ValueError(f'{split} needs at least {minimum_groups} independent {label} source groups')
    return selected


def fit_baseline(rows):
    if not rows or any(row['split'] != 'train' for row in rows):
        raise ValueError('Fitting requires only the train split')
    rows = check_class_counts(rows, 'train')
    from sklearn.exceptions import ConvergenceWarning
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    vectorizer = TfidfVectorizer(analyzer=CONFIG['analyzer'], ngram_range=tuple(CONFIG['ngram_range']),
                                 lowercase=True, min_df=2, max_features=20_000, sublinear_tf=True, norm='l2', smooth_idf=True)
    features = vectorizer.fit_transform([row['text'] for row in rows])
    classifier = LogisticRegression(C=1.0, solver='liblinear', class_weight='balanced', random_state=42, max_iter=1000)
    with warnings.catch_warnings():
        warnings.simplefilter('error', ConvergenceWarning)
        classifier.fit(features, [int(row['label'] == 'ai') for row in rows])
    artifact = {'schemaVersion': evaluation.SCHEMA, 'scoreSemantics': 'uncalibrated_logistic_margin',
                'calibration': evaluation.CALIBRATION, 'config': CONFIG, 'configSha256': evaluation.sha256(evaluation.canonical(CONFIG)),
                'vocabulary': {key: int(value) for key, value in vectorizer.vocabulary_.items()},
                'idf': vectorizer.idf_.tolist(), 'coefficients': classifier.coef_[0].tolist(), 'intercept': float(classifier.intercept_[0]),
                'training': {'split': 'train', 'count': len(rows), 'byLabel': dict(Counter(row['label'] for row in rows)),
                             'sourceGroups': sorted({row['source_group_id'] for row in rows}),
                             'authors': sorted({row['author_id'] for row in rows}),
                             'documentIds': sorted({row['document_id'] for row in rows}),
                             'sourceIds': [row['source_id'] for row in rows],
                             'rowsSha256': evaluation.sha256(evaluation.canonical(rows))}}
    evaluation.validate_weights(artifact)
    return artifact, vectorizer, classifier


def model_holdout_diagnostics(records, analyses, dataset_sha256=None):
    diagnostics = []
    models = CONFIG['modelHoldoutDiagnostics']['models']
    for heldout in models:
        fit_model = next(model for model in models if model != heldout)
        diagnostic = {'heldoutModel': heldout, 'fitModels': [fit_model], 'thresholdModels': [fit_model],
                      'protocol': CONFIG['modelHoldoutDiagnostics']['protocol'], 'available': False}
        pairs = [(row, analysis) for row, analysis in zip(records, analyses, strict=True)
                 if row['label'] == 'human' or (row['label'] == 'ai' and row['model'] == (heldout if row['split'] == 'test' else fit_model))]
        subset, subset_analyses = ([pair[index] for pair in pairs] for index in (0, 1))
        try:
            eligible = [row for row, analysis in pairs if analysis['eligible']]
            for split in ('train', 'validation', 'test'):
                check_class_counts(eligible, split)
            artifact, _, _ = fit_baseline([row for row in eligible if row['split'] == 'train'])
            validation_pairs = [(row, analysis) for row, analysis in pairs if row['split'] == 'validation']
            selection = evaluation.select_threshold(evaluation.score_records([row for row, _ in validation_pairs], [analysis for _, analysis in validation_pairs], artifact))
            artifact['selection'] = selection
            artifact['datasetSha256'] = dataset_sha256 or evaluation.sha256(evaluation.canonical(records))
            evaluation.attach_development_provenance(artifact, [row for row in subset if row['split'] == 'train'], [row for row, _ in validation_pairs])
            evaluation.assert_unseen_test(artifact, subset)
            diagnostic.update({'available': True, 'training': artifact['training'], 'selection': selection,
                               'test': evaluation.heldout_report(evaluation.score_records(subset, subset_analyses, artifact), selection['threshold']),
                               'model': artifact})
        except ValueError as error:
            diagnostic['reason'] = str(error)
        diagnostics.append(diagnostic)
    return diagnostics


def train_run(records, dataset_bytes, fixture=False):
    audit = evaluation.audit_records(records, fixture=fixture)
    eligible = [row for row, analysis in zip(records, audit['analyses'], strict=True) if analysis['eligible']]
    # Minimal engineering gates, deliberately not claimed as statistical adequacy.
    for split in ('train', 'validation', 'test'):
        check_class_counts(eligible, split)
    artifact, vectorizer, classifier = fit_baseline([row for row in eligible if row['split'] == 'train' and row['label'] in ('human', 'ai')])
    validation = [row for row in records if row['split'] == 'validation']
    validation_analyses = [analysis for row, analysis in zip(records, audit['analyses'], strict=True) if row['split'] == 'validation']
    selection = evaluation.select_threshold(evaluation.score_records(validation, validation_analyses, artifact), CONFIG['maxObservedValidationHumanFPR'])
    artifact['selection'] = selection
    artifact['datasetSha256'] = evaluation.sha256(dataset_bytes)
    evaluation.attach_development_provenance(artifact, [row for row in records if row['split'] == 'train'], validation)
    evaluation.assert_unseen_test(artifact, records)
    # Only after freezing fitting and operating point do we compute test margins.
    scored = evaluation.score_records(records, audit['analyses'], artifact)
    parity_texts = [row['text'] for row in records if row['split'] != 'train']
    sklearn_margins = classifier.decision_function(vectorizer.transform(parity_texts))
    parity_error = max(abs(float(margin) - evaluation.score_text(artifact, text)) for text, margin in zip(parity_texts, sklearn_margins, strict=True))
    if parity_error > 1e-10:
        raise ValueError(f'JSON scoring differs from sklearn: {parity_error}')
    style_scored = [{**row, 'score': analysis['styleScore']} for row, analysis in zip(scored, audit['analyses'], strict=True)]
    environment = {'python': platform.python_version(), 'platform': platform.platform(), 'node': audit['node'],
                   'dependencies': {name: importlib.metadata.version(name) for name in ['scikit-learn', 'numpy', 'scipy', 'joblib', 'threadpoolctl', 'narwhals', 'cloudpickle']}}
    code_hashes = {str(path.relative_to(evaluation.ROOT)).replace('\\', '/'): evaluation.sha256(path.read_bytes())
                   for path in [Path(__file__), Path(evaluation.__file__), evaluation.ROOT / 'tools/evaluate.mjs', evaluation.ROOT / 'sites/src/analyzer.mjs']}
    artifact['environment'] = environment
    artifact['codeSha256'] = code_hashes
    artifact['status'] = 'synthetic-engineering-fixture' if fixture else 'exploratory-pilot-not-production'
    report = {'schemaVersion': 'textlab-experimental-evaluation-v1', 'status': artifact['status'],
              'qualityEvidence': False, 'productionApproved': False, 'calibration': evaluation.CALIBRATION,
              'dataset': audit['dataset'], 'selection': selection,
              'trained': evaluation.heldout_report(scored, selection['threshold']),
              'frozenStyleComparator': evaluation.heldout_report(style_scored, 65),
              'leaveOneModelOut': model_holdout_diagnostics(records, audit['analyses'], artifact['datasetSha256']),
              'reproducibility': {'datasetFileSha256': artifact['datasetSha256'], 'datasetCanonicalSha256': evaluation.sha256(evaluation.canonical(records)),
                                  'configSha256': artifact['configSha256'], 'codeSha256': code_hashes, 'environment': environment,
                                  'jsonScoringMaxAbsError': parity_error, 'fitSplit': 'train', 'thresholdSplit': 'validation', 'evaluatedSplit': 'test'},
              'limitations': ['Small historical human versus contemporary model corpus; era, spelling, publisher, topic and genre may confound labels.',
                              'The primary fit sees both models. Separate predeclared leave-one-model-out diagnostics test only the two available models and do not establish generalization to other model families.',
                              'Source/author groups are separated, but excerpts from a group remain dependent. Wilson intervals ignore this dependence.',
                              'Observed validation FPR <=5% does not bound population FPR; only a larger external audit can estimate that.',
                              'No calibrated probability, production deployment, quality score or modern-writing generalization claim is supported.',
                              'Test results are exploratory. Future feature or threshold development needs a fresh holdout rather than retuning this test.']}
    return artifact, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--fixture', action='store_true')
    args = parser.parse_args()
    try:
        records = evaluation.load_records(args.data)
        output = Path(args.output)
        if output.exists():
            raise ValueError('Output path exists; preserve frozen runs and choose a new output path')
        artifact, report = train_run(records, Path(args.data).read_bytes(), fixture=args.fixture)
        serialized = json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + '\n'
        report['reproducibility']['modelFileSha256'] = evaluation.sha256(serialized)
        output.mkdir(parents=True)
        (output / 'model.json').write_text(serialized, encoding='utf-8', newline='\n')
        (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + '\n', encoding='utf-8', newline='\n')
        print(json.dumps({'output': str(output), 'status': report['status'], 'trained': report['trained']['overall'],
                          'frozenStyleComparator': report['frozenStyleComparator']['overall']}, ensure_ascii=False, indent=2, allow_nan=False))
    except (ValueError, OSError, ImportError, Warning) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
