"""Briefing du dimanche : récap de la semaine écoulée (lun-dim) et préparation de la semaine à venir."""
import datetime as dt
import re
import sys
from zoneinfo import ZoneInfo

from . import baikal, charge, garmin, meteo, ntfy, planif, strava, texte
from .config import BAIKAL_WEB, load_config, race_date

from . import chemins

PARIS = ZoneInfo("Europe/Paris")
COURSE = ("Run", "TrailRun")
MARQUEURS = chemins.state_dir()


def lisible(j: dict) -> str | None:
    """Décision du journal en une phrase. Seuls déplacements, retraits et allègements intéressent Tom (pas les créations de routine)."""
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})\|\w+ (.+?)( (\d{2}:\d{2})(->(\d{2}:\d{2}))?)?$", j["detail"])
    if j["action"] == "maj" and m:
        if m[7]:   # ancien et nouvel horaire connus : on n'annonce que les vrais déplacements
            return f"{m[3]}/{m[2]} : {m[4]} déplacée de {m[6]} à {m[8]}" if m[6] != m[8] else None
        return f"{m[3]}/{m[2]} : {m[4]} déplacée à {m[6]}" if m[6] else None
    if j["action"] == "retrait" and m:
        return f"{m[3]}/{m[2]} : {m[4]} retirée du plan"
    if j["action"] == "allegement":
        d = re.match(r"(\d{4})-(\d{2})-(\d{2})\|", j["detail"])
        return f"{d[3]}/{d[2]} : séance dure remplacée par un footing EF (récupération insuffisante)" if d else None
    return None


def totaux(acts: list[dict]) -> dict:
    runs = [a for a in acts if a.get("sport_type", a.get("type")) in COURSE]
    autres = [a for a in acts if a not in runs]
    km = sum(a["distance"] for a in runs) / 1000
    sec = sum(a["moving_time"] for a in runs)
    fc = [a["average_heartrate"] for a in runs if a.get("average_heartrate")]
    return {"n": len(runs), "km": km, "sec": sec, "dplus": sum(a.get("total_elevation_gain", 0) for a in runs),
            "allure": strava.pace(km * 1000, sec) if km else None,
            "fc": round(sum(fc) / len(fc)) if fc else None,
            "seances": sum(1 for a in runs if a.get("workout_type") == 3),
            "longue": max((a["distance"] for a in runs), default=0) / 1000,
            "autres": autres}


def volume(cette: float, precedente: float) -> str:
    if not precedente:
        return f"{cette:.1f} km cette semaine (pas de semaine précédente pour comparer)"
    v = (cette - precedente) / precedente * 100
    avis = " : hausse supérieure à 10 %, prudence sur la semaine à venir" if v > 10 else ""
    return f"{cette:.1f} km contre {precedente:.1f} km la semaine d'avant ({v:+.0f} %){avis}"


def plan_suivi(prevues: list[str], acts: list[dict]) -> tuple[list[str], int]:
    jours_actifs = {a["start_date_local"][:10] for a in acts}
    lignes, faites = [], 0
    for l in prevues:
        d = baikal.debut(l)
        if not d:
            continue
        ok = d[0] in jours_actifs
        faites += ok
        lignes.append(f"{'fait' if ok else 'manqué'} : {texte.jour_court(d[0])} {baikal.court(l)}")
    return lignes, faites


