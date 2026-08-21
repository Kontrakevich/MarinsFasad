from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_saved_edit_mode_reaches_environment_prompt_without_leaking_control_comment():
    created = client.post('/api/projects', data={'name': 'Hybrid mode backend'})
    assert created.status_code == 200
    project_id = created.json()['id']

    mode = client.post(
        f'/api/projects/{project_id}/comments/environment',
        data={'comment': '__MARINS_GENERATION_MODE__:edit'},
    )
    assert mode.status_code == 200
    comment = client.post(
        f'/api/projects/{project_id}/comments/environment',
        data={'comment': 'Убрать столбы и провода, сделать погоду пасмурной.'},
    )
    assert comment.status_code == 200

    compiled = client.get(f'/api/projects/{project_id}/prompt/environment')
    assert compiled.status_code == 200
    payload = compiled.json()
    assert payload['generation_mode'] == 'edit'
    assert 'GENERATION MODE\nEDIT' in payload['prompt']
    assert '__MARINS_GENERATION_MODE__' not in payload['prompt']
    assert 'Убрать столбы и провода' in payload['prompt']


def test_last_saved_mode_wins():
    created = client.post('/api/projects', data={'name': 'Mode switch backend'})
    project_id = created.json()['id']
    for mode in ('edit', 'outpaint', 'hybrid'):
        response = client.post(
            f'/api/projects/{project_id}/comments/environment',
            data={'comment': f'__MARINS_GENERATION_MODE__:{mode}'},
        )
        assert response.status_code == 200

    compiled = client.get(f'/api/projects/{project_id}/prompt/environment').json()
    assert compiled['generation_mode'] == 'hybrid'
    assert 'GENERATION MODE\nHYBRID' in compiled['prompt']
