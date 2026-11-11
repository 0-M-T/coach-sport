#!/usr/bin/env python3
import datetime as dt
import json
import re
import sys
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

from . import baikal, boucles, charge, course, decision, garmin, meteo, ntfy, nutrition, planif, texte
from . import chemins
from .config import BAIKAL_WEB, HA_URL_DEFAUT, load_config, race_date
from .profil import charger_profil

PARIS = ZoneInfo("Europe/Paris")
_p = charger_profil()
DEPART_DEFAUT = _p.depart_coords
MARQUEURS = chemins.state_dir()   # anti-doublon des briefings (remplacé dans les tests)


def get_coords(location_str):
    # « Route / Bitume plat » est un type de terrain, pas une adresse : seul un lieu avec chiffre ou virgule est géocodé
    if not location_str or "maison" in location_str.lower() or _p.depart_nom.lower() in location_str.lower() or not re.search(r"[\d,]", location_str):
        return DEPART_DEFAUT
    try:
        url = f"https://api-adresse.data.gouv.fr/search/?q={urllib.parse.quote(location_str)}&limit=1"
        with urllib.request.urlopen(url, timeout=5) as r:
            feats = json.loads(r.read().decode()).get("features", [])
            if feats:
                c = feats[0]["geometry"]["coordinates"]
                return c[1], c[0], feats[0]["properties"].get("city", location_str)
    except Exception as e:
        print(f"géocodage '{location_str}' : {e}", file=sys.stderr)
    return DEPART_DEFAUT


def nuit_disponible(forme: dict, today: str) -> bool:
    """Les données de la nuit sont là quand Garmin a calculé le score de sommeil du jour (pas celui de la veille)."""
    return (forme.get("sleep_hours") is not None and forme.get("sleep_score") is not None
            and forme.get("sleep_date") in (None, today))


def montre_non_portee(forme: dict) -> bool:
    """Pas de sommeil, presque aucune FC la nuit, mais des mesures depuis ce matin : la montre a été mise au réveil."""
    return (forme.get("sleep_hours") is None and forme.get("fc_nuit") is not None
            and forme["fc_nuit"] < 20 and (forme.get("fc_matin") or 0) >= 10)


INTERIEUR = ("renfo", "activation", "étirement", "etirement")


def en_exterieur(ligne: str) -> bool:
    """Séance dehors (course, vélo, rando) : seules celles-là ont besoin de la météo. Renfo, activation et étirements se font à la maison."""
    return not any(k in baikal.court(ligne).lower() for k in INTERIEUR)


def premiere_course(lignes: list[str]) -> str | None:
    """Première séance de course du jour : c'est elle qui fixe l'échéance du briefing, pas un renfo à 08:30."""
    return next((l for l in lignes if "CAP:" in l), None)


def echeance_passee(now: dt.datetime, ligne_seance: str | None, limite: str = "11:00") -> bool:
    """On n'attend plus les données : limite fixe, ou 20 min avant la séance si elle est plus tôt."""
    h, m = map(int, limite.split(":"))
    fin = now.replace(hour=h, minute=m, second=0, microsecond=0)
    d = baikal.debut(ligne_seance) if ligne_seance else None
    if d and d[0] == now.strftime("%Y-%m-%d"):
        fin = min(fin, dt.datetime.fromisoformat(f"{d[0]}T{d[1]}").replace(tzinfo=now.tzinfo) - dt.timedelta(minutes=20))
    return now >= fin


NOTE_NUIT = "Aucune donnée Garmin ce matin (montre non portée ou non synchronisée) : ouvre Garmin Connect pour forcer la synchro"


class Sources:
    """Collecte tolérante : une source en panne ne bloque pas le briefing, mais elle est dite (bloc « Sources en panne », priorité urgente)."""

    def __init__(self):
        self.problemes: list[str] = []

    def tenter(self, nom, fn, defaut=None):
        try:
            return fn()
        except Exception as e:
            self.problemes.append(f"{nom} : {type(e).__name__} {str(e)[:120]}")
            return defaut


def attendre_nuit(conf: dict, now: dt.datetime) -> bool:
    """Passage rapide du réveil (toutes les 10 min) : True tant que la nuit n'est pas synchronisée et que l'échéance n'est pas là.

    Une montre oubliée (pas de FC la nuit, des mesures depuis le matin) n'est pas attendue : les données n'existeront pas."""
    today = now.strftime("%Y-%m-%d")
    try:
        pret = garmin.nuit_prete(garmin.client(conf), today)
    except Exception as e:
        print(f"Garmin indisponible : {e}", file=sys.stderr)
        pret = False
    if not pret:
        try:
            n, m = garmin.fc_nuit_matin(garmin.client(conf), today)
            pret = montre_non_portee({"sleep_hours": None, "fc_nuit": n, "fc_matin": m})
        except Exception as e:
            print(f"FC Garmin indisponible : {e}", file=sys.stderr)
    if pret:
        return False
    lignes = []
    try:
        lignes = baikal.lister(today)
    except Exception as e:
        print(f"Baïkal indisponible : {e}", file=sys.stderr)
    return not echeance_passee(now, premiere_course(lignes), conf.get("COACH_REVEIL_LIMITE", "11:00"))


