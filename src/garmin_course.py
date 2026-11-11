"""Séances de course structurées pour la montre : allures cibles, distances, récupérations.

Une étape est un tuple : ("w", s) échauffement, ("c", s) retour au calme, ("e", s, lo, hi) footing avec fourchette d'allure, ("t", s) effort au temps sans cible,
("id", m, allure, tol) effort à la distance, ("it", s, allure, tol) effort au temps, ("r", s) récupération,
("rep", n, [étapes]) répétitions, ("fc", s, fc_min, fc_max) effort au temps avec une fourchette de FC. Allures en s/km ; la cible Garmin est une fourchette de vitesse en m/s.
"""
import hashlib
import json

SPORT = {"sportTypeId": 1, "sportTypeKey": "running", "displayOrder": 1}
VELO = {"sportTypeId": 2, "sportTypeKey": "cycling", "displayOrder": 2}
SANS_CIBLE = {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target", "displayOrder": 1}
TYPES = {"warmup": (1, 1), "cooldown": (2, 2), "interval": (3, 3), "recovery": (4, 4)}


def cible_allure(lo_s: float, hi_s: float) -> dict:
    """lo_s : allure la plus lente (s/km), hi_s : la plus rapide. Garmin attend des vitesses : valeur 1 lente, valeur 2 rapide."""
    return {"targetType": {"workoutTargetTypeId": 6, "workoutTargetTypeKey": "pace.zone", "displayOrder": 6},
            "targetValueOne": round(1000 / lo_s, 3), "targetValueTwo": round(1000 / hi_s, 3)}


def _etape(ordre: int, genre: str, condition: tuple[str, float], cible: dict | None) -> dict:
    cid, ckey = (2, "time") if condition[0] == "t" else (3, "distance")
    tid, order = TYPES[genre]
    d = {"type": "ExecutableStepDTO", "stepOrder": ordre, "stepType": {"stepTypeId": tid, "stepTypeKey": genre, "displayOrder": order},
         "endCondition": {"conditionTypeId": cid, "conditionTypeKey": ckey, "displayOrder": cid, "displayable": True},
         "endConditionValue": float(condition[1]), "targetType": SANS_CIBLE}
    if cible:
        d.update(cible)
    return d


def _convertir(etape, ordre: int) -> tuple[list[dict], int]:
    """Renvoie (étapes JSON, prochain ordre libre)."""
    k = etape[0]
    if k == "w":
        return [_etape(ordre, "warmup", ("t", etape[1]), None)], ordre + 1
    if k == "c":
        return [_etape(ordre, "cooldown", ("t", etape[1]), None)], ordre + 1
    if k == "r":
        return [_etape(ordre, "recovery", ("t", etape[1]), None)], ordre + 1
    if k == "e":
        return [_etape(ordre, "interval", ("t", etape[1]), cible_allure(etape[3], etape[2]))], ordre + 1
    if k == "fc":   # effort au temps avec une fourchette de FC (vélo d'appartement de récupération)
        cible = {"targetType": {"workoutTargetTypeId": 4, "workoutTargetTypeKey": "heart.rate.zone", "displayOrder": 4},
                 "targetValueOne": float(etape[2]), "targetValueTwo": float(etape[3])}
        return [_etape(ordre, "interval", ("t", etape[1]), cible)], ordre + 1
    if k == "t":   # effort au temps sans cible d'allure (côte, trail : on pilote à la FC et aux sensations)
        return [_etape(ordre, "interval", ("t", etape[1]), None)], ordre + 1
    if k in ("id", "it"):
        _, valeur, allure, tol = etape
        return [_etape(ordre, "interval", ("d" if k == "id" else "t", valeur), cible_allure(allure + tol, allure - tol))], ordre + 1
    if k == "rep":
        _, n, enfants = etape
        groupe, ordre = ordre, ordre + 1
        sortie = []
        for e in enfants:
            js, ordre = _convertir(e, ordre)
            sortie += js
        for js in sortie:
            js["childStepId"] = groupe
        return [{"type": "RepeatGroupDTO", "stepOrder": groupe, "childStepId": groupe,
                 "stepType": {"stepTypeId": 6, "stepTypeKey": "repeat", "displayOrder": 6}, "numberOfIterations": int(n),
                 "workoutSteps": sortie, "smartRepeat": False,
                 "endCondition": {"conditionTypeId": 7, "conditionTypeKey": "iterations", "displayOrder": 7, "displayable": False},
                 "endConditionValue": float(n)}], ordre
    raise ValueError(f"étape inconnue : {etape!r}")


def _duree(etape) -> float:
    k = etape[0]
    if k in ("w", "c", "r", "e", "it", "t", "fc"):
        return float(etape[1])
    if k == "id":
        return etape[1] / 1000 * etape[2]
    return etape[1] * sum(_duree(e) for e in etape[2])


def charge_utile(etapes, nom: str, sport: dict = SPORT) -> dict:
    steps, ordre = [], 1
    for e in etapes:
        js, ordre = _convertir(e, ordre)
        steps += js
    return {"workoutName": nom, "sportType": sport, "estimatedDurationInSecs": int(sum(_duree(e) for e in etapes)),
            "workoutSegments": [{"segmentOrder": 1, "sportType": sport, "workoutSteps": steps}]}


def empreinte(etapes, nom: str) -> str:
    return hashlib.sha1(json.dumps([nom, etapes], sort_keys=True, default=list).encode()).hexdigest()[:12]
