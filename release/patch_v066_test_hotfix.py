from pathlib import Path
import sys

runtime = Path(sys.argv[1])

replacements = {
    runtime / "tests/test_openrouter_hardened.py": (
        'assert "v0.6.4 API error diagnostics" in index',
        'assert "API error diagnostics" in index',
    ),
    runtime / "tests/test_task_status_async.py": (
        'assert "v0.6.5 task status monitor" in index',
        'assert "task status monitor" in index',
    ),
}

for path, (old, new) in replacements.items():
    if not path.exists():
        raise SystemExit(f"Hotfix failed: missing test file {path.name}")
    text = path.read_text("utf-8")
    if new in text:
        continue
    if old not in text:
        raise SystemExit(f"Hotfix failed: expected assertion not found in {path.name}")
    path.write_text(text.replace(old, new, 1), "utf-8")

print("Applied v0.6.6 cross-version test marker hotfix")
