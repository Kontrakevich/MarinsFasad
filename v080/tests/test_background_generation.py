from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_environment_generation_uses_background_job_and_short_status_requests():
    main = (ROOT / "app" / "main.py").read_text("utf-8")

    assert "threading.Thread(" in main
    assert 'status_code=202' in main
    assert '/environment/generation-status' in main
    assert 'generation_mode": "background-job-polling"' in main
    assert "def _run_environment_generation" in main


def test_environment_generation_worker_persists_success_and_failure_states():
    main = (ROOT / "app" / "main.py").read_text("utf-8")

    assert '"EnvironmentGenerationQueued"' in main
    assert '"EnvironmentGenerationCompleted"' in main
    assert '"EnvironmentGenerationFailed"' in main
    assert 'state["pipeline"]["environment"] = "processing"' in main
    assert 'state["pipeline"]["environment"] = "error"' in main
