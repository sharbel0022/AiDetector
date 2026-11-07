import json
from collections import Counter
import httpx
import pytest
from fastapi.testclient import TestClient
from backend.main import create_app, Settings, protect_text, restore_text, PreservationError

TEXT='Vi betalade 1 250,50 kr den 2026-11-02. Rapporten [12] säger ”Det fungerar”. Läs https://example.org/kalla.'

def cfg(**kwargs):
    return Settings(**kwargs)

def transport_for(rewrite):
    def handler(request):
        body=json.loads(request.content)
        protected=json.loads(body['messages'][-1]['content'])['text']
        return httpx.Response(200,json={'done':True,'message':{'content':json.dumps({'text':rewrite(protected)})}})
    return httpx.MockTransport(handler)

def client(**kwargs):
    return TestClient(create_app(cfg(),transport=transport_for(lambda t:t.replace('Vi betalade','Vi har betalat')),**kwargs))

def test_protected_values_roundtrip():
    protected, mapping=protect_text(TEXT)
    assert '1 250,50' not in protected
    assert 'https://example.org/kalla' not in protected
    assert restore_text(protected,mapping,TEXT)==TEXT

@pytest.mark.parametrize('kind',['delete','duplicate','invent'])
def test_changed_protected_tokens_rejected(kind):
    protected,mapping=protect_text(TEXT)
    key=next(iter(mapping))
    altered=protected.replace(key,'') if kind=='delete' else protected+(' '+key if kind=='duplicate' else ' 777')
    with pytest.raises(PreservationError):restore_text(altered,mapping,TEXT)

def test_empty_model_output_rejected():
    with pytest.raises(PreservationError):restore_text('',{},'hello')

def test_health_has_no_secrets():
    c=TestClient(create_app(cfg(app_token='top-secret-token')))
    r=c.get('/api/health')
    assert r.status_code==200
    assert 'top-secret-token' not in r.text
    assert r.json()['auth_required'] is True

def test_valid_rewrite_uses_model_and_returns_diff():
    with client() as c:
        r=c.post('/api/rewrite',json={'text':TEXT,'tone':'natural','language':'sv'})
        assert r.status_code==200, r.text
        data=r.json()
        assert data['text'].startswith('Vi har betalat')
        assert data['review_required'] is True
        assert data['provider']=='ollama'
        assert any(x['kind']=='insert' for x in data['diff'])
        assert '1 250,50' in data['text']

def test_preservation_failure_not_returned_as_success():
    app=create_app(cfg(),transport=transport_for(lambda t:t+' 9999'))
    with TestClient(app) as c:
        r=c.post('/api/rewrite',json={'text':TEXT})
        assert r.status_code==502
        assert '9999' not in r.text

@pytest.mark.parametrize('text',['','   ','x'*8001])
def test_input_validation(text):
    with client() as c:
        r=c.post('/api/rewrite',json={'text':text})
        assert r.status_code==422
        assert 'input' not in r.json()

def test_validation_does_not_echo_private_text():
    with client() as c:
        r=c.post('/api/rewrite',json={'text':'PRIVATE-MESSAGE','tone':'invalid'})
        assert r.status_code==422
        assert 'PRIVATE-MESSAGE' not in r.text

def test_explicit_token_enforced():
    app=create_app(cfg(app_token='test-token'),transport=transport_for(lambda t:t))
    with TestClient(app) as c:
        assert c.post('/api/rewrite',json={'text':TEXT}).status_code==401
        assert c.post('/api/rewrite',json={'text':TEXT},headers={'Authorization':'Bearer test-token'}).status_code==200

def test_remote_requests_require_configured_authentication():
    with TestClient(create_app(cfg()),client=('203.0.113.10',1234)) as c:
        assert c.post('/api/rewrite',json={'text':TEXT}).status_code==403

def test_untrusted_origin_blocked():
    with client() as c:
        r=c.post('/api/rewrite',json={'text':TEXT},headers={'Origin':'https://evil.example'})
        assert r.status_code==403

def test_body_limit():
    with client() as c:
        assert c.post('/api/rewrite',content='x'*100001,headers={'Content-Type':'application/json'}).status_code==413