def run(conf=None, force=False) -> int:
    from .agent_coach import get_coords
    conf = load_config() if conf is None else conf
    now = dt.datetime.now(PARIS)
    iso = now.isocalendar()
    marker = MARQUEURS / "coach-brief-semaine"
    cle = f"{iso.year}-{iso.week}"
    if not force and marker.exists() and marker.read_text() == cle:
        print("Récap hebdomadaire déjà envoyé cette semaine")
        return 0
    problemes: list[str] = []

    def tenter(nom, fn, defaut=None):
        try:
            return fn()
        except Exception as e:
            problemes.append(f"{nom} : {type(e).__name__} {str(e)[:100]}")
            return defaut

    today = now.date()
    debut_sem = today - dt.timedelta(days=6)
    debut_prec = today - dt.timedelta(days=13)
    acts = tenter("Strava", lambda: strava.activities(strava.token(conf), 60,
                                                      int(dt.datetime.combine(debut_prec, dt.time(), PARIS).timestamp())), [])
    cette = [a for a in acts if a["start_date_local"][:10] >= debut_sem.isoformat()]
    prec = [a for a in acts if a["start_date_local"][:10] < debut_sem.isoformat()]
    t, tp = totaux(cette), totaux(prec)

    prevues = tenter("Baïkal", lambda: baikal.lister(debut_sem.isoformat(), today.isoformat()), [])
    suivi, faites = plan_suivi(prevues, cette)

    def sommeil():
        c = garmin.client(conf)
        jours = [garmin.forme(c, (today - dt.timedelta(days=i)).isoformat(), avec_charge=False) for i in range(7)]
        h = [j["sleep_hours"] for j in jours if j["sleep_hours"]]
        sc = [j["sleep_score"] for j in jours if j["sleep_score"]]
        bad = sum(1 for j in jours if (j["hrv_status"] or "").upper() in ("UNBALANCED", "LOW", "POOR"))
        sans = 7 - len(h)
        return [f"Moyenne {texte.duree_h(sum(h) / len(h))} par nuit, score {sum(sc) / len(sc):.0f}/100 "
                f"({len(h)} nuits mesurées sur 7" + (f", {sans} sans montre" if sans else "") + ")"
                if h and sc else "Pas de données de sommeil",
                f"Variabilité cardiaque dégradée {bad} jour(s) sur 7"]
    nuits = tenter("Garmin", sommeil, [])
    ch = tenter("Charge Garmin", lambda: charge.du_jour(garmin.client(conf), today + dt.timedelta(days=1),
                                                         charge.strava_recentes(conf, today + dt.timedelta(days=1))))

    # le coach prépare la semaine suivante avant d'en parler : séances placées selon l'agenda
    comp, notes_plan = tenter("Planification", lambda: planif.planifier(conf, 14, True), ([], []))
    journal = [x for x in (lisible(j) for j in planif.charger().get("journal", [])
                           if j["ts"][:10] >= (today - dt.timedelta(days=7)).isoformat()) if x][-8:]

    # semaine à venir : lundi à dimanche
    debut_next = today + dt.timedelta(days=1)
    fin_next = today + dt.timedelta(days=7)
    avenir = tenter("Baïkal à venir", lambda: baikal.lister(debut_next.isoformat(), fin_next.isoformat()), [])
    travail = tenter("Baïkal travail", lambda: baikal.lister(debut_next.isoformat(), fin_next.isoformat(), "Travail"), [])
    lat, lon, _ = get_coords(None)
    prev = tenter("Météo", lambda: meteo.fetch(lat, lon, 7))
    duree = int(conf.get("COACH_SEANCE_MIN", 90))
    seances = []
    for l in avenir:
        d = baikal.debut(l)
        w = None
        if prev and d:
            try:
                w = meteo.fenetre(prev, d[0], d[1], duree)
            except ValueError:
                w = None
        seances.append(f"{texte.jour_court(d[0])} {baikal.court(l)}" if d else l)
        if w:
            seances[-1] += f"\n  {w['ressenti_min']:.0f}°C, pluie {w['pluie_prob']:.0f} %, vent {w['vent']:.0f} km/h"
    jours_course = (race_date(conf) - today).days
    club = []
    for l in avenir:
        p = baikal.parse(l)
        if p and p["heure"] != "journée" and dt.date.fromisoformat(p["date"]).weekday() in (1, 3):
            v = planif.compatible_club(p["titre"])
            if v:
                club.append(f"{texte.jour_court(p['date'])} {p['titre']} : {v}")

    def ligne_course(x):
        return (f"{x['n']} sortie{'s' if x['n'] > 1 else ''}, {x['km']:.1f} km, {x['sec'] // 3600} h {x['sec'] % 3600 // 60:02d}, allure moyenne {x['allure']}/km, "
                f"D+ {x['dplus']:.0f} m" + (f", FC moyenne {x['fc']} bpm" if x["fc"] else "")) if x["n"] else "Aucune sortie"
    autres = [f"{texte.nom_fr(a['name'])} : {a['distance'] / 1000:.1f} km" for a in t["autres"] if a["distance"] > 0]
    pannes = texte.bloc("Sources en panne", problemes, puces=True)
    corps = texte.message(
        texte.bloc("Course à pied", [ligne_course(t), f"{t['seances']} séance{'s' if t['seances'] > 1 else ''} de qualité, sortie la plus longue {t['longue']:.1f} km"] if t["n"] else "Aucune sortie"),
        texte.bloc("Vélo et autres", autres, puces=True),
        texte.bloc("Séances prévues", [f"{faites} sur {len(suivi)} réalisées"] + suivi if suivi else None, puces=False),
        texte.bloc("Charge", [volume(t["km"], tp["km"])] + ([charge.phrase(ch)] if ch else [])),
        texte.bloc("Sommeil", nuits),
        texte.bloc("Semaine à venir", seances or "Aucune séance planifiée dans l'agenda", puces=bool(seances)),
        texte.bloc("Décisions du coach", planif.resume_changements(comp, notes_plan, []) + journal, puces=True),
        texte.bloc("Club ASM (mardi et jeudi, 17:30 fractionné, 18:30 au choix)", club, puces=True),
        texte.bloc("Contraintes", [f"{texte.jour_court(baikal.debut(l)[0])} {baikal.court(l)}"
                                   for l in travail if baikal.debut(l)][:6], puces=True),
        pannes)
    ntfy.envoyer(conf, f"Coach de la semaine : J-{jours_course} avant Lourdes-Tarbes", corps,
              f"view, Agenda, {BAIKAL_WEB}", "urgent" if problemes else "default")
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(cle)
    print("Récap hebdomadaire envoyé")
    return 1 if problemes else 0


if __name__ == "__main__":
    sys.exit(run(force="--force" in sys.argv))
