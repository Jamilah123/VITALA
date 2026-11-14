# Start the VITALA RAG service (port 8001) in a new window, then the backend (port 8000) here.
# Local demo only: both bind to 127.0.0.1 and use synthetic data.
#
#   powershell -ExecutionPolicy Bypass -File scripts\run_all.ps1
#
# Optional: -RagPython <path to a Python 3.12 that has rag/requirements.txt installed>

param([string]$RagPython = "")

$root = Split-Path -Parent $PSScriptRoot
$rag = Join-Path $root "rag"
$backend = Join-Path $root "backend"

if (-not $RagPython) { $RagPython = Join-Path $rag ".venv\Scripts\python.exe" }
if (-not (Test-Path $RagPython)) {
    Write-Host "RAG Python not found: $RagPython"
    Write-Host "Create it once:  cd rag; py -3.12 -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements.txt"
    exit 1
}
$envFile = Join-Path $rag ".env"
$envArg = ""
if (Test-Path $envFile) { $envArg = "--env-file `"$envFile`"" }
else { Write-Host "rag\.env not found: the chatbot runs in offline extractive mode (quotes only, no LLM)." }

$ragCommand = "`$env:PYTHONPATH='src'; `$env:VITALA_RETRIEVAL_MODE='hybrid'; " +
    "if (-not (Test-Path '$envFile')) { `$env:VITALA_LLM_PROVIDER='extractive' }; " +
    "& '$RagPython' -m uvicorn vitala_rag.interfaces:app --host 127.0.0.1 --port 8001 $envArg"
Start-Process powershell -WorkingDirectory $rag -ArgumentList "-NoExit", "-Command", $ragCommand

Set-Location $backend
& ".\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
