# Démarrage Coach Sportif pour Windows (PowerShell)
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "Python requis mais introuvable. Installez Python depuis python.org puis relancez."
    exit 1
}

if (-not (Test-Path ".venv")) {
    Write-Host "Création de l'environnement virtuel (.venv)..."
    python -m venv .venv
    .\.venv\Scripts\pip install -q --upgrade pip
    .\.venv\Scripts\pip install -q -r requirements.txt pyyaml platformdirs
}

Write-Host "Démarrage du coach..."
.\.venv\Scripts\python coach.py next
