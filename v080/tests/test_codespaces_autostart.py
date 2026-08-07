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


def test_v080_start_uses_single_hybrid_runtime() -> None:
    start = (REPO_ROOT / "v080" / "start.sh").read_text("utf-8")
    init = (REPO_ROOT / "v080" / "app" / "__init__.py").read_text("utf-8")
    assert 'EXPECTED_TRANSPORT_ENGINE="3.1.0"' in start
    assert 'EXPECTED_PROMPT_CONTRACT="environment-system-v1.5-hybrid"' in start
    assert 'EXPECTED_MODEL="google/gemini-2.5-flash-image"' in start
    assert 'ui_single_window/index.html' in start
    assert 'ui_single_window/styles.css' in start
    assert 'ui_single_window/app-v080.js' in start
    assert 'hybrid-mode-patch.js' in start
    assert 'Hybrid Engine 3.1.0 verified' in start
    assert 'Generation modes: HYBRID / IMAGE EDIT / OUTPAINT' in start
    assert 'stable_engine' in init
    assert 'provider_policy' not in init
    assert 'selective_policy' not in init
    assert 'missing_region_policy' not in init
