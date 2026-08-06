from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_devcontainer_autostarts_v080() -> None:
    config = json.loads(
        (REPO_ROOT / ".devcontainer" / "devcontainer.json").read_text("utf-8")
    )
    assert config["name"] == "Marins Facade v0.8.0"
    assert config["postCreateCommand"] == "cd v080 && bash build.sh"
    assert config["postStartCommand"] == "bash v080/start.sh"
    assert config["portsAttributes"]["8070"]["label"].endswith("v0.8.0")
    assert "release/start_v060.sh" not in config["postStartCommand"]


def test_legacy_codespaces_launchers_redirect_to_v080() -> None:
    start = (REPO_ROOT / "release" / "start_v060.sh").read_text("utf-8")
    setup = (REPO_ROOT / "release" / "setup_v060.sh").read_text("utf-8")
    assert 'exec bash "$ROOT/v080/start.sh"' in start
    assert 'exec bash "$ROOT/v080/build.sh"' in setup


def test_v080_start_synchronizes_current_ui() -> None:
    start = (REPO_ROOT / "v080" / "start.sh").read_text("utf-8")
    assert 'EXPECTED_TRANSPORT_ENGINE="2.7.1"' in start
    assert 'EXPECTED_PROMPT_CONTRACT="environment-system-v1.3"' in start
    assert 'EXPECTED_MODEL="google/gemini-2.5-flash-image"' in start
    assert 'ui_single_window/index.html' in start
    assert 'ui_single_window/styles.css' in start
    assert 'ui_single_window/app-v080.js' in start
    assert 'rm -f /tmp/marins-facade-v060.pid' in start
    assert 'Edit mode: exact local changes with soft-clamped delta compositing' in start
    assert 'Base image: pixel-preserved outside final edit area' in start
    assert 'Global regeneration: suppressed instead of rejected' in start
