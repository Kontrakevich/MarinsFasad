from pathlib import Path

from app.intelligence.alignment import HumanAlignmentAnalyzer
from app.intelligence.orchestrator import System1Intelligence
from app.intelligence.technical import TechnicalFailureLocalizer
from app.project_engine import ProjectEngine


def _review_state(engine: ProjectEngine, project_id: str, job_id: str) -> dict:
    state = engine.read(project_id)
    state["assets"]["geometry_candidate"] = "images/stages/geometry/candidate.png"
    state["assets"]["environment_candidate"] = "images/stages/environment/candidate.png"
    state["generation"] = {
        "stage": "environment",
        "status": "review",
        "job_id": job_id,
        "model": "google/gemini-2.5-flash-image",
    }
    state["pipeline"]["environment"] = "ready"
    engine.write(project_id, state)
    return engine.read(project_id)


def test_layer1_provider_failure_blocks_layer2(tmp_path: Path) -> None:
    projects = ProjectEngine(tmp_path / "projects")
    project = projects.create("Layer gate")
    project_id = project["id"]
    _review_state(projects, project_id, "job-provider-503")

    projects.record(
        project_id,
        "EnvironmentGenerationQueued",
        {"job_id": "job-provider-503", "model": "google/gemini-2.5-flash-image"},
    )
    projects.record(
        project_id,
        "EnvironmentGenerationFailed",
        {"job_id": "job-provider-503", "error": "OpenRouter HTTP 503: Service unavailable"},
    )
    projects.record(
        project_id,
        "RevisionAdded",
        {"stage": "environment", "text": "Слишком нарядно, нужно спокойнее."},
    )

    intelligence = projects.read(project_id)["system1_intelligence"]
    assert intelligence["layer1_technical"]["status"] == "ROOT_CAUSE_FOUND"
    assert intelligence["layer1_technical"]["failure_type"] == "PROVIDER_OR_GATEWAY_FAILURE"
    assert intelligence["latest_feedback"]["layer2_invoked"] is False
    assert intelligence["latest_feedback"]["analysis"]["status"] == "GATED_BY_LAYER1"
    assert intelligence["layer2_alignment"] is None


def test_layer2_runs_only_after_clean_layer1(tmp_path: Path) -> None:
    projects = ProjectEngine(tmp_path / "projects")
    project = projects.create("Alignment gate")
    project_id = project["id"]
    _review_state(projects, project_id, "job-clean")

    projects.record(project_id, "EnvironmentGenerationQueued", {"job_id": "job-clean"})
    projects.record(project_id, "EnvironmentGenerationCompleted", {"job_id": "job-clean"})
    projects.record(
        project_id,
        "RevisionAdded",
        {"stage": "environment", "text": "Слишком нарядно, уже какой-то Дубай."},
    )

    intelligence = projects.read(project_id)["system1_intelligence"]
    assert intelligence["layer1_technical"]["status"] == "NO_TECHNICAL_ROOT_CAUSE"
    assert intelligence["latest_feedback"]["layer2_invoked"] is True
    assert intelligence["layer2_alignment"]["failure_type"] == "OVERDESIGN"
    assert intelligence["layer2_alignment"]["repair_route"]["automatic_execution"] is False


def test_approval_creates_regression_evidence_not_permanent_rule(tmp_path: Path) -> None:
    projects = ProjectEngine(tmp_path / "projects")
    project = projects.create("Regression")
    project_id = project["id"]
    _review_state(projects, project_id, "job-approved")
    projects.record(project_id, "EnvironmentGenerationQueued", {"job_id": "job-approved"})
    projects.record(project_id, "EnvironmentGenerationCompleted", {"job_id": "job-approved"})
    projects.record(
        project_id,
        "EnvironmentApproved",
        {"asset": "images/stages/environment/candidate.png"},
    )

    intelligence = projects.read(project_id)["system1_intelligence"]
    assert intelligence["counts"]["regressions"] == 1
    assert intelligence["latest_regression"]["status"] == "APPROVED_REFERENCE"
    assert intelligence["counts"]["preferences"] == 0


def test_explicit_rule_becomes_project_candidate_only(tmp_path: Path) -> None:
    projects = ProjectEngine(tmp_path / "projects")
    project = projects.create("Preference")
    project_id = project["id"]
    _review_state(projects, project_id, "job-rule")
    projects.record(project_id, "EnvironmentGenerationQueued", {"job_id": "job-rule"})
    projects.record(project_id, "EnvironmentGenerationCompleted", {"job_id": "job-rule"})
    projects.record(
        project_id,
        "RevisionAdded",
        {"stage": "environment", "text": "Правило: всегда сохранять утвержденную геометрию фасада."},
    )

    intelligence = projects.read(project_id)["system1_intelligence"]
    assert intelligence["counts"]["preferences"] == 1
    assert intelligence["precedence"]["learning"].startswith("approval creates regression evidence")


def test_localizers_keep_layer_contract_explicit() -> None:
    technical = TechnicalFailureLocalizer().analyze(observed_failure="OpenRouter HTTP 503")
    assert technical["root_cause_found"] is True
    alignment = HumanAlignmentAnalyzer().analyze("Внизу получилась заплатка низкого качества.")
    assert alignment["failure_type"] == "QUALITY_EXPECTATION_GAP"
    assert System1Intelligence.version == "1.0.0"
