$ErrorActionPreference = "Stop"
if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Python Launcher was not found. Install Python 3.12 and its launcher."
}
py -3.12 -c "import sys; assert sys.version_info[:2] == (3, 12)"
if ($LASTEXITCODE -ne 0) {
    throw "Python 3.12 is required."
}
py -3.12 -m venv .venv
if ($LASTEXITCODE -ne 0) {
    throw "Failed to create the Python 3.12 virtual environment."
}
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    throw "Failed to upgrade pip."
}
& .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) {
    throw "Failed to install development requirements."
}
& .\.venv\Scripts\python.exe -m pytest -q
if ($LASTEXITCODE -ne 0) {
    throw "pytest failed."
}
& .\.venv\Scripts\python.exe -m ruff check .
if ($LASTEXITCODE -ne 0) {
    throw "ruff failed."
}
