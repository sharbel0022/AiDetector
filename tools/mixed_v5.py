"""Build exact mixed-origin historical regression documents, never a new holdout.

Concatenation is the only transformation. Parent origin labels and their original
rights/attribution records are inherited, not independently verified by this tool.
No statistical independence is created by composing existing source material.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ai.contracts import utf16_length
from ai.detector.features import analyze_text


def digest(value: str | bytes) -> str:
    return hashlib.sha256(value.encode('utf-8') if isinstance(value, str) else value).hexdigest()


def compose_mixed(records: list[dict]) -> list[dict]:
    groups = defaultdict(list)
    identities = {}
    seen = set()
    for row in records:
        if row.get('label') not in ('human', 'ai'):
            raise ValueError('Mixed construction requires a known pure parent origin')
        if not isinstance(row.get('text'), str) or digest(row['text']) != row.get('text_sha256'):
            raise ValueError('Parent text hash does not match the archived source')
        if not isinstance(row.get('provenance'), dict):
            raise ValueError('Parent provenance is required')
        if row.get('source_id') in seen:
            raise ValueError('Duplicate parent source identity')
        seen.add(row.get('source_id'))
        for field in ('source_id', 'author_id', 'document_id', 'source_group_id', 'split'):
            if not isinstance(row.get(field), str) or not row[field]:
                raise ValueError('Complete parent identities are required')
        for field in ('author_id', 'document_id', 'source_group_id'):
            key = (field, row[field])
            if key in identities and identities[key] != row['split']:
                raise ValueError('Parent identity crosses a source partition')
            identities[key] = row['split']
        if row.get('language') not in ('sv', 'en'):
            raise ValueError('Unsupported parent language')
        groups[row['source_group_id']].append(row)

    results = []
    for group_index, (family, members) in enumerate(sorted(groups.items())):
        if len({r['language'] for r in members}) != 1:
            raise ValueError('Mixed parent family has inconsistent language')
        humans = sorted((r for r in members if r['label'] == 'human'), key=lambda r: r['source_id'])
        generated = sorted((r for r in members if r['label'] == 'ai'), key=lambda r: r['source_id'])
        for index, ai in enumerate(generated):
            if not humans:
                continue
            human = humans[index % len(humans)]
            parents = [human, ai] if (group_index + index) % 2 == 0 else [ai, human]
            text = '\n\n'.join(r['text'] for r in parents)
            if utf16_length(text) > 12000:
                raise ValueError('Mixed document exceeds the API text limit; parents are never silently truncated')
            position = 0
            spans = []
            provenance = []
            for parent in parents:
                length = utf16_length(parent['text'])
                words = analyze_text(parent['text'], parent['language'])['wordCount']
                spans.append({
                    'start': position, 'end': position + length,
                    'origin': parent['label'], 'wordCount': words,
                    'parentSourceId': parent['source_id'], 'parentTextSha256': parent['text_sha256'],
                    'parentStart': 0, 'parentEnd': length,
                    'generator': parent.get('model'),
                })
                provenance.append({
                    'source_id': parent['source_id'], 'author_id': parent['author_id'],
                    'document_id': parent['document_id'], 'source_group_id': family,
                    'text_sha256': parent['text_sha256'], 'provenance': parent['provenance'],
                    'excerpt': parent.get('excerpt'),
                })
                position += length + 2
            total_words = sum(s['wordCount'] for s in spans)
            ai_words = sum(s['wordCount'] for s in spans if s['origin'] == 'ai')
            results.append({
                'schemaVersion': 'textlab-mixed-regression-v5',
                'id': 'mixed-v5-' + digest('|'.join(r['source_id'] for r in parents))[:20],
                'text': text, 'text_sha256': digest(text),
                'language': human['language'], 'genre': human['genre'],
                'source_group_id': family, 'sourceSplit': human['split'],
                'purpose': 'historical_segment_regression', 'qualityEvidence': False,
                'independentSourceFamiliesAdded': 0,
                'transformation': 'Exact full parent texts joined by two newline characters; alternating order.',
                'labelMeaning': 'Origin of retained source chunks, not an estimate of semantic AI influence.',
                'analyzableWords': total_words, 'knownAiWords': ai_words,
                'knownAiWordShare': 100 * ai_words / total_words if total_words else None,
                'segments': spans, 'parents': provenance,
            })
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', default=str(ROOT / 'data/pilot/corpus.jsonl'))
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = Path(args.output)
    if output.exists():
        parser.error('Output exists; preserve prior evidence and choose a new directory')
    raw = Path(args.data).read_bytes()
    records = [json.loads(line) for line in raw.decode('utf-8').splitlines() if line.strip()]
    # This rejects malformed rights/provenance, lineage leakage and duplicates in
    # the real archived source corpus before generating any deliverable.
    from tools.model_evaluate import audit_records
    audit_records(records)
    mixed = compose_mixed(records)
    if not mixed:
        parser.error('No paired human/AI parents in the audited input')
    body = ''.join(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + '\n' for row in mixed)
    manifest = {
        'schemaVersion': 'textlab-mixed-regression-manifest-v5',
        'status': 'derived-historical-diagnostics', 'qualityEvidence': False,
        'independentSourceFamiliesAdded': 0, 'sourceCorpusSha256': digest(raw),
        'corpusSha256': digest(body), 'documents': len(mixed),
        'existingSourceFamilies': len({row['source_group_id'] for row in mixed}),
        'byLanguage': dict(Counter(row['language'] for row in mixed)),
        'bySourceSplit': dict(Counter(row['sourceSplit'] for row in mixed)),
        'generatorModels': sorted({span['generator'] for row in mixed for span in row['segments'] if span['generator']}),
        'constructionCodeSha256': digest(Path(__file__).read_bytes()),
        'limitations': [
            'Existing pilot data are reused; these documents are not a fresh independent test set.',
            'Parent labels/rights retain their original source-audit limitations.',
            'Artificial juxtaposition is not representative of naturally mixed writing or editing.',
            'Known source word shares do not validate classifier percentages or semantic attribution.',
        ],
    }
    output.mkdir(parents=True)
    (output / 'corpus.jsonl').write_text(body, encoding='utf-8', newline='\n')
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
