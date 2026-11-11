"""Métriques textfile par tâche (un fichier par tâche : deux écrivains sur le même .prom s'écrasent).

L'étiquette s'appelle `tache` et non `job` : Prometheus renomme `job` en `exported_job` (conflit avec le job de scrape),
ce qui avait rendu les alertes du coach aveugles jusqu'au 2026-11-09."""
import os
import time
from pathlib import Path
from . import chemins

ENVOYE = False  # passé à True par ntfy.envoyer : distingue « a envoyé » de « a attendu »
DIR = Path(os.environ.get("COACH_TEXTFILE_DIR", chemins.state_dir() / "prometheus"))


def _precedent(f: Path) -> float:
    try:
        for l in f.read_text().splitlines():
            if l.startswith("coach_job_last_success_timestamp_seconds"):
                return float(l.rsplit(" ", 1)[1])
    except (OSError, ValueError):
        pass
    return 0.0


def ecrire(job: str, code: int, duree: float, envoye: bool = False) -> None:
    """code 0 = succès. envoye : un message ntfy est parti (briefings), pour l'alerte « aucun briefing »."""
    if not DIR.is_dir():
        return
    f = DIR / f"coach_{job}.prom"
    now = time.time()
    ok = now if code == 0 else _precedent(f)
    envoi = now if envoye else _precedent_envoi(f)
    txt = (f'coach_job_last_run_timestamp_seconds{{tache="{job}"}} {now:.0f}\n'
           f'coach_job_last_success_timestamp_seconds{{tache="{job}"}} {ok:.0f}\n'
           f'coach_job_last_exit_code{{tache="{job}"}} {code}\n'
           f'coach_job_duration_seconds{{tache="{job}"}} {duree:.1f}\n'
           f'coach_job_last_sent_timestamp_seconds{{tache="{job}"}} {envoi:.0f}\n')
    tmp = f.with_suffix(".tmp")
    tmp.write_text(txt)
    tmp.replace(f)  # remplacement atomique : le collecteur ne lit jamais un fichier à moitié écrit


def _precedent_envoi(f: Path) -> float:
    try:
        for l in f.read_text().splitlines():
            if l.startswith("coach_job_last_sent_timestamp_seconds"):
                return float(l.rsplit(" ", 1)[1])
    except (OSError, ValueError):
        pass
    return 0.0
