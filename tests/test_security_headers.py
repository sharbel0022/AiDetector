from fastapi.testclient import TestClient
from backend.main import Settings, create_app


def test_content_security_policy_restricts_execution_and_embedding():
    with TestClient(create_app(Settings())) as client:
        for route in ['/api/health','/api/missing']:
            response=client.get(route)
            policy=response.headers.get('Content-Security-Policy','')
            assert "script-src 'self'" in policy
            assert "object-src 'none'" in policy
            assert "base-uri 'none'" in policy
            assert "frame-ancestors 'none'" in policy
            assert "script-src 'self' 'unsafe-inline'" not in policy
            assert "connect-src 'self' https:" in policy
