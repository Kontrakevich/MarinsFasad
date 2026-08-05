from fastapi.testclient import TestClient

from app.ai_engine import OpenRouterImageEngine
from app.main import app

client = TestClient(app)


def test_health():
    response = client.get('/api/health')
    assert response.status_code == 200
    payload = response.json()
    assert payload['version'] == '0.8.0'
    assert payload['runtime'] == 'standalone-v080'
    assert payload['transport_policy'] == 'provider-aware-temporary-copy'
    assert OpenRouterImageEngine.transport_engine_version == '2.1.0'


def test_project_create_and_list():
    created = client.post('/api/projects', data={'name': 'Test project'})
    assert created.status_code == 200
    project_id = created.json()['id']
    listing = client.get('/api/projects').json()
    assert any(item['id'] == project_id for item in listing)
