"""Verify a disposable, loopback-only production container with two workers."""
import argparse
from collections import Counter
import concurrent.futures
import hashlib
import json
from pathlib import Path
import secrets
import subprocess
import time
import urllib.error
import urllib.request


def docker(*args):
    return subprocess.check_output(['docker', *args],text=True).strip()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',default='textlab:v3-review')
    args=parser.parse_args()
    name='textlab-check-'+secrets.token_hex(5)
    token=secrets.token_urlsafe(32)
    digest=hashlib.sha256(token.encode()).hexdigest()
    report={'image':args.image,'published':False,'checks':[],'modelsTested':False}
    try:
        docker('run','--rm','-d','--name',name,'-p','127.0.0.1::8767',
               '-e','TEXTLAB_AUTH_MODE=multiuser',
               '-e','TEXTLAB_USER_TOKENS='+json.dumps({'container-reviewer':digest}),
               '-e','ALLOWED_HOSTS=127.0.0.1,localhost',
               '-e','ALLOWED_ORIGINS=http://127.0.0.1',
               '-e','TEXTLAB_REQUESTS_PER_MINUTE=2',args.image)
        address=docker('port',name,'8767/tcp').splitlines()[0]
        url='http://'+address
        for _ in range(60):
            try:
                with urllib.request.urlopen(url+'/api/health',timeout=1) as response:
                    health=json.load(response)
                    assert health['version']=='3.0.0' and health['auth_required']
                break
            except (urllib.error.URLError,ConnectionError,TimeoutError):
                time.sleep(.2)
        else:
            raise AssertionError('Production container did not become healthy')
        report['checks'].append('Production config starts and reports v3 authenticated health')
        assert docker('exec',name,'id','-u')=='10001'
        report['checks'].append('Server runs as nonroot UID 10001')
        processes=docker('top',name,'-eo','pid,args')
        workers=sum('spawn_main' in line for line in processes.splitlines())
        assert workers==2, f'Expected two worker processes, got {workers}'
        report['workers']=workers
        with urllib.request.urlopen(url,timeout=2) as response:
            assert b'TextLab' in response.read()
            assert response.headers.get('X-Content-Type-Options')=='nosniff'
            assert response.headers.get('Content-Security-Policy')
        report['checks'].append('Built frontend and security headers served')
        try:
            urllib.request.urlopen(url+'/api/provider-status',timeout=2)
            raise AssertionError('Anonymous request was allowed')
        except urllib.error.HTTPError as exc:
            assert exc.code==401
        report['checks'].append('Anonymous protected endpoint rejected with 401')
        def request(_):
            req=urllib.request.Request(url+'/api/provider-status',headers={'Authorization':'Bearer '+token})
            try:
                with urllib.request.urlopen(req,timeout=20) as response:
                    return response.status
            except urllib.error.HTTPError as exc:
                return exc.code
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
            counts=Counter(pool.map(request,range(12)))
        assert counts=={200:2,429:10}, dict(counts)
        report['sharedRateStatuses']=dict(counts)
        report['checks'].append('Two production workers share per-user quota: 2 accepted, 10 rate limited')
        report['passed']=True
    finally:
        subprocess.run(['docker','rm','--force',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
        Path('artifacts').mkdir(exist_ok=True)
        Path('artifacts/container-results.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
