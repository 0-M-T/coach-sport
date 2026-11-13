"""Isolation des tests : aucun test ne touche aux vrais fichiers d'état, à l'agenda, à Garmin, à ntfy ni au réseau.

Le 2026-11-10, un test de briefing a écrasé le vrai état du planificateur (coach-planif.json) : il remplaçait `planif.charger`
mais pas le chemin du fichier, et une nouvelle écriture a suffi. Ce module est importé avant tout module de test : il redirige
d'abord tous les chemins vers un dossier temporaire, puis remplace les accès réels par des refus explicites. Un test qui a besoin
d'un faux service le remplace lui-même (mock.patch), par-dessus ce refus.
"""
import os
import tempfile
import urllib.request
from pathlib import Path

BAC = Path(tempfile.mkdtemp(prefix="coach-tests-"))
for _var, _nom in {"COACH_PLANIF": "planif.json", "COACH_STATE": "sport.json", "COACH_BOUCLES": "boucles.json",
                   "COACH_STRAVA_TOKEN": "strava-token.json", "COACH_GPX_DIR": "gpx", "COACH_BACKUP_DIR": "backups",
                   "COACH_TEXTFILE_DIR": "textfile-absent", "COACH_LOCK": "coach.lock", "COACH_ENV": "absent.env", "COACH_ALERTE_PORTEE": "alerte-portee"}.items():
    os.environ[_var] = str(BAC / _nom)

from src import agent_coach, baikal, config, garmin, semaine  # noqa: E402 (après la redirection des chemins)


def _interdit(quoi: str):
    def refus(*a, **k):
        raise RuntimeError(f"{quoi} réel interdit dans les tests : le remplacer par un faux (mock.patch)")
    return refus


class _GarminInterdit:
    def __init__(self, *a, **k):
        _interdit("Compte Garmin")()


config.DEFAULT_ENV_PATHS = [BAC / "absent.env"]          # jamais le vrai coach.env
config.BAIKAL_ENV = BAC / "absent-baikal.env"         # ni le vrai baikal-agent.env
agent_coach.MARQUEURS = semaine.MARQUEURS = BAC         # anti-doublon des briefings
baikal.baikal_cmd = _interdit("Agenda Baïkal")          # lister, créer, modifier, supprimer passent tous par là
garmin.Garmin = _GarminInterdit
urllib.request.urlopen = _interdit("Réseau (Strava, ntfy, Home Assistant, météo)")
