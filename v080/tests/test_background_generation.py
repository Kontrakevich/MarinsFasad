from pathlib import Path

from fastapi.testclient import TestClient

import app.main as main_module
from app.main import _generation_jobs, _generation_jobs_lock, app, projects


ROOT = Path(__file__).resolve().parents[1]
client = TestClient(app)


def test_environment_generation_uses_background_job_and_short_status_requests():
    main = (ROOT / "app" / "main.py").read_text("utf-8")

    assert "threading.Thread(" in main
    assert 'status_code=202' in main
    assert '/environment/generation-status' in main
    assert '"generation_mode": "background-job-polling"' in main
    assert '"environment_input": "approved-geometry-only"' in main
    assert "def _run_environment_generation" in main


def test_generation_start_returns_202_without_waiting_for_provider(monkeypatch):
    project = projects.create("Async generation test")
    project_id = project["id"]
    state = projects.read(project_id)
    state["pipeline"]["geometry"] = "approved"
    state["pipeline"]["environment"] = "ready"
    state["geometry"] = {"status": "approved"}
    state["assets"]["geometry_candidate"] = "images/stages/geometry/candidate.png"
    state["master_canvas"] = {"width": 1200, "height": 900}
    projects.write(project_id, state)

    monkeypatch.setattr(
        main_module,
        "_run_environment_generation",
        lambda project_id, job_id: None,
    )
    with _generation_jobs_lock:
        _generation_jobs.pop(project_id, None)

    response = client.post(f"/api/projects/{project_id}/environment/generate")
    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "queued"
    assert payload["job_id"]
    assert payload["status_url"].endswith("/environment/generation-status")

    stored = projects.read(project_id)
    assert stored["generation"]["input"] == "approved-geometry-only"
    assert stored["generation"]["outpaint_detection"] == "automatic"
    assert "geometry_outpaint_mask" not in stored["assets"]

    status = client.get(payload["status_url"])
    assert status.status_code == 200
    assert status.json()["status"] == "queued"


def test_environment_generation_worker_persists_success_and_failure_states():
    main = (ROOT / "app" / "main.py").read_text("utf-8")

    assert '"EnvironmentGenerationQueued"' in main
    assert '"EnvironmentGenerationCompleted"' in main
    assert '"EnvironmentGenerationFailed"' in main
    assert 'state["pipeline"]["environment"] = "processing"' in main
    assert 'state["pipeline"]["environment"] = "error"' in main
    assert "OutpaintPlanEngine" in main
    assert "geometry_outpaint_mask" not in main
