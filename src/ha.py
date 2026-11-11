"""Capteurs Home Assistant du coach : prochaine séance, jours avant l'objectif, séances de la semaine, dernière décision."""
import datetime as dt
import json
import urllib.request
from zoneinfo import ZoneInfo

from . import baikal, charge, planif, texte
from .config import HA_URL_DEFAUT, load_config
from .plan import OBJECTIFS

PARIS = ZoneInfo("Europe/Paris")


def prochaine_seance(lignes: list[str], maintenant: dt.datetime) -> str:
    """Première séance à venir parmi les lignes de l'agenda (déjà triées par date), « Aucune séance planifiée » sinon."""
    for l in sorted(lignes):
        p = baikal.parse(l)
        if not p or p["heure"] == "journée":
            continue
        if dt.datetime.fromisoformat(f"{p['date']}T{p['heure']}").replace(tzinfo=PARIS) >= maintenant:
            return f"{texte.jour_court(p['date'])} {p['heure']} {p['titre']}"[:250]
    return "Aucune séance planifiée"


def objectif(aujourdhui: dt.date) -> tuple[int, str]:
    futurs = sorted((o for o in OBJECTIFS if o["date"] >= aujourdhui.isoformat()), key=lambda o: o["date"])
    if not futurs:
        return -1, "aucun"
    return (dt.date.fromisoformat(futurs[0]["date"]) - aujourdhui).days, futurs[0]["nom"]


def capteurs(maintenant: dt.datetime | None = None) -> list[tuple[str, str, dict]]:
    from .semaine import lisible
    maintenant = maintenant or dt.datetime.now(PARIS)
    j = maintenant.date()
    lignes = baikal.lister(j.isoformat(), (j + dt.timedelta(days=14)).isoformat())
    lundi = j - dt.timedelta(days=j.weekday())
    cette_semaine = [l for l in lignes + baikal.lister(lundi.isoformat(), j.isoformat())
                     if (p := baikal.parse(l)) and lundi.isoformat() <= p["date"] <= (lundi + dt.timedelta(days=6)).isoformat()]
    jours, nom = objectif(j)
    etat = planif.charger()
    decision = next((x for x in (lisible(e) for e in reversed(etat.get("journal", []))) if x), "aucune")
    ch = etat.get("charge") or {}
    return [("coach_prochaine_seance", prochaine_seance(lignes, maintenant), {"icon": "mdi:run", "friendly_name": "Coach : prochaine séance"}),
            ("coach_jours_objectif", str(jours), {"icon": "mdi:flag-checkered", "friendly_name": f"Coach : jours avant {nom}", "unit_of_measurement": "j", "objectif": nom}),
            ("coach_seances_semaine", str(len(set(cette_semaine))), {"icon": "mdi:calendar-check", "friendly_name": "Coach : séances de la semaine"}),
            ("coach_derniere_decision", decision[:250], {"icon": "mdi:compass", "friendly_name": "Coach : dernière décision"}),
            # -1 : charge jamais calculée (une série absente n'alerte pas)
            ("coach_charge_rapport", str(ch.get("ratio") if ch.get("ratio") is not None else -1),
             {"icon": "mdi:chart-line", "friendly_name": "Coach : rapport fatigue / condition", "condition": ch.get("ctl"),
              "fatigue": ch.get("atl"), "fraicheur": ch.get("tsb"), "date": ch.get("date"), "avis": charge.avis(ch.get("ratio")) if ch else None})]


def pousser(conf: dict | None = None, maintenant: dt.datetime | None = None) -> int:
    conf = load_config() if conf is None else conf
    if not conf.get("HA_TOKEN"):
        return 0
    base = conf.get("HA_URL", HA_URL_DEFAUT).rstrip("/")
    n = 0
    for nom, etat, attrs in capteurs(maintenant):
        urllib.request.urlopen(urllib.request.Request(
            f"{base}/api/states/sensor.{nom}", data=json.dumps({"state": etat, "attributes": attrs}).encode(),
            headers={"Authorization": f"Bearer {conf['HA_TOKEN']}", "Content-Type": "application/json"}, method="POST"), timeout=8)
        n += 1
    return n
