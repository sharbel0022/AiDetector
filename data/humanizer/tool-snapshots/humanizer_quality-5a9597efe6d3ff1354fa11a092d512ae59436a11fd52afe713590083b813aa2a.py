"""Opt-in real Ollama challenge matrix; bounded claim checks are not semantic proof.

python tools/humanizer_quality.py --label baseline --models llama3.2:3b qwen3.5:4b
The default matrix is frozen sv/en development + heldout sources, all six modes.
No model download, no LLM judge, no provider secrets or production budget changes.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FIXTURES = ROOT / 'data/humanizer/challenges.json'


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_cases(path=FIXTURES):
    return json.loads(Path(path).read_text(encoding='utf-8'))['cases']


def assess_case(case, output):
    """Recognize preregistered surface realizations; absence means unassessed.

    A passing pattern does not prove a claim is true or exclude other added facts.
    These checks never influence production acceptance or silently repair output.
    """
    claims = []
    for claim in case['claims']:
        positive = any(re.search(pattern, output, re.I | re.S) for pattern in claim['any'])
        forbidden = any(re.search(pattern, output, re.I | re.S) for pattern in claim.get('forbidden', []))
        claims.append({'id': claim['id'], 'description': claim['description'],
                       'status': 'contradicted_pattern' if forbidden else 'supported_pattern' if positive else 'unassessed'})
    exact = all(output.count(value) == case['text'].count(value) for value in case['exact_values'])
    return {'exact_values_preserved': exact, 'claims': claims,
            'all_bounded_checks_pass': bool(output) and exact and all(c['status'] == 'supported_pattern' for c in claims),
            'semantic_equivalence_verified': False, 'no_added_facts_verified': False,
            'manual_review_required': ['all claims and relations', 'added facts', 'language quality', 'mode fidelity']}


def mode_summary(rows):
    sources = {}
    for row in rows:
        group = sources.setdefault(row['case_id'], [])
        group.append(row)
    return {'unchanged_count': sum(row['http_status'] == 200 and row['output'] == row['input'] for row in rows),
            'by_source': {key: {'successful_modes': [r['mode'] for r in group if r['http_status'] == 200],
                                'distinct_successful_outputs': len({r['output'] for r in group if r['http_status'] == 200}),
                                'all_six_modes_distinct': len({r['output'] for r in group if r['http_status'] == 200}) == 6,
                                'word_count_ratios': {r['mode']: round(len(r['output'].split()) / len(r['input'].split()), 3)
                                                      for r in group if r['http_status'] == 200}}
                          for key, group in sources.items()},
            'limitation': 'Distinct output and length are observable behavior, not proof of tone quality.'}


class RecordingOllama(httpx.AsyncBaseTransport):
    """Record local synthetic-only request/response bodies at the actual boundary."""
    def __init__(self):
        self.exchanges = []

    async def handle_async_request(self, request):
        body = json.loads(request.content)
        if request.url.host not in ('127.0.0.1', 'localhost', '::1'):
            raise ValueError('This evidence collector is local-only')
        async with httpx.AsyncClient(timeout=300, trust_env=False) as client:
            response = await client.post(str(request.url), json=body)
        self.exchanges.append({'request': body, 'http_status': response.status_code,
                               'response': response.json(),
                               'request_sha256': hashlib.sha256(request.content).hexdigest()})
        return httpx.Response(response.status_code, content=response.content, headers=response.headers)


def main():
    from fastapi.testclient import TestClient
    from backend.main import MODES, Settings, create_app, protect_text
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models', nargs='+', default=['llama3.2:3b', 'qwen3.5:4b'])
    parser.add_argument('--label', required=True)
    parser.add_argument('--split', choices=['all', 'development', 'heldout'], default='all')
    parser.add_argument('--output')
    args = parser.parse_args()
    destination = Path(args.output or ROOT / f'data/humanizer/runs/{args.label}.json')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=20, trust_env=False) as client:
        tags = client.get('http://127.0.0.1:11434/api/tags').json()
        version = client.get('http://127.0.0.1:11434/api/version').json()
    git_head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    report = {'schema': 1, 'label': args.label, 'timestamp_utc': datetime.now(timezone.utc).isoformat(),
              'real_model_requests': True, 'synthetic_inputs_only': True, 'ollama_version': version,
              'git_head': git_head, 'fixtures_sha256': sha256_file(FIXTURES),
              'backend_sha256': {str(p.relative_to(ROOT)): sha256_file(p) for p in sorted((ROOT / 'backend').glob('*.py'))},
              'tool_sha256': sha256_file(__file__), 'models': [],
              'semantic_equivalence_verified': False, 'human_review_completed': False,
              'test_client_limits_note': '300s timeout, 6000 output tokens, 100M daily budgets only in this opt-in process; production defaults unchanged.'}
    for model in args.models:
        installed = next((item for item in tags.get('models', []) if item['name'] == model), None)
        if installed is None:
            raise SystemExit(f'Model not installed: {model}; no download attempted')
        recorder = RecordingOllama()
        settings = Settings(provider='ollama', model=model, requests_per_minute=1000,
                            daily_token_budget=100000000, global_daily_token_budget=100000000,
                            request_timeout=300, max_output_tokens=6000,
                            auth_mode='private', app_token='', state_db='', environment='development')
        entry = {'model': model, 'model_digest': installed['digest'], 'model_details': installed['details'], 'rewrites': []}
        report['models'].append(entry)
        with TestClient(create_app(settings, transport=recorder)) as client:
            for case in load_cases():
                if args.split != 'all' and case['split'] != args.split:
                    continue
                for mode in MODES:
                    _, audit_mapping = protect_text(case['text'], case.get('protected_terms', []))
                    audit_values = {key.rsplit('_', 3)[1]: value for key, value in audit_mapping.items()}
                    start = time.perf_counter()
                    before = len(recorder.exchanges)
                    response = client.post('/api/rewrite', json={'text': case['text'], 'language': case['language'], 'tone': mode,
                                                                'protected_terms': case.get('protected_terms', [])})
                    body = response.json()
                    output = body.get('text', '')
                    row = {'case_id': case['id'], 'split': case['split'], 'language': case['language'], 'mode': mode,
                           'seconds': round(time.perf_counter() - start, 3), 'http_status': response.status_code,
                           'input': case['text'], 'output': output, 'response': body,
                           'assessment': assess_case(case, output), 'exchanges': recorder.exchanges[before:]}
                    # Recover raw candidate for audit even when the production guard rejects it.
                    if row['exchanges']:
                        try:
                            raw = row['exchanges'][-1]['response']['message']['content']
                            model_output = json.loads(raw)
                            row['model_output'] = model_output
                            request_data = json.loads(row['exchanges'][-1]['request']['messages'][-1]['content'])
                            mapping = request_data.get('protected_values') or {
                                key: audit_values[key.rsplit('_', 3)[1]]
                                for key in re.findall(r'__TL_[a-f0-9]{16}_\d+__', request_data['text'])}
                            row['protected_mapping'] = mapping
                            candidate = model_output['text']
                            for key, value in mapping.items():
                                candidate = candidate.replace(key, value)
                            row['raw_candidate'] = candidate
                            row['raw_candidate_assessment'] = assess_case(case, candidate) if '__TL_' not in candidate else None
                        except (KeyError, TypeError, ValueError):
                            pass
                    entry['rewrites'].append(row)
                    entry['mode_behavior'] = mode_summary(entry['rewrites'])
                    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
                    print(json.dumps({k: row[k] for k in ['case_id', 'mode', 'http_status', 'seconds']} | {
                        'checks': row['assessment']['all_bounded_checks_pass'], 'changed': output != case['text'] if output else None}), flush=True)
        entry['counts'] = {'total': len(entry['rewrites']),
                           'accepted': sum(r['http_status'] == 200 for r in entry['rewrites']),
                           'accepted_bounded_checks_pass': sum(r['http_status'] == 200 and r['assessment']['all_bounded_checks_pass'] for r in entry['rewrites']),
                           'rejected': sum(r['http_status'] != 200 for r in entry['rewrites'])}
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(str(destination.resolve()))


if __name__ == '__main__':
    main()
