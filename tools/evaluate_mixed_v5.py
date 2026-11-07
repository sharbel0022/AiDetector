"""Replay exact mixed-origin test derivatives; never create independent evidence.

The custom construction schema keeps each parent's identities and origin spans.
It is deliberately not converted into a pure human/AI document training label.
Unavailable segment classification produces unavailable quality metrics, not 0%.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai.detector.runtime import analyze_v5, load_artifact
from ai.detector.linear import digest
from tools.mixed_v5 import compose_mixed
from tools.model_evaluate import audit_records


def evaluate_mixed(mixed, parents, model_path=None):
    audit_records(parents)
    expected = compose_mixed(parents)
    if mixed != expected:
        raise ValueError('Mixed construction does not match audited archived parents')
    artifact, gates = load_artifact(model_path)
    selected = [row for row in mixed if row['sourceSplit'] == 'test']
    if not selected:
        raise ValueError('Mixed construction has no historical test derivatives')
    records = []
    origin_words = runtime_words = cross_origin = eligible_segments = classified = 0
    human_eligible = false_positive = true_positive = predicted_positive = 0
    errors = []
    for row in selected:
        result = analyze_v5(row['text'], row['language'], model_path)
        encoded = row['text'].encode('utf-16-le')
        segments = []
        eligible_origin_words = eligible_ai_words = 0
        last = 0
        for segment in result['segments']:
            start, end = segment['start'], segment['end']
            if start < last or encoded[2*start:2*end].decode('utf-16-le') != segment['text']:
                raise ValueError('Runtime segment differs from exact source interval')
            last = end
            origins = [source for source in row['segments'] if source['start'] <= start and end <= source['end']]
            origin = origins[0]['origin'] if len(origins) == 1 else None
            cross_origin += int(origin is None and segment['wordCount'] > 0)
            eligible = segment['eligible'] and origin is not None
            if eligible:
                eligible_segments += 1
                eligible_origin_words += segment['wordCount']
                eligible_ai_words += segment['wordCount'] if origin == 'ai' else 0
                classified += segment['category'] in ('ai_like', 'human_like')
                human_eligible += origin == 'human'
                if segment['category'] == 'ai_like':
                    predicted_positive += 1
                    true_positive += origin == 'ai'
                    false_positive += origin == 'human'
            segments.append({key: segment[key] for key in ('id', 'start', 'end', 'wordCount', 'category', 'eligible')} |
                            {'knownOrigin': origin})
        source_words = sum(span['wordCount'] for span in row['segments'])
        counted_words = sum(segment['wordCount'] for segment in result['segments'])
        if counted_words != source_words or result['wordCount'] != source_words:
            raise ValueError('Runtime word accounting differs from source construction')
        origin_words += source_words
        runtime_words += counted_words
        expected_share = 100 * eligible_ai_words / eligible_origin_words if eligible_origin_words else None
        share = result['detector']['aiMarkedPercent']
        if share is not None and expected_share is not None:
            errors.append(abs(share - expected_share))
        records.append({
            'id': row['id'], 'language': row['language'], 'sourceFamily': row['source_group_id'],
            'textSha256': row['text_sha256'], 'knownConstructionAiShare': row['knownAiWordShare'],
            'eligibleOriginAiShare': expected_share,
            'detectorMarkedShare': share, 'segmentValidated': result['detector']['segmentValidated'],
            'analyzedWords': result['detector']['analyzedWords'],
            'excludedWords': result['detector']['excludedWords'], 'segments': segments,
        })
    valid = gates['segment']['passed']
    return {
        'schemaVersion': 'textlab-v5-mixed-replay-1',
        'evidenceUse': 'historical-derived-regression', 'qualityEvidence': False,
        'sourceSplit': 'test', 'documents': len(records),
        'existingSourceFamilies': len({row['source_group_id'] for row in selected}),
        'independentSourceFamiliesAdded': 0,
        'modelVersion': artifact['modelVersion'], 'artifactSha256': artifact['artifactSha256'],
        'constructionCanonicalSha256': digest(mixed),
        'toolSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'alignment': {'sourceExact': True, 'crossOriginSegments': cross_origin,
                      'originWords': origin_words, 'runtimeWords': runtime_words},
        'metrics': {
            'classificationCoverage': classified / eligible_segments if eligible_segments else 0,
            'segmentPrecision': true_positive / predicted_positive if valid and predicted_positive else None,
            'humanFalsePositiveRate': false_positive / human_eligible if valid and human_eligible else None,
            'markedShareMeanAbsoluteError': sum(errors)/len(errors) if valid and errors else None,
        },
        'definitions': {
            'classificationCoverage': 'Binary-classified eligible segments / all eligible segments with known single origin.',
            'segmentPrecision': 'AI-origin segments / all AI-marked segments, only with validated segment inference.',
            'humanFalsePositiveRate': 'AI-marked human-origin segments / eligible human-origin segments.',
            'markedShareMeanAbsoluteError': 'Percentage-point error against known AI word share among eligible single-origin segments, not all source words.',
        },
        'limitations': [
            'Existing parents and test families have been inspected before; this is not independent quality evidence.',
            'Exact juxtaposition is not representative of naturally mixed or edited writing.',
            'Closed segment gates mean no precision, false-positive or percentage-error result is available.',
            'Origin labels inherit all provenance limitations of the archived parents.',
        ],
        'records': records,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=ROOT/'data/v5-mixed-regression/corpus.jsonl')
    parser.add_argument('--parents', type=Path, default=ROOT/'data/pilot/corpus.jsonl')
    parser.add_argument('--model', type=Path, default=ROOT/'models/v5/detector.json')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error('Output exists; choose a new path to preserve prior evidence')
    read = lambda path: [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    try:
        result = evaluate_mixed(read(args.data), read(args.parents), args.model)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
        print(json.dumps({key: result[key] for key in ('documents', 'qualityEvidence', 'alignment', 'metrics')}))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, f'Mixed replay rejected: {error}\n')


if __name__ == '__main__':
    main()
