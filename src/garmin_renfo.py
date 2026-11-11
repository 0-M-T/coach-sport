"""Séances de renforcement envoyées à la montre (Garmin Connect) et programmées les jours prévus par le plan.

Option 1 : séances sur mesure construites avec le catalogue d'exercices de Garmin (séries, répétitions, repos chronométrés), animées sur la montre (champs ANIMATION).
Option 2 : séances animées de la bibliothèque Garmin (yoga, Pilates, force au poids du corps) que Tom a ajoutées à
« Mes entraînements » : le coach les programme sur les jours d'étirements et d'activation (yoga et mobilité, que le catalogue
d'exercices ne couvre pas).
"""
import datetime as dt
import hashlib
import json
import re
import sys

import garminconnect.exercises as ex

from . import exercices_fr, garmin_course

SPORT = {"sportTypeId": 5, "sportTypeKey": "strength_training", "displayOrder": 5}
# Champs des séances de la bibliothèque Garmin : avec eux, la montre affiche l'animation de chaque exercice.
# Vérifié sur la Forerunner 255 le 2026-11-10 avec une séance d'essai envoyée par l'API.
ANIMATION = {"workoutProvider": "Garmin", "workoutSourceId": "GGe2df9"}
REPOS_S = 60
POIDS_KG = {"unitId": 8, "unitKey": "kilogram", "factor": 1000.0}

# (nom Garmin exact, séries, répétitions ou "30s" pour un effort chronométré)
CIRCUITS_GARMIN = {
    "A1": [("Goblet Squat", 3, "8"), ("Romanian Deadlift", 3, "8"), ("Walking Dumbbell Lunge", 3, "12"),
           ("Alternating Box Dumbbell Step-ups", 3, "10"), ("Single-leg Standing Dumbbell Calf Raise", 3, "10"), ("Seated Calf Raise", 3, "12"),
           ("Side Plank", 2, "30s")],
    "A2": [("Single-leg Romanian Deadlift with Dumbbell", 2, "8"), ("Dumbbell Reverse Lunge", 2, "10"), ("Hip Raise", 2, "12"),
           ("Single-leg Standing Dumbbell Calf Raise", 2, "10"), ("Seated Calf Raise", 2, "12"), ("Plank", 2, "45s")],
    "A3": [("Goblet Squat", 3, "8"), ("Alternating Box Dumbbell Step-ups", 3, "8"), ("Dumbbell Reverse Lunge", 3, "8"),
           ("Single-leg Standing Dumbbell Calf Raise", 3, "12"), ("Seated Calf Raise", 3, "12"), ("Plank", 2, "45s")],
    "B1": [("Dumbbell Bench Press", 3, "8"), ("Banded Row", 3, "8"), ("Kneeling Ab Wheel", 3, "9"), ("Plank", 3, "40s"), ("Push-up", 2, "10")],
    "B2": [("Incline Dumbbell Bench Press", 3, "8"), ("Single-arm Neutral-grip Dumbbell Row", 3, "10"), ("Dead Bug", 3, "10"),
           ("Kneeling Ab Wheel", 3, "8"), ("Side Plank", 2, "30s")],
    "B3": [("Dumbbell Shoulder Press", 3, "8"), ("Dumbbell Row", 3, "10"), ("Dumbbell Lying Triceps Extension", 3, "10"),
           ("Face Pull", 3, "12"), ("Farmer's Walk", 3, "40s"), ("Side Plank", 2, "30s")],
    "C1": [("Jump Rope", 3, "120s"), ("Single-leg Standing Calf Raise", 3, "30s"), ("Hip Raise", 2, "12"), ("Kneeling Ab Wheel", 2, "8")],
    "C2": [("Single-leg Standing Calf Raise", 2, "15"), ("Dead Bug", 2, "10"), ("Side Plank", 2, "30s"), ("Hip Raise", 2, "12"), ("Plank", 2, "30s")],
}

TITRES_AGENDA = {  # titre de l'événement Baïkal -> code du circuit
    "Renfo A1, bas du corps": "A1", "Renfo A2, bas du corps allégé": "A2", "Renfo A3, bas du corps et descente": "A3",
    "Renfo B3, haut du corps pour les bâtons": "B3", "Renfo B1, haut du corps et gainage": "B1", "Renfo B2, haut du corps et gainage": "B2",
    "Activation C1": "C1", "Activation C2": "C2",
}


