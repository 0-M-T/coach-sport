"""Saisie et suivi du ressenti d'effort subjectif (RPE, échelle 1-10) post-séance."""
import datetime as dt
import json
from pathlib import Path
from . import chemins


def rpe_file() -> Path:
    return chemins.state_dir() / "coach-rpe.json"


def enregistrer_rpe(note: int, commentaire: str = "", date_iso: str | None = None) -> dict:
    if not (1 <= note <= 10):
        raise ValueError("La note RPE doit être comprise entre 1 (effort très facile) et 10 (effort maximal).")

    date_iso = date_iso or dt.date.today().isoformat()
    f = rpe_file()
    donnees = {}
    if f.exists():
        try:
            donnees = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            donnees = {}

    donnees[date_iso] = {
        "note": note,
        "commentaire": commentaire,
        "horodatage": dt.datetime.now(dt.UTC).isoformat(),
    }

    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(donnees, indent=2, ensure_ascii=False), encoding="utf-8")
    return donnees[date_iso]


def dernier_rpe(date_iso: str | None = None) -> dict | None:
    date_iso = date_iso or dt.date.today().isoformat()
    f = rpe_file()
    if not f.exists():
        return None
    try:
        donnees = json.loads(f.read_text(encoding="utf-8"))
        return donnees.get(date_iso)
    except Exception:
        return None
