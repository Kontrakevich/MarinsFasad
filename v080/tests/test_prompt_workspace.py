from fastapi.testclient import TestClient

from app.main import _clear_job, _set_job, app


client = TestClient(app)


def _create(name: str) -> str:
    response = client.post("/api/projects", data={"name": name})
    assert response.status_code == 200
    return response.json()["id"]


def test_environment_prompt_exposes_concise_nano_banana_prompt_and_internal_contract() -> None:
    project_id = _create("Prompt adapter")
    client.post(
        f"/api/projects/{project_id}/comments/environment",
        data={"comment": "Удали столбы и провода."},
    )

    response = client.get(f"/api/projects/{project_id}/prompt/environment")
    assert response.status_code == 200
    payload = response.json()

    assert payload["prompt"].startswith("NANO BANANA EXECUTION PROMPT v1")
    assert "Удали столбы и провода." in payload["prompt"]
    assert "SYSTEM PRESERVATION CONTRACT" not in payload["prompt"]
    assert "SYSTEM PRESERVATION CONTRACT" in payload["internal_prompt"]
    assert payload["prompt_source"] == "nano-banana-adapted"
    assert payload["nano_banana_prompt_adapter_version"] == "1.0.0"


def test_manual_provider_prompt_override_is_used_until_source_prompt_changes() -> None:
    project_id = _create("Prompt edit")
    client.post(
        f"/api/projects/{project_id}/comments/environment",
        data={"comment": "Дорисуй отсутствующее окружение."},
    )
    base = client.get(f"/api/projects/{project_id}/prompt/environment").json()
    edited = base["prompt"] + "\n\nMANUAL NOTE\nPreserve the exact pavement texture."

    saved = client.post(
        f"/api/projects/{project_id}/prompt/environment/edit",
        data={"prompt": edited},
    )
    assert saved.status_code == 200
    assert saved.json()["prompt_source"] == "manual-provider-override"

    current = client.get(f"/api/projects/{project_id}/prompt/environment").json()
    assert current["prompt"] == edited
    assert current["prompt_override_active"] is True

    client.post(
        f"/api/projects/{project_id}/comments/environment",
        data={"comment": "Добавь ещё одно требование."},
    )
    rebuilt = client.get(f"/api/projects/{project_id}/prompt/environment").json()
    assert rebuilt["prompt"] != edited
    assert rebuilt["prompt_override_active"] is False
    assert rebuilt["prompt_override_stale"] is True


def test_prompt_override_can_be_reset() -> None:
    project_id = _create("Prompt reset")
    base = client.get(f"/api/projects/{project_id}/prompt/environment").json()
    edited = base["prompt"] + "\nManual edit"
    client.post(
        f"/api/projects/{project_id}/prompt/environment/edit",
        data={"prompt": edited},
    )

    reset = client.delete(f"/api/projects/{project_id}/prompt/environment/edit")
    assert reset.status_code == 200
    assert reset.json()["prompt_source"] == "nano-banana-adapted"
    assert reset.json()["prompt"] != edited


def test_project_can_be_deleted_when_idle() -> None:
    project_id = _create("Delete me")
    deleted = client.delete(f"/api/projects/{project_id}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert client.get(f"/api/projects/{project_id}").status_code == 404


def test_project_deletion_is_blocked_during_generation() -> None:
    project_id = _create("Busy project")
    _set_job(project_id, job_id="test-job", status="processing")
    try:
        response = client.delete(f"/api/projects/{project_id}")
        assert response.status_code == 409
        assert client.get(f"/api/projects/{project_id}").status_code == 200
    finally:
        _clear_job(project_id)
        client.delete(f"/api/projects/{project_id}")


def test_workspace_controls_are_bundled() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    patch = (root / "ui_single_window" / "workspace-controls-patch.js").read_text("utf-8")
    assert "save-prompt-edit" in patch
    assert "rebuild-prompt" in patch
    assert "delete-project" in patch
    assert "contentEditable" in patch