def test_missing_cloud_config_is_not_fake_ai():
    with TestClient(create_app(cfg(provider='openai',model=''))) as c:
        r=c.post('/api/rewrite',json={'text':TEXT})
        assert r.status_code==503

def test_provider_error_is_sanitized():
    def fail(request):return httpx.Response(500,text='SECRET upstream details')
    with TestClient(create_app(cfg(),transport=httpx.MockTransport(fail))) as c:
        r=c.post('/api/rewrite',json={'text':TEXT})
        assert r.status_code==502
        assert 'SECRET' not in r.text

def test_provider_timeout():
    def fail(request):raise httpx.ReadTimeout('private input')
    with TestClient(create_app(cfg(),transport=httpx.MockTransport(fail))) as c:
        assert c.post('/api/rewrite',json={'text':TEXT}).status_code==504

def test_malformed_model_json():
    tr=httpx.MockTransport(lambda r:httpx.Response(200,json={'done':True,'message':{'content':'not json'}}))
    with TestClient(create_app(cfg(),transport=tr)) as c:
        assert c.post('/api/rewrite',json={'text':TEXT}).status_code==502

def test_rate_limit():
    app=create_app(cfg(requests_per_minute=2),transport=transport_for(lambda t:t))
    with TestClient(app) as c:
        assert c.post('/api/rewrite',json={'text':TEXT}).status_code==200
        assert c.post('/api/rewrite',json={'text':TEXT}).status_code==200
        assert c.post('/api/rewrite',json={'text':TEXT}).status_code==429

def test_production_fails_without_token():
    with pytest.raises(ValueError):create_app(cfg(environment='production'))

def test_host_validation():
    with client() as c:
        assert c.get('/api/health',headers={'Host':'evil.example'}).status_code==400

def test_no_cache_headers():
    with client() as c:
        r=c.get('/api/health')
        assert r.headers['cache-control']=='no-store'
        assert r.headers['x-content-type-options']=='nosniff'

def test_openai_protocol_and_no_store():
    def handler(request):
        assert request.url.host=='api.openai.com'
        if request.method == 'GET':
            assert request.url.path == '/v1/models/test-model'
            assert not request.content
            return httpx.Response(200, json={'id':'test-model'})
        body=json.loads(request.content)
        assert body['store'] is False
        assert body['text']['format']['type']=='json_schema'
        protected=json.loads(body['input'])['text']
        return httpx.Response(200,json={'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps({'text':protected})}]}]})
    with TestClient(create_app(cfg(provider='openai',model='test-model',openai_key='test-key'),transport=httpx.MockTransport(handler))) as c:
        r=c.post('/api/rewrite',json={'text':TEXT})
        assert r.status_code==200,r.text
        assert r.json()['provider']=='openai'

def test_numbers_in_identifiers_are_protected():
    text='Vi använder Python3 och version v2.7 i projektet.'
    protected,mapping=protect_text(text)
    assert 'Python3' not in protected
    assert restore_text(protected,mapping,text)==text

def test_many_protected_values_have_a_prompt_size_limit():
    with client() as c:
        r=c.post('/api/rewrite',json={'text':'1; '*2000})
        assert r.status_code==422

def test_non_ascii_access_token_is_handled_safely():
    app=create_app(cfg(app_token='kod-åäö'),transport=transport_for(lambda t:t))
    with TestClient(app) as c:
        r=c.post('/api/rewrite',json={'text':TEXT},headers=[(b'Authorization','Bearer kod-åäö'.encode())])
        assert r.status_code in (200,401)

def test_incomplete_openai_output_rejected():
    tr=httpx.MockTransport(lambda r:httpx.Response(200,json={'status':'incomplete','output':[]}))
    with TestClient(create_app(cfg(provider='openai',model='test-model',openai_key='test-key'),transport=tr)) as c:
        assert c.post('/api/rewrite',json={'text':TEXT}).status_code==502

def test_remote_http_ollama_is_not_allowed():
    with pytest.raises(ValueError):create_app(cfg(ollama_url='http://unsafe.example'))
