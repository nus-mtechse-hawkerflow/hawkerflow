from pathlib import Path


def test_windows_bootstrap_requires_python_312_and_requirements_file():
    script = Path("scripts/bootstrap.ps1").read_text(encoding="utf-8")
    assert "py -3.12" in script
    assert ".venv" in script
    assert "requirements-dev.txt" in script
