from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health():
    response = client.get('/api/health')
    assert response.status_code == 200
    assert response.json()['version'] == '0.8.0-dev'


def test_project_create_and_list():
    created = client.post('/api/projects', data={'name': 'Test project'})
    assert created.status_code == 200
    project_id = created.json()['id']
    listing = client.get('/api/projects').json()
    assert any(item['id'] == project_id for item in listing)
