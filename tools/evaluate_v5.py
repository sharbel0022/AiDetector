"""Reproduce V5 diagnostics from a frozen safe JSON model without refitting it."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai.detector.runtime import load_artifact
from ai.detector.linear import digest
from tools.train_v5 import audit_dataset, lineage_aliases, load_jsonl, report_slices, score_records
from tools.model_evaluate import normalized_text_hash


def assert_independent_from_development(records, artifact, level='document'):
    audit = artifact['evidence'][level]['lineageAudit']
    mapping = {'source_id': 'sourceIds', 'document_id': 'documentIds', 'author_id': 'authors', 'source_group_id': 'sourceGroups'}
    for row in records:
        for split in ('train', 'calibration', 'validation'):
            footprint = audit['splits'][split]
            if any(row.get(key) in footprint[value] for key, value in mapping.items()):
                raise ValueError('Evaluation overlaps a development identity')
            if lineage_aliases(row) & {tuple(item) for item in footprint.get('lineageAliases', [])}:
                raise ValueError('Evaluation derivative overlaps development')
            if normalized_text_hash(row['text']) in footprint['normalizedTextSha256']:
                raise ValueError('Evaluation text overlaps development')


def evaluate(artifact, records, level='document'):
    if any(row.get('split') != 'test' for row in records):
        raise ValueError('Frozen model evaluation requires test rows only')
    model = artifact.get(level + 'Model')
    if model is None:
        return {'available': False, 'reason': 'No separately trained segment model',
                'evidenceUse': 'historical-development-diagnostic', 'qualityEvidence': False}
    audit = audit_dataset(records)
    assert_independent_from_development(records, artifact, level)
    return {'available': True, 'modelVersion': artifact['modelVersion'], 'artifactSha256': artifact['artifactSha256'],
            'datasetCanonicalSha256': digest(records), 'audit': audit,
            **report_slices(score_records(model, records, level), artifact[level + 'Thresholds'], artifact[level + 'Calibration']),
            'evidenceUse': 'historical-development-diagnostic', 'qualityEvidence': False,
            'note': 'Replay never changes release gates or creates a fresh-test claim.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path, default=ROOT/'models/v5/detector.json')
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--overwrite', action='store_true')
    parser.add_argument('--level', choices=('document', 'segment'), default='document')
    args = parser.parse_args(argv)
    try:
        if args.output.exists() and not args.overwrite:
            raise ValueError('Output already exists; choose a new file or explicitly pass --overwrite')
        artifact, _ = load_artifact(args.model)
        records = [row for row in load_jsonl(args.data) if row['split'] == 'test']
        if not records:
            raise ValueError('No test records to evaluate')
        result = evaluate(artifact, records, args.level)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('w' if args.overwrite else 'x', encoding='utf-8') as stream:
            stream.write(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
        print(json.dumps({'available': result['available'], 'qualityEvidence': False, 'output': str(args.output)}))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, f'V5 evaluation rejected: {error}\n')


if __name__ == '__main__':
    main()
