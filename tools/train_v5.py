"""Audit/import a curated corpus, train numerical V5 models and reproduce reports.

Default input is the existing, historically inspected pilot. Passing --data
imports a JSONL corpus after rights/label/lineage checks; --manifest is mandatory
for any claim of a fresh independent test. No network or model generation occurs.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import platform
import sys
import warnings

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai.detector import features
from ai.detector.evidence import POLICY, POLICY_VERSION, gate_results
from ai.detector.linear import calibrated_probability, canonical, digest, margin, validate_model
from ai.detector.runtime import MIN_SEGMENT_WORDS, SCHEMA, _language_and_style
from tools import model_evaluate as evaluation

CANDIDATES = ('char_3_5', 'word_1_2', 'word_char_1_2_3_5')
SPLITS = ('train', 'calibration', 'validation', 'test')
HISTORICAL_PATHS = ('data/pilot/corpus.jsonl', 'data/modern-human/corpus.jsonl',
                    'data/pilot-edits/corpus.jsonl', 'data/v5-mixed-regression/corpus.jsonl')
IDENTITIES = ('source_id', 'document_id', 'author_id', 'source_group_id')
RELATION_FIELDS = ('related_source_id', 'parent_source_id', 'parent_source_ids',
                   'paraphrase_group_id', 'derivative_group_id', 'prompt_family_id', 'lineage_ids')


def load_jsonl(path):
    path = Path(path)
    if path.stat().st_size > 100_000_000:
        raise ValueError('Corpus exceeds 100 MB; import reviewed shards separately')
    records = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    if not records or len(records) > 50_000:
        raise ValueError('Corpus must contain 1 to 50,000 records')
    return records


def _values(value):
    if value is None:
        return []
    values = value if isinstance(value, list) else [value]
    if any(not isinstance(item, str) or not item.strip() for item in values):
        raise ValueError('Lineage identifiers must be nonempty strings')
    return values


def _historical_identities():
    identities = set()
    hashes = set()
    for name in HISTORICAL_PATHS:
        path = ROOT / name
        if not path.exists():
            continue
        for row in load_jsonl(path):
            identities.update((key, value) for key in IDENTITIES for value in _values(row.get(key)))
            hashes.add(evaluation.normalized_text_hash(row['text']))
    return identities, hashes


def lineage_aliases(row):
    aliases = {(key, row[key]) for key in IDENTITIES}
    if row.get('commissioning_human_author_id'):
        aliases.add(('author_id', row['commissioning_human_author_id']))
    for key in RELATION_FIELDS:
        namespace = 'source_id' if key in ('related_source_id', 'parent_source_id', 'parent_source_ids') else key
        aliases.update((namespace, value) for value in _values(row.get(key)))
    return aliases


def audit_dataset(records, evidence_use='historical-development-diagnostic', manifest=None):
    """Reject cross-split connected lineages, including transitive derivatives.

    Provenance evidence is a recorded human review, not an automatic copyright
    determination. This audit verifies completeness, hashes and split isolation.
    """
    if evidence_use not in ('historical-development-diagnostic', 'fresh-independent-holdout', 'engineering-fixture'):
        raise ValueError('Invalid evidence use')
    parents = {}

    def find(item):
        parents.setdefault(item, item)
        while parents[item] != item:
            parents[item] = parents[parents[item]]
            item = parents[item]
        return item

    def union(left, right):
        parents[find(right)] = find(left)

    seen_ids, seen_texts, normalized = set(), {}, {}
    nodes = {}
    historical_ids, historical_hashes = _historical_identities() if evidence_use == 'fresh-independent-holdout' else (set(), set())
    for row in records:
        if not isinstance(row, dict) or any(not isinstance(row.get(key), str) or not row[key].strip() for key in IDENTITIES):
            raise ValueError('Every row needs source, document, author, and source-group identity')
        source = row['source_id']
        if source in seen_ids:
            raise ValueError('Duplicate source identity')
        seen_ids.add(source)
        if row.get('split') not in SPLITS or row.get('label') not in ('human', 'ai', 'ai-edited', 'mixed'):
            raise ValueError('Unsupported split or origin label')
        if row.get('language') not in ('sv', 'en') or not isinstance(row.get('genre'), str):
            raise ValueError('Language and genre are mandatory')
        text = row.get('text')
        if not isinstance(text, str) or not text.strip() or len(text.encode('utf-16-le')) // 2 > 12000:
            raise ValueError('Invalid bounded source text')
        text_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()
        if row.get('text_sha256') is not None and row['text_sha256'] != text_hash:
            raise ValueError('Source text hash mismatch')
        provenance = row.get('provenance', {})
        rights, label = provenance.get('rights', {}), provenance.get('label', {})
        if rights.get('status') != 'verified' or not rights.get('evidence') or not rights.get('basis'):
            raise ValueError('Verified rights evidence is mandatory')
        if not provenance.get('source') or not label.get('method') or not label.get('evidence'):
            raise ValueError('Origin label evidence is mandatory')
        if row['label'] in ('ai', 'ai-edited') and (not row.get('model') or label.get('method') not in ('generation-log', 'edit-log', 'verified-generation')):
            raise ValueError('AI labels need actual generator identity and generation/edit evidence')
        norm = evaluation.normalized_text_hash(text)
        normalized[source] = norm
        node = ('source_id', source)
        nodes[source] = node
        for key in IDENTITIES:
            union(node, (key, row[key]))
        if row.get('commissioning_human_author_id'):
            union(node, ('author_id', row['commissioning_human_author_id']))
        for key in RELATION_FIELDS:
            for value in _values(row.get(key)):
                namespace = 'source_id' if key in ('related_source_id', 'parent_source_id', 'parent_source_ids') else key
                union(node, (namespace, value))
        if norm in seen_texts:
            union(node, nodes[seen_texts[norm]])
        seen_texts[norm] = source
        if row['split'] == 'test' and evidence_use == 'fresh-independent-holdout':
            historical_parent = any(('source_id', value) in historical_ids
                                    for key in ('related_source_id', 'parent_source_id', 'parent_source_ids')
                                    for value in _values(row.get(key)))
            historical_author = ('author_id', row.get('commissioning_human_author_id')) in historical_ids
            if norm in historical_hashes or any((key, row[key]) in historical_ids for key in IDENTITIES) or historical_parent or historical_author:
                raise ValueError('A known historical corpus or family cannot become a fresh independent test')
    components = defaultdict(list)
    for row in records:
        components[find(nodes[row['source_id']])].append(row)
    for component in components.values():
        if len({row['split'] for row in component}) != 1:
            raise ValueError('Cross-split lineage leakage: ' + ', '.join(sorted(row['source_id'] for row in component)[:8]))
    frozen = False
    if evidence_use == 'fresh-independent-holdout':
        manifest = manifest or {}
        test_rows = [row for row in records if row['split'] == 'test']
        review = manifest.get('rightsReview', {})
        freeze = manifest.get('testFreeze', {})
        if (manifest.get('schemaVersion') != 'textlab-v5-data-manifest-1' or
                not all(review.get(key) for key in ('reviewer', 'reviewedAt', 'evidence')) or
                freeze.get('canonicalRowsSha256') != digest(test_rows) or
                not all(freeze.get(key) for key in ('frozenAt', 'custodian', 'record')) or
                freeze.get('neverUsedForDevelopment') is not True):
            raise ValueError('Fresh test requires reviewed rights, frozen test hashes and an explicit independent-custodian record')
        frozen = True
    split_details = {}
    for split in SPLITS:
        subset = [row for row in records if row['split'] == split]
        split_details[split] = {
            'count': len(subset), 'classCounts': dict(Counter(row['label'] for row in subset)),
            'sourceFamilies': len({row['source_group_id'] for row in subset}),
            'authors': sorted({row['author_id'] for row in subset}),
            'documentIds': sorted({row['document_id'] for row in subset}),
            'sourceGroups': sorted({row['source_group_id'] for row in subset}),
            'sourceIds': [row['source_id'] for row in subset],
            'lineageAliases': [list(item) for item in sorted(set().union(*(lineage_aliases(row) for row in subset)))],
            'normalizedTextSha256': sorted({normalized[row['source_id']] for row in subset}),
            'canonicalRowsSha256': digest(subset),
        }
    return {'passed': True, 'independentSplits': True, 'evidenceUse': evidence_use,
            'testFrozenBeforeEvaluation': frozen, 'recordCount': len(records),
            'connectedLineageFamilies': len(components), 'splits': split_details,
            'datasetCanonicalSha256': digest(records),
            'checks': ['source', 'document', 'author', 'source_group', 'parent', 'paraphrase', 'derivative',
                       'prompt_family', 'commissioning_author', 'normalized_text_hash', 'rights', 'origin_label'],
            'limitations': ['Metadata and recorded rights/label review cannot authenticate authorship of every word.',
                            'Unknown aliases, undisclosed derivatives, and approximate paraphrases need curator review.']}


def _eligible(row, level='document'):
    result = _language_and_style(row['text'], row['language'])
    reasons = []
    if result['languageAssessment']['status'] != 'supported':
        reasons.append('language_not_supported')
    if result['wordCount'] < (80 if level == 'document' else MIN_SEGMENT_WORDS):
        reasons.append('too_short')
    if level == 'document' and result['sentenceCount'] < 4:
        reasons.append('too_few_sentences')
    return result['wordCount'], reasons


def fit_candidate(name, rows, level='document'):
    if name not in CANDIDATES or not rows or any(row['split'] != 'train' for row in rows):
        raise ValueError('Candidate fitting requires only the train split')
    from sklearn.exceptions import ConvergenceWarning
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from scipy.sparse import hstack
    from sklearn.preprocessing import normalize

    eligible = [row for row in rows if row['label'] in ('human', 'ai') and not _eligible(row, level)[1]]
    if any(sum(row['label'] == label for row in eligible) < 4 for label in ('human', 'ai')):
        raise ValueError('Training requires at least four eligible examples of each binary class')
    analyzers = ['char'] if name == 'char_3_5' else ['word'] if name == 'word_1_2' else ['word', 'char']
    vectorizers, matrices, blocks = [], [], []
    for analyzer in analyzers:
        options = dict(analyzer=analyzer, ngram_range=(3, 5) if analyzer == 'char' else (1, 2),
                       lowercase=True, min_df=2, max_features=20000 if analyzer == 'char' else 10000,
                       sublinear_tf=True, norm='l2', smooth_idf=True)
        if analyzer == 'word':
            options['token_pattern'] = r'(?u)\b\w\w+\b'
        vectorizer = TfidfVectorizer(**options)
        matrices.append(vectorizer.fit_transform([row['text'] for row in eligible]))
        vectorizers.append(vectorizer)
        blocks.append({'analyzer': analyzer, 'ngramRange': list(options['ngram_range']),
                       'vocabulary': {term: int(index) for term, index in vectorizer.vocabulary_.items()},
                       'idf': vectorizer.idf_.tolist()})
    matrix = normalize(hstack(matrices), norm='l2')
    classifier = LogisticRegression(C=1., solver='liblinear', class_weight='balanced', random_state=42, max_iter=1000)
    with warnings.catch_warnings():
        warnings.simplefilter('error', ConvergenceWarning)
        classifier.fit(matrix, [int(row['label'] == 'ai') for row in eligible])
    model = {'kind': 'tfidf_logistic', 'blocks': blocks, 'coefficients': classifier.coef_[0].tolist(),
             'intercept': float(classifier.intercept_[0]), 'normalization': 'block-l2-then-global-l2'}
    validate_model(model)
    return model, vectorizers, classifier


def score_records(model, records, level='document'):
    scored = []
    for row in records:
        words, reasons = _eligible(row, level)
        score = margin(model, row['text'])
        if score is None:
            reasons.append('out_of_vocabulary')
        scored.append({key: row.get(key) for key in ('source_id', 'source_group_id', 'author_id', 'document_id', 'split', 'label', 'language', 'genre')} |
                      {'model': row.get('model') or '(human)', 'words': words,
                       'score': None if reasons else score, 'abstentionReasons': reasons})
    return scored


def fit_calibration(scored):
    if not scored or any(row.get('split') != 'calibration' for row in scored):
        raise ValueError('Probability calibration requires only the separate calibration split')
    from sklearn.linear_model import LogisticRegression
    values = [row for row in scored if row['label'] in ('human', 'ai') and row['score'] is not None]
    counts = dict(Counter(row['label'] for row in values))
    if any(counts.get(label, 0) < 2 for label in ('human', 'ai')):
        raise ValueError('Calibration requires both classes')
    classifier = LogisticRegression(C=1., solver='lbfgs', random_state=42, max_iter=1000)
    classifier.fit([[row['score']] for row in values], [int(row['label'] == 'ai') for row in values])
    fitted = {'method': 'platt', 'slope': float(classifier.coef_[0][0]),
              'intercept': float(classifier.intercept_[0]),
              'fitting': {'split': 'calibration', 'classCounts': counts, 'scoredRowsSha256': digest(values)}}
    if fitted['slope'] <= 0:
        raise ValueError('Calibration inverted the class order; no supported probability mapping')
    return fitted


def calibration_metrics(labels, probabilities):
    if not labels:
        return {'count': 0, 'ece10': None, 'brier': None, 'bins': []}
    bins = []
    ece = 0.
    for index in range(10):
        pairs = [(y, p) for y, p in zip(labels, probabilities, strict=True) if min(9, int(p*10)) == index]
        if not pairs:
            continue
        observed = sum(y for y, _ in pairs) / len(pairs)
        predicted = sum(p for _, p in pairs) / len(pairs)
        ece += len(pairs) / len(labels) * abs(observed-predicted)
        bins.append({'lower': index/10, 'upper': (index+1)/10, 'count': len(pairs),
                     'meanProbability': predicted, 'observedAiFraction': observed,
                     'observedAiFractionInterval95': evaluation.wilson(sum(y for y, _ in pairs), len(pairs))})
    return {'count': len(labels), 'ece10': ece,
            'brier': sum((p-y)**2 for y, p in zip(labels, probabilities, strict=True))/len(labels), 'bins': bins}


def select_thresholds(scored):
    selection = evaluation.select_threshold(scored, .05)
    # Select a separate human-like boundary with a symmetric observed AI-as-human
    # constraint. Neither boundary has a statistical guarantee on a tiny pilot.
    human = [row['score'] for row in scored if row['label'] == 'human' and row['score'] is not None]
    ai = [row['score'] for row in scored if row['label'] == 'ai' and row['score'] is not None]
    candidates = sorted(set(human+ai))
    candidates.insert(0, math.nextafter(candidates[0], -math.inf))
    candidates = [value for value in candidates if value < selection['threshold'] and sum(x <= value for x in ai)/len(ai) <= .05]
    low = max(candidates, key=lambda value: (sum(x <= value for x in human), -sum(x <= value for x in ai), -value))
    return {'aiMin': selection['threshold'], 'humanMax': low, 'selectionSplit': 'validation',
            'objective': 'maximize class recall subject to observed opposite-class error <= 0.05; ambiguous gap abstains',
            'maximumObservedOppositeClassError': .05}, selection


def summarize(scored, thresholds, calibration=None):
    binary = [row for row in scored if row['label'] in ('human', 'ai', 'ai-edited')]
    metrics = evaluation.summarize(binary, thresholds['aiMin'])
    metrics['classCounts'] = {label: sum(row['label'] == label for row in binary) for label in ('human', 'ai')}
    metrics['familiesByLabel'] = {label: len({row['source_group_id'] for row in binary if row['label'] == label}) for label in ('human', 'ai')}
    metrics['sourceFamilies'] = len({row['source_group_id'] for row in scored})
    metrics['intervals95']['precision'] = evaluation.wilson(metrics['confusion']['tp'], metrics['confusion']['tp'] + metrics['confusion']['fp'])
    metrics['intervals95']['recallAllAI'] = evaluation.wilson(metrics['confusion']['tp'], metrics['classCounts']['ai'])
    metrics['intervals95'] = {key: [value['lower'], value['upper']] if value else None
                              for key, value in metrics['intervals95'].items()}
    metrics['intervalMethod'] = '95% Wilson observation-level; dependence within source families may make these intervals too narrow.'
    categories = Counter('unassessed' if row['score'] is None else 'ai_like' if row['score'] >= thresholds['aiMin']
                         else 'human_like' if row['score'] <= thresholds['humanMax'] else 'uncertain' for row in scored)
    metrics['categoryCounts'] = dict(categories)
    metrics['decisionCoverage'] = (categories['ai_like'] + categories['human_like'])/len(scored) if scored else None
    metrics['binaryMetricSemantics'] = 'AI flag versus not flagged at aiMin; uncertain scores count as not flagged, ineligible scores abstain.'
    human_rows = [row for row in binary if row['label'] == 'human']
    families = {row['source_group_id'] for row in human_rows if row['score'] is not None}
    flagged = {row['source_group_id'] for row in human_rows if row['score'] is not None and row['score'] >= thresholds['aiMin']}
    metrics['humanFamilyFalsePositives'] = {'flagged': len(flagged), 'assessed': len(families),
        'interval95': evaluation.wilson(len(flagged), len(families)),
        'estimand': 'Source families with any flagged human excerpt; assumes independent exchangeable families.'}
    values = [row for row in binary if row['label'] in ('human', 'ai') and row['score'] is not None]
    metrics['calibration'] = calibration_metrics([int(row['label'] == 'ai') for row in values],
                                               [calibrated_probability(calibration, row['score']) for row in values]) if calibration else {
        'count': 0, 'ece10': None, 'brier': None, 'bins': [], 'reason': 'No separate calibration fit; margins are not probabilities.'}
    return metrics


def report_slices(scored, thresholds, calibration=None):
    def slices(key):
        values = sorted({key(row) for row in scored})
        return {value: summarize([row for row in scored if key(row) == value], thresholds, calibration) for value in values}
    return {'metrics': summarize(scored, thresholds, calibration),
            'byLanguage': slices(lambda row: row['language']), 'byGenre': slices(lambda row: row['genre']),
            'byLength': slices(lambda row: 'short' if row['words'] < 80 else 'medium' if row['words'] < 300 else 'long'),
            'byGenerator': slices(lambda row: row['model']), 'predictions': scored}


def train_level(records, audit, level='document'):
    train = [row for row in records if row['split'] == 'train']
    validation = [row for row in records if row['split'] == 'validation']
    test = [row for row in records if row['split'] == 'test']
    calibration_rows = [row for row in records if row['split'] == 'calibration']
    if not validation or not test:
        raise ValueError('Separate validation and test splits are mandatory')
    candidates, fitted = [], {}
    for name in CANDIDATES:
        model, vectorizers, classifier = fit_candidate(name, train, level)
        scored = score_records(model, validation, level)
        thresholds, selection = select_thresholds(scored)
        candidates.append({'name': name, 'featureCount': len(model['coefficients']), 'modelSha256': digest(model),
                           'thresholds': thresholds, 'validation': selection})
        fitted[name] = (model, vectorizers, classifier)
    # Freeze model choice and operating points before looking at any test score.
    chosen = max(candidates, key=lambda item: (item['validation']['metrics']['recallAllAI'],
                 -item['validation']['metrics']['falsePositiveRate'], item['validation']['metrics']['coverage'],
                 -CANDIDATES.index(item['name'])))
    model, vectorizers, classifier = fitted[chosen['name']]
    calibration = fit_calibration(score_records(model, calibration_rows, level)) if calibration_rows else None
    from scipy.sparse import hstack
    from sklearn.preprocessing import normalize
    parity_texts = [row['text'] for row in records] + ['😀 the\n\nand Åsa', 'one O’Neill １２３', 'unseen𐐀']
    matrix = normalize(hstack([vectorizer.transform(parity_texts) for vectorizer in vectorizers]), norm='l2')
    expected = classifier.decision_function(matrix)
    errors = [abs(float(reference) - actual) for text, reference in zip(parity_texts, expected, strict=True) if (actual := margin(model, text)) is not None]
    parity = max(errors, default=0.)
    if parity > 1e-10:
        raise ValueError('Exported model inference differs from sklearn')
    for candidate in candidates:
        candidate['historicalTestDiagnostics'] = report_slices(score_records(fitted[candidate['name']][0], test, level), candidate['thresholds'])
        candidate['testUsedForSelection'] = False
    scored = score_records(model, test, level)
    evidence = {**report_slices(scored, chosen['thresholds'], calibration),
                'evidenceUse': audit['evidenceUse'], 'testFrozenBeforeEvaluation': audit['testFrozenBeforeEvaluation'],
                'modelSha256': digest(model), 'thresholdsSha256': digest(chosen['thresholds']),
                'calibrationSha256': digest(calibration) if calibration else None}
    evidence['lineageAudit'] = {**audit, 'bindingSha256': digest(evidence)}
    report = {'selectedCandidate': chosen['name'], 'selectionSplit': 'validation', 'candidates': candidates,
              'predeclaredCandidateOrder': list(CANDIDATES), 'jsonSklearnMaximumAbsoluteError': parity,
              'calibration': calibration, 'evidence': evidence, 'trainingAudit': audit}
    return model, chosen['thresholds'], calibration, evidence, report


def train_run(records, manifest=None, evidence_use='historical-development-diagnostic', segment_records=None,
              segment_manifest=None, segment_evidence_use='historical-development-diagnostic'):
    audit = audit_dataset(records, evidence_use, manifest)
    model, thresholds, calibration, evidence, report = train_level(records, audit)
    artifact = {'schemaVersion': SCHEMA, 'modelVersion': 'textlab-v5-' + digest(model)[:12] + '-' + digest(records)[:8],
                'documentModel': model, 'documentThresholds': thresholds, 'documentCalibration': calibration,
                'segmentModel': None, 'segmentThresholds': None, 'segmentCalibration': None,
                'evidencePolicy': {'version': POLICY_VERSION, **POLICY}, 'evidence': {'document': evidence},
                'scoreSemantics': 'linear_scores_private_until_independent_gates_pass',
                'eligibility': {'documentMinimumWords': 80, 'documentMinimumSentences': 4,
                                'segmentMinimumWords': MIN_SEGMENT_WORDS, 'languages': ['sv', 'en']},
                'lineageAudit': audit}
    segment_report = None
    if segment_records:
        segment_audit = audit_dataset(segment_records, segment_evidence_use, segment_manifest)
        smodel, sthresholds, scalibration, sevidence, segment_report = train_level(segment_records, segment_audit, 'segment')
        artifact.update(segmentModel=smodel, segmentThresholds=sthresholds, segmentCalibration=scalibration)
        artifact['evidence']['segment'] = sevidence
    artifact['artifactSha256'] = digest(artifact)
    gates = gate_results(artifact)
    environment = {'python': platform.python_version(), 'dependencies': {
        name: importlib.metadata.version(name) for name in ('scikit-learn', 'numpy', 'scipy')}}
    combined_report = {'schemaVersion': 'textlab-v5-evaluation-1', 'evidenceUse': evidence_use,
                       'qualityEvidence': evidence_use == 'fresh-independent-holdout',
                       'productionApproved': gates['document']['passed'] and gates['calibration']['passed'],
                       'gates': gates, 'policy': {'version': POLICY_VERSION, **POLICY},
                       'document': report, 'segment': segment_report,
                       'artifactSha256': artifact['artifactSha256'], 'environment': environment,
                       'reproducibility': {
                           'datasetCanonicalSha256': digest(records),
                           'trainingConfiguration': {'lowercase': True, 'minDf': 2, 'sublinearTf': True,
                               'smoothIdf': True, 'normalization': 'block-l2-then-global-l2',
                               'maxCharFeatures': 20000, 'maxWordFeatures': 10000,
                               'logisticRegression': {'C': 1., 'solver': 'liblinear', 'classWeight': 'balanced', 'randomState': 42, 'maxIter': 1000},
                               'plattRegression': {'C': 1., 'solver': 'lbfgs', 'randomState': 42, 'maxIter': 1000}},
                           'codeSha256': {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in (
                               'tools/train_v5.py', 'tools/model_evaluate.py', 'ai/detector/linear.py',
                               'ai/detector/runtime.py', 'ai/detector/evidence.py', 'ai/detector/features.py')},
                       },
                       'limitations': ['Existing pilot and previously inspected holdouts are historical diagnostics, not fresh evidence.',
                                       'Observation-level Wilson intervals ignore source dependence; family counts and intervals are also reported.',
                                       'No modern multilingual genre-balanced corpus or independent segment calibration is bundled.',
                                       'Era, topic, publisher spelling and generator-family confounds remain.']}
    return artifact, combined_report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=ROOT/'data/pilot/corpus.jsonl')
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--output-dir', type=Path, default=ROOT/'artifacts/v5-reproduced')
    parser.add_argument('--overwrite', action='store_true', help='Explicitly replace V5 outputs; prior corpus/model files are never modified')
    parser.add_argument('--evidence-use', choices=('historical-development-diagnostic', 'fresh-independent-holdout', 'engineering-fixture'), default='historical-development-diagnostic')
    parser.add_argument('--segment-data', type=Path)
    parser.add_argument('--segment-manifest', type=Path)
    parser.add_argument('--segment-evidence-use', choices=('historical-development-diagnostic', 'fresh-independent-holdout', 'engineering-fixture'), default='historical-development-diagnostic')
    parser.add_argument('--modern-human', type=Path, default=ROOT/'data/modern-human/corpus.jsonl')
    args = parser.parse_args(argv)
    try:
        outputs = [args.output_dir/name for name in ('detector.json', 'evaluation.json')]
        if not args.overwrite and any(path.exists() for path in outputs):
            raise ValueError('Output already exists; choose a new directory or explicitly pass --overwrite')
        records = load_jsonl(args.data)
        artifact, report = train_run(records,
            json.loads(args.manifest.read_text()) if args.manifest else None, args.evidence_use,
            load_jsonl(args.segment_data) if args.segment_data else None,
            json.loads(args.segment_manifest.read_text()) if args.segment_manifest else None, args.segment_evidence_use)
        if args.modern_human.exists():
            modern = load_jsonl(args.modern_human)
            report['modernHumanHistoricalDiagnostic'] = {
                **report_slices(score_records(artifact['documentModel'], modern), artifact['documentThresholds'], artifact['documentCalibration']),
                'evidenceUse': 'historical-development-diagnostic', 'usedForSelection': False,
                'freshIndependentEvidence': False, 'datasetCanonicalSha256': digest(modern)}
        args.output_dir.mkdir(parents=True, exist_ok=True)
        mode = 'w' if args.overwrite else 'x'
        with outputs[0].open(mode, encoding='utf-8') as stream:
            stream.write(canonical(artifact)+'\n')
        with outputs[1].open(mode, encoding='utf-8') as stream:
            stream.write(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
        print(json.dumps({'modelVersion': artifact['modelVersion'], 'selectedCandidate': report['document']['selectedCandidate'],
                          'artifactSha256': artifact['artifactSha256'], 'productionApproved': report['productionApproved'],
                          'documentGate': report['gates']['document']['passed'], 'segmentGate': report['gates']['segment']['passed']}))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, f'V5 training rejected: {error}\n')


if __name__ == '__main__':
    main()