def _fmt(v, suf=""):
    return "n/d" if v is None else f"{v}{suf}"


def message_soir(demain: list[str], meteo_demain: dict | None) -> str:
    return texte.message(
        texte.bloc("Demain", [baikal.court(l) for l in demain] if demain else "Repos ou séance libre"),
        texte.bloc("Météo de demain", meteo.resume(meteo_demain) if meteo_demain else None),
        texte.bloc("À prévoir", meteo.conseils(meteo_demain) if meteo_demain else None, puces=True),
        texte.bloc("Repas", nutrition.repas_veille(demain), puces=True),
        texte.bloc("Ce soir", ["Écrans éteints à 22 h 30, coucher à 23 h", "Montre au poignet pour la nuit, et chargée"]))


def message_matin(sport: list[str], w: dict | None, forme: dict, sans_montre: bool, note_nuit: str | None, ch: dict | None,
                  parcours: dict | None, lignes_plan: list[str], alertes: list[str] = ()) -> str:
    """Briefing du matin à partir des données déjà collectées (aucun appel réseau)."""
    titres_jour = " ".join(baikal.court(l) for l in sport) or None
    conseils = decision.conseil(titres_jour, forme.get("sleep_hours"), forme.get("hrv_status"),
                                w["rafales"] if w else None, w["pluie_mm"] if w else None, forme)
    if sans_montre:
        conseils += decision.conseil_sans_donnees(titres_jour)
    conseils += list(alertes)
    hrv = texte.HRV.get((forme.get("hrv_status") or "").upper(), forme.get("hrv_status"))
    etat = ("Pas de données de sommeil cette nuit (montre non portée ?)" if sans_montre else note_nuit
            or f"Batterie corporelle {_fmt(forme.get('body_battery'), '/100')}, sommeil {_fmt(forme.get('sleep_score'), '/100')} "
               f"({texte.duree_h(forme.get('sleep_hours'))}), variabilité cardiaque {_fmt(hrv)}")
    fatigue = False if sans_montre else decision.fatigue(forme.get("sleep_hours"), forme.get("hrv_status"), forme)
    return texte.message(
        texte.bloc("Séance" if len(sport) < 2 else "Séances", [baikal.court(l) for l in sport] if sport else "Repos ou récupération active"),
        texte.bloc("Météo", meteo.resume(w) if w else None),
        texte.bloc("Forme", etat),
        texte.bloc("Charge", charge.phrase(ch) if ch else None),
        texte.bloc("Attention", conseils, puces=True),
        texte.bloc("Repas", nutrition.repas_jour(sport, fatigue), puces=True),
        texte.bloc("À prévoir", meteo.conseils(w) if w else None, puces=True),
        texte.bloc("Parcours conseillé", (f"{parcours['km']} km, +{parcours['dplus']} m, ta sortie du {parcours['date'][8:]}/{parcours['date'][5:7]} "
                                          f"(https://www.strava.com/activities/{parcours['id']})") if parcours else None),
        texte.bloc("Plan", lignes_plan, puces=True))