def _etape_exercice(ordre: int, nom: str, reps: str) -> dict:
    r = ex.resolve(nom)
    if not r:
        raise ValueError(f"exercice inconnu du catalogue Garmin : {nom}")
    chrono = reps.endswith("s")
    cond = ({"conditionTypeId": 2, "conditionTypeKey": "time", "displayOrder": 2, "displayable": True} if chrono
            else {"conditionTypeId": 10, "conditionTypeKey": "reps", "displayOrder": 10, "displayable": True})
    return {"type": "ExecutableStepDTO", "stepOrder": ordre, "stepType": {"stepTypeId": 3, "stepTypeKey": "interval", "displayOrder": 3},
            "endCondition": cond, "endConditionValue": float(reps.rstrip("s")),
            "targetType": {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target", "displayOrder": 1},
            "category": r["category"], "exerciseName": r["exercise"],
            **({"weightValue": kg, "weightUnit": POIDS_KG} if (kg := exercices_fr.charge_kg(nom)) else {})}


def _repos(ordre: int, secondes: int) -> dict:
    return {"type": "ExecutableStepDTO", "stepOrder": ordre, "stepType": {"stepTypeId": 5, "stepTypeKey": "rest", "displayOrder": 5},
            "endCondition": {"conditionTypeId": 2, "conditionTypeKey": "time", "displayOrder": 2, "displayable": True},
            "endConditionValue": float(secondes)}


def charge_utile(code: str, nom: str) -> dict:
    """JSON d'une séance de force : un groupe « N séries » par exercice (exercice puis repos)."""
    steps, ordre = [], 1
    for exo, series, reps in CIRCUITS_GARMIN[code]:
        groupe = ordre
        interne = [_etape_exercice(ordre + 1, exo, reps), _repos(ordre + 2, REPOS_S)]
        for s in interne:
            s["childStepId"] = groupe
        steps.append({"type": "RepeatGroupDTO", "stepOrder": groupe, "childStepId": groupe,
                      "stepType": {"stepTypeId": 6, "stepTypeKey": "repeat", "displayOrder": 6},
                      "numberOfIterations": series, "workoutSteps": interne, "smartRepeat": False,
                      "endCondition": {"conditionTypeId": 7, "conditionTypeKey": "iterations", "displayOrder": 7, "displayable": False},
                      "endConditionValue": float(series)})
        ordre += 3
    duree = sum(s["numberOfIterations"] * (45 + REPOS_S) for s in steps)
    return {"workoutName": nom, "sportType": SPORT, "estimatedDurationInSecs": int(duree), **ANIMATION,
            "workoutSegments": [{"segmentOrder": 1, "sportType": SPORT, "workoutSteps": steps}]}


def empreinte(code: str, nom: str) -> str:
    return hashlib.sha1(json.dumps(charge_utile(code, nom), sort_keys=True).encode()).hexdigest()[:12]


def code_de(titre: str) -> str | None:
    return TITRES_AGENDA.get(titre)


DANGEREUX = ("JUMP", "BURPEE", "THRUST", "MOUNTAIN_CLIMBER", "SHUFFLE", "HIGH_KNEES", "SKATER", "PLYO", "JACK", "HOP")
SPORTS_DOUX = ("yoga", "pilates", "mobility", "flexibility", "strength_training")
MOTS_CORE = re.compile(r"\b(ab|abs|core|burner|plank|strong|glute)\b", re.I)
DUREE_MAX_MIN = 30


def _exercices(etapes: list[dict], sortie: list[str]) -> list[str]:
    for e in etapes:
        if e.get("type") == "RepeatGroupDTO":
            _exercices(e["workoutSteps"], sortie)
        elif e.get("exerciseName") or e.get("category"):
            sortie.append(str(e.get("exerciseName") or e.get("category")))
    return sortie


def analyser(c, w: dict) -> dict:
    """Contenu d'une séance de la bibliothèque : durée, type, et surtout présence de sauts ou d'exercices à impact (tendons et mollets fragiles)."""
    d = c.get_workout_by_id(w["workoutId"])
    exos = _exercices(d["workoutSegments"][0]["workoutSteps"], [])
    return {"nom": w.get("workoutName", ""), "sport": ((d.get("sportType") or {}).get("sportTypeKey") or "").lower(),
            "duree": (d.get("estimatedDurationInSecs") or 0) // 60, "sur": not any(k in x.upper() for x in exos for k in DANGEREUX)}


def impact_autorise(aujourdhui: dt.date) -> bool:
    """Sauts et pliométrie permis loin d'un objectif : les mollets se renforcent par une charge progressive, pas par l'évitement.

    Pas de nouvelle charge à impact dans les 21 jours avant un objectif (semi, 24 h de La Rhune, 10 km)."""
    from .plan import OBJECTIFS
    futurs = [dt.date.fromisoformat(o["date"]) for o in OBJECTIFS if o["date"] >= aujourdhui.isoformat()]
    return not futurs or (min(futurs) - aujourdhui).days >= 21


def classer(a: dict, impact_ok: bool = False) -> str | None:
    """etirements, activation ou None (HIIT, cardio, trop long, ou impact trop près d'un objectif). Les HIIT sont toujours exclus : trop intenses pour des jours faciles."""
    if a["sport"] not in SPORTS_DOUX or (not a["sur"] and not impact_ok) or not (0 < a["duree"] <= DUREE_MAX_MIN):
        return None
    if a["sport"] in ("yoga", "pilates", "mobility", "flexibility") and not MOTS_CORE.search(a["nom"]):
        return "etirements"
    return "activation"


def animees(entrainements: list[dict], connus: set[int], analyses: dict | None = None, impact_ok: bool = False) -> dict[str, list[dict]]:
    """Séances de la bibliothèque ajoutées par Tom (pas créées par le coach), rangées par usage. Sans analyse du contenu, rien n'est retenu."""
    out = {"etirements": [], "activation": []}
    for w in entrainements:
        a = (analyses or {}).get(str(w.get("workoutId")))
        nom = (w.get("workoutName") or "").lower()
        if w.get("workoutId") in connus or not a or nom.startswith("test") or "ne pas programmer" in nom:
            continue   # séance d'essai de Tom (le 15/11, « TEST animation : Renfo A1 » avait pris la place de l'activation C1)
        usage = classer(a, impact_ok)
        if usage:
            out[usage].append(w)
    return out


def choisir(candidats: list[dict], date: str) -> dict | None:
    """Rotation stable par date : la même séance revient seulement après avoir fait le tour."""
    if not candidats:
        return None
    triees = sorted(candidats, key=lambda w: w["workoutId"])
    return triees[dt.date.fromisoformat(date).toordinal() % len(triees)]


def synchroniser(c, etat: dict, aujourdhui: str, jours: int = 14, apply: bool = True) -> list[str]:
    """Aligne les séances Garmin sur les événements Baïkal du coach (même titre, même jour).

    A1/A2/B1/B2 : séances sur mesure. C1/C2 et étirements : séances animées ajoutées par Tom si elles existent,
    sinon séance sur mesure pour C et rien pour les étirements.
    """
    g = etat.setdefault("garmin", {"workouts": {}, "programmes": {}})
    fin = (dt.date.fromisoformat(aujourdhui) + dt.timedelta(days=jours)).isoformat()
    compte: list[str] = []
    cibles = {i: r for i, r in etat["evenements"].items() if aujourdhui <= r["date"] < fin
              and (code_de(r["titre"]) or r["cle"].endswith("|etirements") or r.get("etapes"))}
    g.setdefault("courses", {})
    connus = {w["id"] for w in g["workouts"].values()} | {w["id"] for w in g["courses"].values()}
    besoin = any(r["cle"].endswith("|etirements") or (code_de(r["titre"]) or "").startswith("C") for r in cibles.values())
    bibliotheque = None
    if besoin:
        biblio = [w for w in (c.get_workouts(0, 200) or []) if w["workoutId"] not in connus]
        analyses = g.setdefault("bibliotheque", {})
        for w in biblio:   # une seule analyse par séance (un appel Garmin), mise en cache
            if str(w["workoutId"]) not in analyses and (w.get("sportType") or {}).get("sportTypeKey") not in ("running", "cycling"):
                analyses[str(w["workoutId"])] = analyser(c, w)
        bibliotheque = animees(biblio, connus, analyses, impact_autorise(dt.date.fromisoformat(aujourdhui)))
    voulus: dict[str, tuple[int, str]] = {}   # ident -> (workoutId, source)
    for ident, r in cibles.items():
        if r.get("etapes"):   # séance de course structurée : une séance Garmin par événement, mise à jour si le plan change
            h = garmin_course.empreinte(r["etapes"], r["titre"])
            w = g["courses"].get(ident)
            if not w or w["hash"] != h:
                compte.append(f"séance de course {r['cle']} {'mise à jour' if w else 'créée'} sur la montre")
                if not apply:
                    continue
                sport = garmin_course.VELO if r["cle"].endswith("|velo_maison") else garmin_course.SPORT
                nouveau = c.upload_workout(garmin_course.charge_utile(r["etapes"], r["titre"], sport))["workoutId"]
                if w:
                    g.setdefault("a_supprimer", []).append(w["id"])
                g["courses"][ident] = {"id": nouveau, "hash": h}
            voulus[ident] = (g["courses"][ident]["id"], "course")
            continue
        code = code_de(r["titre"])
        usage = "etirements" if r["cle"].endswith("|etirements") else ("activation" if code and code.startswith("C") else None)
        anime = choisir((bibliotheque or {}).get(usage, []), r["date"]) if usage else None
        if anime:
            voulus[ident] = (anime["workoutId"], "anime")
            continue
        if not code:
            continue  # étirements sans séance animée disponible : l'événement Baïkal suffit
        w = g["workouts"].get(code)
        h = empreinte(code, r["titre"])
        if not w or w["hash"] != h:
            compte.append(f"séance Garmin {code} {'mise à jour' if w else 'créée'}")
            if apply:
                nouveau = c.upload_workout(charge_utile(code, r["titre"]))["workoutId"]
                ancien = w["id"] if w else None
                g["workouts"][code] = {"id": nouveau, "hash": h, "nom": r["titre"]}
                g.setdefault("a_supprimer", []).extend([ancien] if ancien else [])
            else:
                continue
        voulus[ident] = (g["workouts"][code]["id"], "custom")
    for ident, (wid, source) in voulus.items():
        r = etat["evenements"][ident]
        p = g["programmes"].get(ident)
        if p and p["date"] == r["date"] and p["workoutId"] == wid:
            continue
        compte.append(f"{r['cle']} : programmée sur la montre ({source})")
        if apply:
            if p:
                c.unschedule_workout(p["scheduleId"])
            rep = c.schedule_workout(wid, r["date"])
            g["programmes"][ident] = {"workoutId": wid, "scheduleId": rep["workoutScheduleId"], "date": r["date"], "source": source}
    for ident, p in list(g["programmes"].items()):
        if ident not in voulus and (ident not in etat["evenements"] or etat["evenements"][ident]["date"] >= aujourdhui):
            compte.append(f"{p['date']} : déprogrammée de la montre")
            if apply:
                try:
                    c.unschedule_workout(p["scheduleId"])
                except Exception as e:  # souvent déjà supprimée côté Garmin
                    print(f"[GARMIN] déprogrammation {p['scheduleId']} : {e}", file=sys.stderr)
                del g["programmes"][ident]
    if apply:
        for ident, w in list(g["courses"].items()):
            if ident not in etat["evenements"]:
                g.setdefault("a_supprimer", []).append(w["id"])
                del g["courses"][ident]
        utiles = {p["workoutId"] for p in g["programmes"].values()}
        for wid in g.get("a_supprimer", []):
            if wid not in utiles:
                try:
                    c.delete_workout(wid)
                except Exception as e:  # séance orpheline possible sur Garmin Connect : on le dit
                    print(f"[GARMIN] suppression de la séance {wid} : {e}", file=sys.stderr)
        g["a_supprimer"] = []
    return compte


def ids_programmes(etat: dict) -> set[int]:
    """Séances Garmin gérées par le coach : le miroir Garmin vers Baïkal ne doit pas les recopier."""
    g = etat.get("garmin", {})
    return ({p["workoutId"] for p in g.get("programmes", {}).values()} | {w["id"] for w in g.get("workouts", {}).values()}
            | {w["id"] for w in g.get("courses", {}).values()})
