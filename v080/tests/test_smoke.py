from fastapi.testclient import TestClient

from app.ai_engine import OpenRouterImageEngine
from app.main import app
from app.system_prompts import ENVIRONMENT_SYSTEM_PROMPT, PROMPT_CONTRACT_VERSION

client = TestClient(app)


def test_health():
    response = client.get('/api/health')
    assert response.status_code == 200
    payload = response.json()
    assert payload['version'] == '0.8.1'
    assert payload['runtime'] == 'standalone-v080'
    assert payload['generation_mode'] == 'background-job-polling'
    assert payload['image_model'] == 'google/gemini-2.5-flash-image'
    assert payload['environment_input'] == 'approved-geometry-only'
    assert payload['outpaint_detection'] == 'automatic-from-approved-geometry'

    engine = OpenRouterImageEngine()
    assert OpenRouterImageEngine.transport_engine_version == '3.3.0'
    assert engine.required_model == 'google/gemini-2.5-flash-image'
    assert engine.default_generation_mode == 'hybrid'
    assert engine.available_generation_modes == ('hybrid', 'relight', 'edit', 'outpaint')
    assert engine.skill_contract_version == 'outpaint-relight-edit-hybrid-v1'
    assert engine.environment_input_policy == 'approved-geometry-only'
    assert engine.outpaint_detection_policy == 'automatic-from-approved-geometry-transparency'
    assert engine.user_mask_required is False
    assert engine.internal_outpaint_tiles_allowed is False
    assert engine.provider_input_policy == 'single-approved-geometry-reference'
    assert engine.outpaint_qc_blocking is True
    assert engine.outpaint_qc_policy == 'reject-solid-white-black-placeholder'
    assert engine.missing_region_transport_policy == 'native-transparency-single-reference'
    assert engine.outpaint_repair_mode == 'hybrid-second-pass'
    assert ENVIRONMENT_SYSTEM_PROMPT
    assert PROMPT_CONTRACT_VERSION == 'environment-system-v1.6-skill-contracts'


def test_project_create_and_list():
    created = client.post('/api/projects', data={'name': 'Test project'})
    assert created.status_code == 200
    project_id = created.json()['id']
    listing = client.get('/api/projects').json()
    assert any(item['id'] == project_id for item in listing)
