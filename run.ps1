param(
  [switch]$NoInstall
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

if (-not (Test-Path ".venv")) {
  python -m venv .venv
}

$venvActivate = Join-Path ".venv" "Scripts\\Activate.ps1"
. $venvActivate

if (-not $NoInstall) {
  pip install -r requirements.txt
}

uvicorn main:app --reload --host 0.0.0.0 --port 8000

