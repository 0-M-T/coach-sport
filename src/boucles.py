"""Parcours conseillés depuis l'historique de Tom : ses propres sorties au départ de la maison, avec export GPX.

Pas de service de calcul d'itinéraire : un parcours déjà couru est connu, sûr et à la bonne distance. Le GPX part en pièce jointe ntfy
(à ouvrir avec Garmin Connect ou l'app du compteur iGPSPORT).
"""
import collections
import datetime as dt
import json
from pathlib import Path

from . import club, ntfy, strava
from .config import ecrire_json

from . import chemins

CATALOGUE = chemins.boucles_path()
GPX_DIR = chemins.gpx_dir()
RAYON_M = 600
ALLURE_EF_MIN_KM = 5.5   # pour passer d'une durée à une distance


def maison(acts: list[dict]) -> tuple[float, float]:
    """Point de départ le plus fréquent (à 3 décimales, environ 100 m) : la maison."""
    c = collections.Counter((round(a["start_latlng"][0], 3), round(a["start_latlng"][1], 3)) for a in acts if a.get("start_latlng"))
    return c.most_common(1)[0][0]


def maj(conf: dict) -> list[dict]:
    t = strava.token(conf)
    acts = []
    for page in range(1, 6):
        r = strava.call(t, f"/athlete/activities?per_page=200&page={page}")
        if not r:
            break
        acts += r
    sorties = [a for a in acts if a.get("sport_type") in ("Run", "TrailRun") and a.get("start_latlng")]
    centre = maison(sorties)
    routes: dict[tuple, dict] = {}
    for a in sorted(sorties, key=lambda x: x["start_date_local"]):
        if club.distance_m(centre, a["start_latlng"]) > RAYON_M or a["distance"] < 3000:
            continue
        cle = (round(a["distance"] / 500), round(a.get("total_elevation_gain", 0) / 25))   # même parcours : mêmes distance et dénivelé arrondis
        routes[cle] = {"id": a["id"], "date": a["start_date_local"][:10], "km": round(a["distance"] / 1000, 1),
                       "dplus": round(a.get("total_elevation_gain", 0)), "nom": a["name"]}
    liste = sorted(routes.values(), key=lambda r: r["km"])
    ecrire_json(CATALOGUE, {"maison": centre, "routes": liste, "maj": dt.date.today().isoformat()})
    return liste


def charger() -> list[dict]:
    return json.loads(CATALOGUE.read_text())["routes"] if CATALOGUE.exists() else []


def suggere(kind: str, minutes: int, routes: list[dict] | None = None) -> dict | None:
    """Parcours de l'historique adapté à la séance : distance de la durée à allure facile, profil plat (EF) ou vallonné (côtes)."""
    routes = routes if routes is not None else charger()
    if kind not in ("ef", "longue", "cotes") or not routes:
        return None
    cible = minutes / ALLURE_EF_MIN_KM
    def score(r):
        pente = r["dplus"] / r["km"]                                  # m de D+ par km
        ecart_km = abs(r["km"] - cible) / cible
        profil = max(0, pente - 15) / 15 if kind == "ef" else (max(0, 30 - pente) / 30 if kind == "cotes" else 0)
        return ecart_km + 0.5 * profil
    meilleur = min(routes, key=score)
    return meilleur if abs(meilleur["km"] - cible) / cible <= 0.25 else None


def gpx(conf: dict, activite: int) -> Path:
    t = strava.token(conf)
    s = strava.call(t, f"/activities/{activite}/streams?keys=latlng,altitude,time&key_by_type=true")
    pts = s["latlng"]["data"]
    alt = s.get("altitude", {}).get("data", [0] * len(pts))
    d = strava.call(t, f"/activities/{activite}")
    depart = dt.datetime.fromisoformat(d["start_date"].replace("Z", "+00:00"))
    temps = s.get("time", {}).get("data", list(range(len(pts))))
    trkpts = "\n".join(f'      <trkpt lat="{la:.6f}" lon="{lo:.6f}"><ele>{e:.1f}</ele><time>{(depart + dt.timedelta(seconds=tt)).strftime("%Y-%m-%dT%H:%M:%SZ")}</time></trkpt>'
                       for (la, lo), e, tt in zip(pts, alt, temps, strict=False))   # flux de longueurs égales chez Strava ; sinon on tronque
    nom = d["name"].replace("&", "et").replace("<", "")
    GPX_DIR.mkdir(parents=True, exist_ok=True)
    f = GPX_DIR / f"{activite}.gpx"
    f.write_text(f'<?xml version="1.0" encoding="UTF-8"?>\n<gpx version="1.1" creator="coach-sport" xmlns="http://www.topografix.com/GPX/1/1">\n'
                 f'  <trk><name>{nom}</name><trkseg>\n{trkpts}\n    </trkseg></trk>\n</gpx>\n')
    return f


def envoyer_gpx(conf: dict, fichier: Path, titre: str) -> None:
    """Pièce jointe ntfy : ouvrir sur le téléphone puis partager vers Garmin Connect ou l'app iGPSPORT."""
    ntfy.piece_jointe(conf, fichier, titre, "Parcours au format GPX. Ouvrir puis partager vers Garmin Connect ou l'app du compteur.")


def suggere_pour_titre(titre: str, routes: list[dict] | None = None) -> dict | None:
    """Parcours conseillé pour une séance d'après son titre (« Footing EF 40 min », « Sortie longue 1h30 », « Côtes 8x45 s »)."""
    import re
    t = titre.lower()
    if any(k in t for k in ("pic du rey", "trail", "simulation", "rando", "seuil", "fractionné", "10 km", "rappel", "test", "club", "groupe")):
        return None
    if "footing" in t or "décrassage" in t:
        kind = "ef"
    elif "sortie longue" in t:
        kind = "longue"
    elif "côtes" in t:
        kind = "cotes"
    else:
        return None
    m = re.search(r"(\d+)\s*min", t)
    h = re.search(r"(\d+)h(\d{2})?", t)
    minutes = int(m[1]) if m else (int(h[1]) * 60 + int(h[2] or 0) if h else 60 if kind == "cotes" else None)
    return suggere(kind, minutes, routes) if minutes else None
