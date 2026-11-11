#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3 requis mais non trouvé. Installez Python 3 puis relancez." >&2
    exit 1
fi

if [ ! -d ".venv" ]; then
    echo "Création de l'environnement virtuel (.venv)..."
    python3 -m venv .venv
    .venv/bin/pip install -q --upgrade pip
    .venv/bin/pip install -q -r requirements.txt pyyaml platformdirs
fi

echo "Démarrage du coach..."
.venv/bin/python coach.py next
