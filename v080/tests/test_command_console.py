from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_command_console_replaces_visible_right_inspector():
    patch = (ROOT / "ui_single_window" / "command-console-patch.js").read_text("utf-8")
    assert "SYSTEM №1" in patch
    assert "COMMAND CONSOLE" in patch
    assert "command-console-legacy" in patch
    assert ":root{--inspector:420px}" in patch
    assert "system1-command-console" in patch


def test_command_console_supports_core_workflow_commands():
    patch = (ROOT / "ui_single_window" / "command-console-patch.js").read_text("utf-8")
    for command in (
        "status",
        "process",
        "prompt",
        "diagnostics",
        "quality",
        "generate",
        "approve",
        "projects",
        "delete",
        "comment",
        "clear",
    ):
        assert command in patch
    assert "delete confirm" in patch
    assert "prompt edit" in patch
    assert "prompt rebuild" in patch


def test_console_process_receives_background_generation_events():
    patch = (ROOT / "ui_single_window" / "command-console-patch.js").read_text("utf-8")
    assert "marins-generation-status" in patch
    assert "GENERATION COMPLETED" in patch
    assert "GENERATION ERROR" in patch
    assert "работа продолжается, интерфейс свободен" in patch
    assert "RUN TRACE" in patch


def test_console_contains_inline_provider_prompt_editor():
    patch = (ROOT / "ui_single_window" / "command-console-patch.js").read_text("utf-8")
    assert "command-prompt-editor" in patch
    assert "/prompt/${stage}/edit" in patch
    assert "СОХРАНИТЬ" in patch
    assert "СОБРАТЬ ЗАНОВО" in patch