def run_agent_coach(soir=False, conf=None, force=False, reveil=False) -> int:
    """Briefing du matin ou du soir : anti-doublon, attente de la nuit, collecte, écritures du matin, message, envoi."""
    conf = load_config() if conf is None else conf
    marker = MARQUEURS / f"coach-brief-{'soir' if soir else 'matin'}"
    jour = dt.datetime.now(PARIS).strftime("%Y-%m-%d")
    if not force and marker.exists() and marker.read_text() == jour:
        print("Briefing déjà envoyé aujourd'hui (--force pour renvoyer)")
        return 0
    if reveil and dt.datetime.now(PARIS).strftime("%H:%M") < conf.get("COACH_REVEIL_DEBUT", "07:00"):
        return 0  # trop tôt : aucun appel Garmin
    now = dt.datetime.now(PARIS)
    today = now.strftime("%Y-%m-%d")
    if reveil and not soir and attendre_nuit(conf, now):
        print("Données de la nuit pas encore synchronisées : nouvel essai au prochain passage")
        return 0
    days_left = (race_date(conf) - now.date()).days

    # collecte
    src = Sources()
    sport = src.tenter("Baïkal", lambda: baikal.lister(today), [])
    lat, lon, _ = get_coords(baikal.lieu(sport[0]) if sport else None)
    prevision = src.tenter("Météo", lambda: meteo.fetch(lat, lon))
    duree = int(conf.get("COACH_SEANCE_MIN", 90))

    def fenetre(ligne):
        d = baikal.debut(ligne) if ligne else None
        if not (prevision and d) or d[1] == "journée":
            return None
        return src.tenter("Météo séance", lambda: meteo.fenetre(prevision, d[0], d[1], duree))

    forme = src.tenter("Garmin", lambda: garmin.forme(garmin.client(conf), today), {})
    sans_montre = montre_non_portee(forme)
    note_nuit = None
    if reveil and not soir and not sans_montre and not nuit_disponible(forme, today):
        if not echeance_passee(now, premiere_course(sport), conf.get("COACH_REVEIL_LIMITE", "11:00")):
            print("Données de la nuit pas encore synchronisées : nouvel essai au prochain passage")
            return 0
        note_nuit = NOTE_NUIT
        src.problemes = [p for p in src.problemes if not p.startswith("Garmin")]  # l'absence de données est dite par la note, pas par une alerte

    demain: list[str] = []
    if soir:
        demain = src.tenter("Baïkal demain", lambda: baikal.lister((now + dt.timedelta(days=1)).strftime("%Y-%m-%d")), [])
        if not demain and not src.problemes and not force:
            print("Pas de séance demain : pas de briefing du soir")
            return 0
        dehors = [l for l in demain if en_exterieur(l)]
        title, body = f"Coach du soir : J-{days_left} avant Lourdes-Tarbes", message_soir(demain, fenetre(dehors[0]) if dehors else None)
    else:
        dehors = [l for l in sport if en_exterieur(l)]
        w = fenetre(dehors[0]) if dehors else None   # pas de météo pour un renfo à la maison
        parcours = src.tenter("Parcours", lambda: boucles.suggere_pour_titre(baikal.court(dehors[0]).split(" ", 1)[1]), None) if dehors else None
        # écritures du matin, idempotentes : le plan, puis l'allègement éventuel du jour, puis la charge pour Home Assistant
        comp, notes_plan = src.tenter("Planification", lambda: planif.planifier(conf, 10, True, now), ([], []))
        # charge avant l'allègement : une grosse sortie vélo de la veille (compteur iGPSPORT, invisible pour Garmin) compte dans la fatigue
        sorties = src.tenter("Strava (charge)", lambda: charge.strava_recentes(conf, now.date()), None)
        ch = src.tenter("Charge Garmin", lambda: charge.du_jour(garmin.client(conf), now.date(), sorties))
        if ch:
            src.tenter("Charge enregistrée", lambda: planif.enregistrer_charge(ch))
            if forme and ch.get("veille", 0) > (forme.get("charge_veille") or 0):
                forme["charge_veille"] = ch["veille"]
        ajust = [] if sans_montre else src.tenter("Ajustement", lambda: planif.ajuster_jour(forme, now), [])
        alertes = []
        try:   # facultatifs : une panne est journalisée sans rendre le briefing urgent
            hist = planif.enregistrer_fc_repos(today, forme.get("fc_repos"))
            alertes = [a for a in [decision.fc_repos_elevee(hist, today)] if a]
            s = garmin.seuil(garmin.client(conf))
            if s:
                planif.memoriser("seuil", s)
        except Exception as e:
            print(f"[FC repos / seuil] échec : {e}", file=sys.stderr)
        title, body = f"Coach du matin : J-{days_left} avant Lourdes-Tarbes", message_matin(
            sport, w, forme, sans_montre, note_nuit, ch, parcours, planif.resume_changements(comp, notes_plan, ajust), alertes)

    if (days_left == 0 and not soir) or (days_left == 1 and soir):   # jour et veille du semi : le briefing de course remplace l'habituel
        lignes = demain if soir else sport
        d = baikal.debut(lignes[0]) if lignes else None
        depart = d[1] if d and d[1] != "journée" else course.DEPART_DEFAUT
        jour_course = (now + dt.timedelta(days=days_left)).strftime("%Y-%m-%d")   # pas `jour` : c'est le marqueur
        prev = src.tenter("Météo course", lambda: meteo.fetch(*course.LOURDES, 3))
        wc = src.tenter("Météo course", lambda: meteo.fenetre(prev, jour_course, depart, 100)) if prev else None
        title, body = (("Veille du semi de Lourdes-Tarbes", course.message_veille(wc, depart)) if soir
                       else ("Jour de course : semi de Lourdes-Tarbes", course.message_jour_j(wc, depart, forme)))

    # les pannes en dernier : toutes les sources du passage y figurent (avant, celles de la planification ou de la météo étaient perdues)
    body = texte.message(body, texte.bloc("Sources en panne", src.problemes, puces=True))
    actions = f"view, Agenda, {BAIKAL_WEB}; view, Tableau de bord, {conf.get('HA_URL', HA_URL_DEFAUT).rstrip('/')}/dashboard-sport/0"
    ntfy.envoyer(conf, title, body, actions, "urgent" if src.problemes else "default")
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(jour)
    print("Notification ntfy envoyée" + (f" ({len(src.problemes)} source(s) en panne)" if src.problemes else ""))
    return 1 if src.problemes else 0


if __name__ == "__main__":
    sys.exit(run_agent_coach(soir="--soir" in sys.argv, force="--force" in sys.argv))
