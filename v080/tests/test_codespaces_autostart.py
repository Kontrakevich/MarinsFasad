from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_devcontainer_autostarts_v081() -> None:
    config = json.loads(
        (REPO_ROOT / ".devcontainer" / "devcontainer.json").read_text("utf-8")
    )
    assert config["name"] == "Marins Facade v0.8.1"
    assert config["postCreateCommand"] == "cd v080 && bash build.sh"
    assert config["postStartCommand"] == "bash v080/start.sh"
    assert config["portsAttributes"]["8070"]["label"].endswith("v0.8.1")


def test_v080_start_uses_single_quality_runtime() -> None:
    start = (REPO_ROOT / "v080" / "start.sh").read_text("utf-8")
    init = (REPO_ROOT / "v080" / "app" / "__init__.py").read_text("utf-8")
    assert 'EXPECTED_TRANSPORT_ENGINE="3.4.0"' in start
    assert 'EXPECTED_PROMPT_CONTRACT="environment-system-v1.7-quality-outpaint"' in start
    assert 'EXPECTED_MODEL="google/gemini-2.5-flash-image"' in start
    assert 'EXPECTED_APP_VERSION="0.8.1"' in start
    assert 'ui_single_window/index.html' in start
    assert 'ui_single_window/styles.css' in start
    assert 'ui_single_window/app-v080.js' in start
    assert 'hybrid-mode-patch.js' in start
    assert 'Skill Engine 3.4.0 verified' in start
    assert 'Generation quality: DRAFT / STANDARD / HIGH / MAXIMUM; default HIGH' in start
    assert 'OUTPAINT seams: tone harmonization + feather only inside missing regions' in start
    assert 'skill_engine' in init
    assert 'stable_engine' not in init
    assert 'provider_policy' not in init
    assert 'selective_policy' not in init
    assert 'missing_region_policy' not in init
