from fastapi.testclient import TestClient

from app.ai_engine import OpenRouterImageEngine
from app.main import app
from app.system_prompts import ENVIRONMENT_SYSTEM_PROMPT, PROMPT_CONTRACT_VERSION

client = TestClient(app)


def test_health():
    response = client.get('/api/health')
    assert response.status_code == 200
    payload = response.json()
    assert payload['version'] == '0.8.0'
    assert payload['runtime'] == 'standalone-v080'
    assert payload['transport_policy'] == 'provider-aware-temporary-copy'
    assert payload['generation_mode'] == 'background-job-polling'
    assert payload['image_model'] == 'google/gemini-2.5-flash-image'
    assert payload['environment_input'] == 'approved-geometry-only'
    assert payload['outpaint_detection'] == 'automatic-from-approved-geometry'
    assert OpenRouterImageEngine.transport_engine_version == '2.9.0'
    assert OpenRouterImageEngine.required_model == 'google/gemini-2.5-flash-image'
    assert OpenRouterImageEngine.environment_input_policy == 'approved-geometry-only'
    assert OpenRouterImageEngine.outpaint_detection_policy == 'automatic-from-approved-geometry-transparency'
    assert OpenRouterImageEngine.user_mask_required is False
    assert OpenRouterImageEngine.provider_input_policy == 'single-approved-geometry-reference'
    assert OpenRouterImageEngine.outpaint_repair_mode == 'component-tiles'
    assert OpenRouterImageEngine.outpaint_tile_max_calls == 8
    assert OpenRouterImageEngine.default_transmit_max_request_bytes == 32 * 1024 * 1024
    assert OpenRouterImageEngine._select_provider_size(8064, 6048) == (1536, 1024)
    assert ENVIRONMENT_SYSTEM_PROMPT
    assert PROMPT_CONTRACT_VERSION == 'environment-system-v1.4'


def test_project_create_and_list():
    created = client.post('/api/projects', data={'name': 'Test project'})
    assert created.status_code == 200
    project_id = created.json()['id']
    listing = client.get('/api/projects').json()
    assert any(item['id'] == project_id for item in listing)
    assert all('geometry_outpaint_mask' not in item.get('assets', {}) for item in listing)
