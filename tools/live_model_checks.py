"""Opt-in real Ollama smoke using synthetic text; no model downloads or mocks.

Run: python tools/live_model_checks.py --models llama3.2:3b --output artifacts/live-model-results.json
This makes real local model requests. It measures transport/preservation, not meaning.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from backend.main import MODES, Settings, create_app


SOURCES = {
    'sv': 'Åsa Öberg skrev rapporten den 2 november 2026 för Projekt Orion. Teamet testade 12 sensorer och minskade energianvändningen med 15 %. Rapporten [Öberg, 2026] säger ”Resultaten är preliminära”. Mer information finns på https://example.org/studie. Syftet är att förklara de uppmätta förändringarna tydligt utan att dra säkra slutsatser om orsaken.',
    'en': 'Alice Smith wrote the report on 2 November 2026 for Project Orion. The team tested 12 sensors and reduced energy use by 15 %. The report [Smith, 2026] states "The results are preliminary". More information is available at https://example.org/study. The aim is to explain the measured changes clearly without drawing firm conclusions about their cause.',
}
EXACT = {
    'sv': ['Åsa Öberg', '2 november 2026', 'Projekt Orion', '12', '15 %', '[Öberg, 2026]', '”Resultaten är preliminära”', 'https://example.org/studie'],
    'en': ['Alice Smith', '2 November 2026', 'Project Orion', '12', '15 %', '[Smith, 2026]', '"The results are preliminary"', 'https://example.org/study'],
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models', nargs='+', default=['llama3.2:3b'])
    parser.add_argument('--modes', nargs='+', choices=list(MODES), default=list(MODES))
    parser.add_argument('--languages', nargs='+', choices=list(SOURCES), default=list(SOURCES))
    parser.add_argument('--output', default='artifacts/live-model-results.json')
    args = parser.parse_args()
    report = {'timestamp_utc': datetime.now(timezone.utc).isoformat(), 'provider': 'ollama',
              'real_model_requests': True, 'synthetic_inputs_only': True, 'semantic_quality_verified': False,
              'latency_note': 'First observed call is measured; model unloading/cold start is not asserted.',
              'models': []}
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    for model in args.models:
        settings = Settings(provider='ollama', model=model, requests_per_minute=100,
                            auth_mode='private', app_token='', state_db='', environment='development')
        entry = {'model': model, 'rewrites': []}
        report['models'].append(entry)
        with TestClient(create_app(settings)) as client:
            start = time.perf_counter()
            status = client.get('/api/provider-status')
            entry['first_observed_call_seconds'] = round(time.perf_counter() - start, 3)
            entry['readiness'] = {'http_status': status.status_code, **status.json()}
            print(json.dumps({'model': model, 'readiness': entry['readiness'], 'seconds': entry['first_observed_call_seconds']}, ensure_ascii=True), flush=True)
            # Readiness has a smaller time/output allowance than a rewrite. A model
            # can exceed its probe deadline yet still produce a bounded rewrite.
            for language in args.languages:
                for mode in args.modes:
                    start = time.perf_counter()
                    response = client.post('/api/rewrite', json={'text': SOURCES[language], 'tone': mode, 'language': language})
                    body = response.json()
                    output = body.get('text', '')
                    result = {'language': language, 'mode': mode, 'seconds': round(time.perf_counter() - start, 3),
                              'http_status': response.status_code, 'input': SOURCES[language], 'output': output,
                              'exact_values_preserved': all(output.count(term) == SOURCES[language].count(term) for term in EXACT[language]) if response.status_code == 200 else False,
                              'changed': output != SOURCES[language] if response.status_code == 200 else None,
                              'response': body}
                    entry['rewrites'].append(result)
                    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
                    print(json.dumps({k: result[k] for k in ['language', 'mode', 'seconds', 'http_status', 'exact_values_preserved', 'changed']}), flush=True)
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(str(destination.resolve()))
    passed = all(model['readiness'].get('ready') is True and model['readiness'].get('verified') is True
                 and all(result['http_status'] == 200 and result['exact_values_preserved'] for result in model['rewrites'])
                 for model in report['models'])
    report['passed'] = passed
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    raise SystemExit(0 if passed else 1)


if __name__ == '__main__':
    main()
