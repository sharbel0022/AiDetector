"""Evidence hashes must survive the Git checkout used by CI and reviewers."""
from pathlib import Path
import hashlib
import json
import subprocess


def test_frozen_dataset_model_and_source_bytes_are_not_changed_by_git_filters():
    root=Path(__file__).resolve().parents[1]
    paths=['data/pilot/corpus.jsonl','data/pilot/manifest.json','models/experimental/pilot-v1/model.json',
           'tools/train_baseline.py','tools/model_evaluate.py','tools/evaluate.mjs','sites/src/analyzer.mjs']
    for path in paths:
        raw=subprocess.check_output(['git','hash-object','--no-filters',path],cwd=root,text=True).strip()
        stored=subprocess.check_output(['git','hash-object','--path',path,path],cwd=root,text=True,stderr=subprocess.PIPE).strip()
        assert raw==stored, f'Git filters change frozen evidence bytes: {path}'


def evidence_path(root, value):
    return root / value.replace('\\','/')


def test_frozen_humanizer_snapshots_and_reassessed_report_hashes_match():
    root=Path(__file__).resolve().parents[1]
    snapshots=json.loads((root/'data/humanizer/frozen-backend-snapshots.json').read_text(encoding='utf8'))
    for item in snapshots.values():
        assert hashlib.sha256(evidence_path(root,item['snapshot']).read_bytes()).hexdigest()==item['sha256']
    reassessed=json.loads((root/'data/humanizer/reassessment-v2.json').read_text(encoding='utf8'))
    for item in reassessed['source_reports']:
        assert hashlib.sha256(evidence_path(root,item['path']).read_bytes()).hexdigest()==item['sha256']


def test_all_72_frozen_requests_and_their_historical_validators_are_preserved():
    root=Path(__file__).resolve().parents[1]
    report=json.loads((root/'data/humanizer/request-replay-v2.json').read_text(encoding='utf8'))
    assert report['new_model_requests'] is False and len(report['rows'])==72
    for item in report['rows']:
        assert item['byte_identical'] is True
        assert item['recorded_request_sha256']==item['current_request_sha256']
        assert hashlib.sha256(evidence_path(root,item['report']).read_bytes()).hexdigest()==item['report_sha256']
    # "current" in this frozen V3 report meant the validator at its recorded
    # time. Bind it to immutable snapshots so a runtime refactor cannot silently
    # redefine historical evidence, and do not claim it verifies today's code.
    for path, expected in report['validator_sha256'].items():
        stem=Path(path.replace('\\','/')).stem
        snapshot=root/'data/humanizer/backend-snapshots'/f'{stem}-{expected}.py'
        assert hashlib.sha256(snapshot.read_bytes()).hexdigest()==expected
