"""Rejeu : applique les règles du coach (allègement selon la forme, progression des allures) à l'historique réel.

Sert à calibrer les seuils avant de leur laisser modifier l'agenda : combien de jours auraient été jugés fatigués,
sur combien de séances dures, et que dit la progression des bilans passés.
"""
import datetime as dt
import time

from . import charge, decision, garmin, progression, strava
from .config import load_config

MOTS_DURS = ("seuil", "as21", "vma", "fractionné", "frac", "piste", "tempo")


def est_qualite(a: dict) -> bool:
    return (a.get("sport_type", a.get("type")) in ("Run", "TrailRun") and
            (a.get("workout_type") == 3 or any(k in a.get("name", "").lower() for k in MOTS_DURS)))


def allure_blocs(laps: list[dict], cible: int) -> float | None:
    rapides = [l for l in laps if l.get("distance", 0) >= 400 and l["moving_time"] / (l["distance"] / 1000) <= cible + 25]
    if not rapides:
        return None
    d, t = sum(l["distance"] for l in rapides), sum(l["moving_time"] for l in rapides)
    return t / (d / 1000)


def rejouer(jours: int = 28, conf=None, pause: float = 0.4, avec_strava: bool = True) -> dict:
    conf = load_config() if conf is None else conf
    c = garmin.client(conf)
    aujourdhui = dt.date.today()
    debut = aujourdhui - dt.timedelta(days=jours)
    formes = {}
    charges: dict[str, float] = {}
    garmin_acts = c.get_activities(0, 200) or []
    for a in garmin_acts:   # une seule lecture : charge d'entraînement par jour
        j = a["startTimeLocal"][:10]
        charges[j] = charges.get(j, 0) + (a.get("activityTrainingLoad") or 0)
    if avec_strava:   # vélo sur le compteur iGPSPORT, invisible pour Garmin
        charge.ajouter_strava(charges, garmin_acts, charge.strava_recentes(conf, aujourdhui, jours + 7))
    for i in range(jours, 0, -1):
        d = (aujourdhui - dt.timedelta(days=i)).isoformat()
        try:
            formes[d] = garmin.forme(c, d, charges=charges)
        except Exception as e:
            formes[d] = {"erreur": str(e)[:60]}
        time.sleep(pause)
    tok = strava.token(conf)
    acts = strava.activities(tok, 100, int(dt.datetime.combine(debut, dt.time()).timestamp()))
    qualite = [a for a in acts if est_qualite(a)]
    par_jour = {}
    for a in qualite:
        par_jour.setdefault(a["start_date_local"][:10], []).append(a)

    lignes, fatigues, durs_sur_fatigue = [], 0, []
    for d, f in formes.items():
        connue = f.get("sleep_hours") is not None or f.get("hrv_status")
        fat_ancienne = decision.fatigue(f.get("sleep_hours"), f.get("hrv_status")) if connue else None
        fat = decision.fatigue(f.get("sleep_hours"), f.get("hrv_status"), f) if connue else None
        inconnue = f.get("sleep_hours") is None and not f.get("hrv_status")
        dur = par_jour.get(d, [])
        fatigues += bool(fat)
        if fat and dur:
            durs_sur_fatigue.append(d)
        lignes.append({"date": d, "sommeil": f.get("sleep_hours"), "vfc": f.get("hrv_status"), "fatigue": fat, "ancienne": fat_ancienne,
                       "signaux": decision.signaux(f),
                       "inconnue": inconnue, "dure": [a["name"] for a in dur]})

    # progression : bilans d'après les séances « AS21 » du passé (cible 4'25) et ce que la règle aurait décidé après chacune
    bilans, historique = [], []
    for a in sorted((x for x in qualite if "as21" in x.get("name", "").lower()), key=lambda x: x["start_date"]):
        laps = strava.call(tok, f"/activities/{a['id']}/laps")
        al = allure_blocs(laps, 265)
        time.sleep(pause)
        if al is None:
            continue
        b = {"date": a["start_date_local"][:10], "famille": "as21", "cible": 265 + (progression.correction(bilans, "as21", 265)[0]),
             "ecart": al - 265, "fc": a.get("average_heartrate")}
        bilans.append(b)
        corr, raison = progression.correction(bilans, "as21", 265)
        historique.append({**b, "apres": corr, "raison": raison})
    return {"jours": jours, "lignes": lignes, "fatigues": fatigues, "fatigues_ancienne": sum(1 for l in lignes if l["ancienne"]), "durs_sur_fatigue": durs_sur_fatigue,
            "n_qualite": len(qualite), "progression": historique}


def formater(r: dict) -> str:
    mesures = [l for l in r["lignes"] if not l["inconnue"]]
    out = [f"Rejeu sur {r['jours']} jours : {len(mesures)} jours avec données de forme, {r['fatigues']} jugés fatigués "
           f"({(100 * r['fatigues'] / len(mesures)) if mesures else 0:.0f} %), {r['n_qualite']} séances de qualité."]
    out.append(f"Règle précédente (sommeil et VFC seuls) : {r['fatigues_ancienne']} jours ; avec les signaux fins : {r['fatigues']} jours.")
    for l in r["lignes"]:
        if l["fatigue"] and not l["ancienne"]:
            out.append(f"  ajouté par les signaux fins : {l['date']} : {' ; '.join(l['signaux'])}")
    out.append(f"Séances de qualité faites un jour jugé fatigué : {len(r['durs_sur_fatigue'])} ({', '.join(r['durs_sur_fatigue']) or 'aucune'}).")
    out.append("Jours sans données de sommeil : " + (", ".join(l["date"][5:] for l in r["lignes"] if l["inconnue"]) or "aucun"))
    for l in r["lignes"]:
        if l["fatigue"] or l["dure"]:
            out.append(f"  {l['date']} sommeil {l['sommeil']} h, VFC {l['vfc']}, {'FATIGUE' if l['fatigue'] else 'ok'}"
                       + (f" | dure : {', '.join(l['dure'])}" if l["dure"] else ""))
    for h in r["progression"]:
        out.append(f"  progression {h['date']} : écart {h['ecart']:+.1f} s/km (cible {h['cible']}) -> correction {h['apres']:+d} {h['raison']}")
    return "\n".join(out)
