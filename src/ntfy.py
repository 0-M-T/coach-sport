"""Notifications ntfy du coach (canal coach-sport) : messages et pièces jointes. Module sans dépendance interne, importable partout."""
import re
import urllib.request
from pathlib import Path

from . import suivi

URL_DEFAUT = "https://ntfy.sh/coach-sport"


def _entetes(conf: dict, titre: str) -> dict:
    return {"Title": titre.encode("utf-8"), "Authorization": f"Bearer {conf.get('NTFY_TOKEN', '')}"}


def envoyer(conf: dict, titre: str, message: str, actions: str | None = None, priority: str = "default") -> None:
    message = re.sub(r"(?<=\d)\.(?=\d)", ",", message)  # décimales à la française
    headers = {**_entetes(conf, titre), "Priority": priority}
    if actions:
        headers["Actions"] = actions
    urllib.request.urlopen(urllib.request.Request(conf.get("NTFY_URL", URL_DEFAUT), data=message.encode("utf-8"), headers=headers), timeout=5)
    suivi.ENVOYE = True


def piece_jointe(conf: dict, fichier: Path, titre: str, message: str) -> None:
    req = urllib.request.Request(conf.get("NTFY_URL", URL_DEFAUT), data=fichier.read_bytes(), method="PUT",
                                 headers={**_entetes(conf, titre), "Filename": fichier.name, "Message": message.encode("utf-8")})
    urllib.request.urlopen(req, timeout=30)
