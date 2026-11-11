"""Notification dédiée à l'usure des chaussures : une fois par chaussure et par seuil franchi."""
import json

from . import ntfy, strava, texte
from .config import ecrire_json, load_config

from . import chemins

STATE = chemins.state_path()


def niveau(km: float, alerte: int, usure: int) -> int:
    return usure if km >= usure else alerte if km >= alerte else 0


def verifier(conf=None, access=None, envoyer=True) -> list[tuple[str, str]]:
    conf = load_config() if conf is None else conf
    access = access or strava.token(conf)
    alerte, usure = int(conf.get("COACH_GEAR_ALERT_KM", 700)), int(conf.get("COACH_GEAR_MAX_KM", 750))
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    deja = state.setdefault("materiel", {})
    messages = []
    import datetime as dt
    depuis = int((dt.datetime.now() - dt.timedelta(days=120)).timestamp())
    # /athlete ne donne pas les chaussures sans le scope profile:read_all : on prend celles utilisées récemment (ids « g… »)
    ids = {a["gear_id"] for a in strava.activities(access, 100, depuis) if str(a.get("gear_id", "")).startswith("g")}
    if conf.get("STRAVA_GEAR_ID"):
        ids.add(conf["STRAVA_GEAR_ID"])
    for gid in sorted(ids):
        shoe = strava.call(access, f"/gear/{gid}")
        if shoe.get("retired"):
            continue
        shoe["id"] = gid
        km = shoe.get("distance", 0) / 1000
        niv = niveau(km, alerte, usure)
        if not niv or deja.get(shoe["id"], 0) >= niv:
            continue
        titre = f"Chaussures à changer : {shoe['name']}" if niv == usure else f"Chaussures bientôt usées : {shoe['name']}"
        reste = max(0, usure - km)
        corps = texte.message(
            texte.bloc("Chaussures", f"{shoe['name']} : {km:.0f} km sur {usure} ({reste:.0f} km restants)"),
            texte.bloc("À faire", "Prévoir une paire de remplacement" if niv == alerte else "Remplacer avant la prochaine séance dure"))
        messages.append((titre, corps))
        if envoyer:
            ntfy.envoyer(conf, titre, corps)
            deja[shoe["id"]] = niv
    if envoyer and messages:
        ecrire_json(STATE, state)
    return messages
