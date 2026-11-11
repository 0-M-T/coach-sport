"""Charge d'entraînement : condition (moyenne sur 42 jours), fatigue (7 jours) et rapport entre les deux.

Calcul local (même formule qu'intervals.icu : moyennes exponentielles) sur la charge Garmin de chaque activité
(`activityTrainingLoad`, échelle EPOC et non TSS), plus les activités Strava que Garmin ne voit pas (vélo sur le compteur iGPSPORT). Le rapport fatigue / condition ne dépend pas de l'échelle :
c'est lui qui sert d'avis. Information seulement : la règle d'allègement (`decision.py`) n'en tient pas compte.
Rejeu du 2026-11-10 sur 60 jours : rapport au-dessus de 1,5 pendant 3 semaines de suite à la reprise de septembre (historique court,
condition basse), donc trop bruité pour alléger une séance. À réévaluer avec un historique de plus de 6 mois.
"""

import datetime as dt

CTL_J, ATL_J, HISTORIQUE_J = 42, 7, 150


# Activités que Garmin ne voit pas (vélo enregistré sur le compteur iGPSPORT) : effort relatif Strava (calculé sur la FC) converti à l'échelle
# de la charge Garmin. Rapports mesurés le 2026-11-10 sur 71 activités enregistrées des deux côtés : médiane 2,0 ; vélo 2,3 ; course 2,5.
FACTEUR_EFFORT = {"Ride": 2.3, "MountainBikeRide": 2.3, "GravelRide": 2.3, "VirtualRide": 2.3, "EBikeRide": 2.3}
FACTEUR_DEFAUT = 2.0


def _instant(texte: str) -> dt.datetime:
    return dt.datetime.fromisoformat(texte.replace(" ", "T").replace("Z", "") + "+00:00")


def ajouter_strava(charges: dict[str, float], garmin_acts: list[dict], strava_acts: list[dict] | None, fin: dt.date | None = None) -> dict[str, float]:
    """Ajoute aux charges Garmin les activités Strava sans équivalent Garmin (même départ à 5 min près), à partir de leur effort relatif."""
    debuts = [_instant(a["startTimeGMT"]) for a in garmin_acts if a.get("startTimeGMT")]
    for a in strava_acts or []:
        if not a.get("suffer_score") or not a.get("start_date"):
            continue
        debut = _instant(a["start_date"])
        if any(abs((debut - g).total_seconds()) < 300 for g in debuts):
            continue   # déjà comptée par Garmin
        j = a["start_date_local"][:10]
        if fin and j > fin.isoformat():
            continue   # après la période lue chez Garmin : impossible de vérifier le doublon
        charges[j] = charges.get(j, 0) + a["suffer_score"] * FACTEUR_EFFORT.get(a.get("sport_type", a.get("type")), FACTEUR_DEFAUT)
    return charges


def strava_recentes(conf: dict, fin: dt.date, jours: int = HISTORIQUE_J) -> list[dict]:
    """Activités Strava de la période (une ou deux requêtes)."""
    from . import strava
    t = strava.token(conf)
    apres = int(dt.datetime.combine(fin - dt.timedelta(days=jours), dt.time()).timestamp())
    out, page = [], 1
    while page <= 3:
        r = strava.call(t, f"/athlete/activities?per_page=200&page={page}&after={apres}")
        out += r or []
        if not r or len(r) < 200:
            break
        page += 1
    return out


def par_jour(c, fin: dt.date, jours: int = HISTORIQUE_J, strava_acts: list[dict] | None = None) -> dict[str, float]:
    """Charge totale par jour sur la période (un appel Garmin), plus les activités Strava que Garmin ne voit pas."""
    acts = c.get_activities_by_date((fin - dt.timedelta(days=jours)).isoformat(), fin.isoformat()) or []
    out: dict[str, float] = {}
    for a in acts:
        j = (a.get("startTimeLocal") or "")[:10]
        if j:
            out[j] = out.get(j, 0) + (a.get("activityTrainingLoad") or 0)
    return ajouter_strava(out, acts, strava_acts, fin)


def calculer(
    charges: dict[str, float], jour: dt.date, jours: int = HISTORIQUE_J
) -> dict:
    """Condition, fatigue, fraîcheur (condition moins fatigue) et rapport, journée `jour` comprise."""
    ctl = atl = 0.0
    for i in range(jours, -1, -1):
        x = charges.get((jour - dt.timedelta(days=i)).isoformat(), 0)
        ctl += (x - ctl) / CTL_J
        atl += (x - atl) / ATL_J
    return {
        "date": jour.isoformat(),
        "ctl": round(ctl, 1),
        "atl": round(atl, 1),
        "tsb": round(ctl - atl, 1),
        "ratio": round(atl / ctl, 2) if ctl >= 1 else None,
    }


def avis(ratio: float | None) -> str:
    if ratio is None:
        return "pas assez d'historique"
    if ratio > 1.5:
        return "hausse trop rapide, risque de blessure : alléger les prochains jours"
    if ratio > 1.3:
        return "hausse rapide : prudence, pas de séance en plus"
    if ratio >= 0.8:
        return "charge maîtrisée"
    return "charge en baisse (normal pendant l'affûtage ou une semaine de récupération)"


def phrase(ch: dict) -> str:
    r = ch["ratio"]
    return (
        f"Condition {ch['ctl']:.0f}, fatigue {ch['atl']:.0f}"
        + (f", rapport {r:.2f}" if r is not None else "")
        + f" : {avis(r)}"
    )


def du_jour(c, aujourdhui: dt.date, strava_acts: list[dict] | None = None) -> dict:
    """Charge au matin : jusqu'à la veille incluse (la séance du jour n'est pas encore faite). `veille` : charge de la veille, vélo compris."""
    veille = aujourdhui - dt.timedelta(days=1)
    charges = par_jour(c, veille, strava_acts=strava_acts)
    return {**calculer(charges, veille), "veille": round(charges.get(veille.isoformat(), 0))}
