"""Measure real local HTTP and ASGI integration overhead, not model inference speed."""
import asyncio
from collections import Counter
import json
import math
import os
from pathlib import Path
import platform
import sys
import time

import httpx
import psutil

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.main import Settings, create_app


def timing(values):
    ordered = sorted(values)
    return {'samples':len(values),'p50Ms':ordered[math.ceil(len(values)*.5)-1], 'p95Ms':ordered[math.ceil(len(values)*.95)-1], 'maxMs':ordered[-1]}


async def batch(client, path, count, payload=None):
    durations, statuses = [], Counter()
    async def one():
        start = time.perf_counter()
        response = await (client.get(path) if payload is None else client.post(path,json=payload))
        durations.append((time.perf_counter()-start)*1000)
        statuses[response.status_code] += 1
        return response
    responses = await asyncio.gather(*(one() for _ in range(count)))
    return dict(timing(durations),statuses=dict(statuses)), responses


async def main():
    report = {'measuredAt':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'environment':{'python':platform.python_version(),'platform':platform.platform(),'logicalCpus':psutil.cpu_count(),'physicalMemoryBytes':psutil.virtual_memory().total},'modelInferenceMeasured':False}
    async with httpx.AsyncClient(base_url=os.getenv('TEXTLAB_TEST_URL','http://127.0.0.1:8767'),trust_env=False,timeout=10) as client:
        report['realHttpHealthConcurrent40'], responses = await batch(client,'/api/health',40)
        assert all(r.status_code == 200 for r in responses)
        report['realHttpOversizedRewriteConcurrent8'], responses = await batch(client,'/api/rewrite',8,{'text':'x'*8001,'language':'sv'})
        assert all(r.status_code == 422 for r in responses)

    async def echo_model(request):
        body = json.loads(request.content)
        protected = json.loads(body['messages'][-1]['content'])['text']
        # Fixed simulated latency is deliberately excluded from model-quality claims.
        await asyncio.sleep(.01)
        return httpx.Response(200,json={'done':True,'message':{'content':json.dumps({'text':protected})}})

    settings = Settings(provider='ollama',requests_per_minute=10000,max_concurrent=2,daily_token_budget=10_000_000,global_daily_token_budget=20_000_000,app_token='',auth_mode='private',state_db='',environment='development')
    app = create_app(settings,httpx.MockTransport(echo_model))
    rss_before = psutil.Process().memory_info().rss
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app,client=('127.0.0.1',123)),base_url='http://127.0.0.1') as client:
        text=('Vi skriver en text med tydliga förbehåll och kontrollerbara uppgifter. '*130)[:8000]
        durations=[]
        for _ in range(20):
            measured,responses=await batch(client,'/api/rewrite',1,{'text':text,'language':'sv'})
            assert responses[0].status_code==200, responses[0].text
            assert responses[0].json()['text']==text.strip()
            durations.append(measured['p50Ms'])
        report['asgiLongRewriteMockProvider'] = dict(timing(durations),characters=len(text),provider='HTTP mock echo with fixed 10ms delay',qualityEvidence=False)
        report['asgiConcurrentRewriteMockProvider'], responses=await batch(client,'/api/rewrite',8,{'text':text,'language':'sv'})
        statuses=Counter(r.status_code for r in responses)
        assert statuses[200]==2 and statuses[429]==6, dict(statuses)
    report['processRssBytes']={'before':rss_before,'after':psutil.Process().memory_info().rss,'scope':'Entire benchmark process, framework and Python runtime; not isolated per-request allocations'}
    report['modelColdStart']={'status':'not_measured','reason':'Not measured by this integration-overhead harness; use opt-in live-model checks for first-observed latency.'}
    Path('artifacts').mkdir(exist_ok=True)
    Path('artifacts/api-performance.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    asyncio.run(main())
