"""Enrichit les activités Strava synchronisées par Garmin : nom, description, type de séance.

Sans --apply, rien n'est écrit (dry-run). Ne touche qu'à un nom générique et une description vide.
"""
import datetime as dt
import json
import re
import sys
from zoneinfo import ZoneInfo

from . import baikal, humour, ntfy, strava, texte
from . import chemins
from .config import ecrire_json, load_config, race_date

PARIS = ZoneInfo("Europe/Paris")
GENERIC = re.compile(r"^(Morning|Lunch|Afternoon|Evening|Night) (Run|Ride|Workout|Walk|Weight Training)$")

STATE = chemins.state_path()
COURSE = ("Run", "TrailRun")
TARGET_SEC = 265  # 4'25/km


def workout_type(titre: str) -> int:
    """Strava Run : 0 normal, 1 course, 2 sortie longue, 3 séance."""
    t = titre.lower()
    if any(k in t for k in ("course", "compétition", "lourdes")):
        return 1
    if "longue" in t or "sl " in t:
        return 2
    if any(k in t for k in ("seuil", "as21", "vma", "400m", "piste", "fractionné")):
        return 3
    return 0


def famille_et_cible(date: str, titre: str | None) -> tuple[str | None, int]:
    """Famille suivie par la progression (seuil, as21) et allure cible de la séance du coach ce jour-là (sinon 4'25)."""
    t = (titre or "").lower()
    famille = "as21" if "as21" in t or "allure semi" in t or "rappel d'allure" in t else ("seuil" if "seuil" in t else None)
    cible = None
    if famille:
        from . import planif
        cible = planif.cible_du_jour(planif.charger(), date, famille)
    return famille, cible or TARGET_SEC


def seance_du_jour(date: str, heure: str | None = None) -> str | None:
    """Séance de course de l'agenda la plus proche de l'heure de départ. Jamais un renfo ou des étirements du même jour
    (le 10/11, le footing du club de 18:30 aurait pris le nom du renfo de 08:30)."""
    courses = [p for p in map(baikal.parse, baikal.lister(date))
               if p and p["heure"] != "journée" and any(k in p["titre"].lower() for k in MOTS_COURSE + ("groupe", "potes", "club", "rhune"))]
    if not courses:
        return None
    if heure:
        courses.sort(key=lambda p: abs(minutes_hm(p["heure"]) - minutes_hm(heure)))
    return courses[0]["titre"]


def minutes_hm(h: str) -> int:
    return int(h[:2]) * 60 + int(h[3:5])


def _groupes(laps: list[dict], cible: int = TARGET_SEC) -> list[list[dict]]:
    """Tours consécutifs à l'allure seuil (± 20 s) regroupés en blocs d'au moins 1,5 km ; les autres = récup."""
    groupes, cur = [], []
    for l in laps:
        if l.get("distance", 0) > 0 and l["moving_time"] / (l["distance"] / 1000) <= cible + 20:
            cur.append(l)
        elif cur:
            groupes.append(cur)
            cur = []
    if cur:
        groupes.append(cur)
    return [g for g in groupes if sum(l["distance"] for l in g) >= 1500]


def _blocs(laps: list[dict], cible: int = TARGET_SEC) -> list[list[float]]:
    """Blocs [distance, secondes]."""
    return [[sum(l["distance"] for l in g), sum(l["moving_time"] for l in g)] for g in _groupes(laps, cible)]


def fc_stabilisee(groupe: list[dict]) -> float | None:
    """FC moyenne du bloc sans son premier tour (la FC y monte encore), pondérée par le temps."""
    tours = [l for l in (groupe[1:] if len(groupe) > 1 else groupe) if l.get("average_heartrate")]
    t = sum(l["moving_time"] for l in tours)
    return sum(l["average_heartrate"] * l["moving_time"] for l in tours) / t if t else None


def verdict_seuil(fc: float, fcsl: int) -> str:
    """Au seuil : de FCSL - 5 à FCSL + 2 (au-dessus, l'effort ne tient pas 1 h ; dessous, il reste de la marge)."""
    return "au-dessus du seuil" if fc > fcsl + 2 else "au seuil" if fc >= fcsl - 5 else "sous le seuil"


def bilan(act: dict, titre: str | None, laps: list[dict], cible: int = TARGET_SEC, fcsl: int | None = None) -> list[str]:
    d = act["distance"]
    lignes = [f"{d / 1000:.2f} km à {strava.pace(d, act['moving_time'])}/km"
              + (f", FC moyenne {int(act['average_heartrate'])} bpm" if act.get("average_heartrate") else "")]
    if titre and workout_type(titre) == 3 and laps:
        for i, g in enumerate(_groupes(laps, cible)):
            dist, sec = sum(l["distance"] for l in g), sum(l["moving_time"] for l in g)
            p = sec / (dist / 1000)
            fc = fc_stabilisee(g)
            lignes.append(f"Bloc {i + 1} : {dist / 1000:.2f} km à {strava.pace(dist, sec)}/km ({int(p - cible):+d} s sur {cible // 60}'{cible % 60:02d})"
                          + (f", FC {fc:.0f} : {verdict_seuil(fc, fcsl)} ({fcsl})" if fc and fcsl else ""))
    elif (not titre or workout_type(titre) == 0) and act.get("average_heartrate"):
        lignes += analyse_endurance(act)
    return lignes


EF_FC_MAX, EF_LENTE, EF_RAPIDE = 145, 335, 315   # endurance : FC limite, repère d'allure 5'15 à 5'35/km


def analyse_endurance(act: dict) -> list[str]:
    """En endurance, la FC décide, l'allure n'est qu'un repère : une allure lente avec la bonne FC est une séance réussie."""
    fc, fmax = act["average_heartrate"], act.get("max_heartrate")
    allure = act["moving_time"] / (act["distance"] / 1000) if act.get("distance") else None
    if fc > EF_FC_MAX:
        out = [f"FC moyenne {fc:.0f}, au-dessus de la limite de {EF_FC_MAX} : trop vite pour de l'endurance, ralentis la prochaine fois (marche dans les côtes)"]
    else:
        out = [f"FC moyenne {fc:.0f} : {EF_FC_MAX - fc:.0f} bpm de marge sous la limite de {EF_FC_MAX}"]
        if allure and allure > EF_LENTE:
            out.append(f"Allure {strava.pace(act['distance'], act['moving_time'])}/km, plus lente que le repère de 5'15 à 5'35 : "
                       "normal, la FC passe avant l'allure (côtes, chaleur, fatigue du moment)")
        elif allure and allure < EF_RAPIDE:
            out.append(f"Allure {strava.pace(act['distance'], act['moving_time'])}/km avec une FC basse : la forme progresse")
    if fmax and fmax > EF_FC_MAX + 3 and fc <= EF_FC_MAX:
        out.append(f"Pointe à {fmax:.0f} : sans conséquence si elle est brève (une montée)")
    return out


def verdict(act: dict, titre: str | None, laps: list[dict], cible: int = TARGET_SEC) -> str | None:
    """Une ligne qui dit si la séance est réussie, selon le critère qui compte pour elle (FC en endurance, allure des blocs en qualité)."""
    prevu = re.search(r"(\d+) min", titre or "")
    faite = act["moving_time"] / 60
    duree = f", {faite:.0f} min sur {prevu[1]} prévues" if prevu and faite < 0.9 * int(prevu[1]) else ""
    if titre and workout_type(titre) == 3:
        bl = _blocs(laps, cible)
        if not bl:
            return None
        e = sum(sec / (dist / 1000) - cible for dist, sec in bl) / len(bl)
        if abs(e) <= 5:
            return f"Séance réussie : blocs dans la cible ({e:+.0f} s/km en moyenne){duree}"
        return f"Blocs {'plus rapides' if e < 0 else 'plus lents'} que la cible ({e:+.0f} s/km en moyenne){duree}"
    if (not titre or workout_type(titre) == 0) and act.get("average_heartrate"):
        if act["average_heartrate"] <= EF_FC_MAX:
            return "Séance réussie : endurance respectée" + (duree or (f", {faite:.0f} min comme prévu" if prevu else ""))
        return f"Trop rapide pour de l'endurance : FC moyenne {act['average_heartrate']:.0f}, limite {EF_FC_MAX}{duree}"
    return None


def reperes(titre: str | None) -> str | None:
    """Repères de la séance prévue, rappelés dans le débrief."""
    t = (titre or "").lower()
    if any(k in t for k in ("footing", "décrassage", "ef ")):
        return f"FC sous {EF_FC_MAX}, allure repère 5'15 à 5'35/km"
    return None


MOTS_COURSE = ("cap", "seuil", "as21", "vma", "footing", "ef ", "sortie longue", "course", "fractionné", "trail", "piste", "côtes")


def caler_agenda(act: dict, conf: dict, apply: bool) -> tuple[str, str | None]:
    """Recale l'événement Sport de la course sur l'heure réelle de départ.

    Renvoie (état, note) ; état : 'aucun' (pas d'événement de course ce jour), 'ok' (à l'heure), 'deplace'.
    Seuil de décalage : COACH_DECALAGE_MIN (10 min). Un événement non sportif du même jour n'est jamais touché.
    """
    reel = dt.datetime.fromisoformat(act["start_date_local"][:19])
    date = reel.date().isoformat()
    candidats = []
    for l in baikal.lister(date):
        d, m = baikal.debut(l), baikal.court(l)
        if d and baikal.ident(l) and any(k in m.lower() for k in MOTS_COURSE):
            prevu = dt.datetime.fromisoformat(f"{d[0]}T{d[1]}")
            candidats.append((abs((reel - prevu).total_seconds()), prevu, l))
    if not candidats:
        return "aucun", None
    ecart_s, prevu, ligne = min(candidats, key=lambda c: c[0])
    if ecart_s > 3 * 3600:
        return "aucun", None  # trop loin : probablement une autre séance
    seuil = int(conf.get("COACH_DECALAGE_MIN", 10))
    if ecart_s < seuil * 60:
        return "ok", None
    fin = reel + dt.timedelta(seconds=act.get("elapsed_time", act["moving_time"]))
    note = f"séance décalée de {prevu:%H:%M} à {reel:%H:%M} ({(reel - prevu).total_seconds() / 60:+.0f} min)"
    if apply:
        baikal.deplacer(baikal.ident(ligne), reel.strftime("%Y-%m-%dT%H:%M"), fin.strftime("%Y-%m-%dT%H:%M"))
        print(f"[AGENDA] {act['id']} {note}")
    else:
        print(f"[AGENDA DRY] {act['id']} {note}")
    return "deplace", note


def generique(nom: str) -> bool:
    """Nom généré par Garmin/Strava (« Afternoon Run », « Lunch Ride »...), jamais un nom écrit par Tom."""
    return texte.nom_fr(nom) != nom




def balade_du_chien(act: dict) -> bool:
    """Marche partie de la maison (à moins de 600 m), ou sans GPS : c'est la promenade du chien. Une randonnée (Hike) n'en est pas une. Le tag Strava « Avec un animal » n'est pas
    accessible par l'API (2026) : Tom le coche dans l'app s'il le veut ; le coach donne le nom."""
    if act.get("sport_type", act.get("type")) != "Walk":
        return False
    if "WithPet" in (act.get("tags") or []):   # tag « Avec un animal » coché par Tom : lisible par l'API, pas modifiable
        return True
    if not act.get("start_latlng"):
        return True   # marche sans GPS (le 10/11, la montre n'a enregistré aucune trace) : c'est la balade du chien
    from . import boucles, club
    try:
        maison = json.loads(boucles.CATALOGUE.read_text())["maison"]
    except (OSError, ValueError, KeyError):
        return False
    return club.distance_m(tuple(maison), tuple(act["start_latlng"])) <= 600


def nom_sans_seance(act: dict, deja: dict | None = None) -> str | None:
    n = texte.nom_fr(act["name"])
    if n == act["name"]:
        return None
    if balade_du_chien(act):
        return humour.nom_balade(act, deja)
    wt = act.get("workout_type")
    if act.get("sport_type", act.get("type")) in COURSE and wt in (2, 3):
        n = n.replace("Course", "Sortie longue" if wt == 2 else "Séance", 1)
    return n


def proposer(act: dict, titre: str | None, laps: list[dict], cible: int = TARGET_SEC, fcsl: int | None = None,
             deja: dict | None = None) -> dict | None:
    """act doit être le détail de l'activité (la liste ne contient pas la description).

    Description publique : la phrase d'humour seule. Note privée (visible de Tom seul) : le récap de la séance.
    Ne remplace jamais un nom écrit par Tom, une description non vide ni une note privée non vide.
    """
    out: dict = {}
    est_course = act.get("sport_type", act.get("type")) in COURSE
    if generique(act["name"]):
        if titre:
            out["name"] = re.sub(r"^CAP:\s*", "", titre)
            if est_course:   # les valeurs de workout_type diffèrent pour le vélo (10 à 12)
                out["workout_type"] = workout_type(titre)
        elif (n := nom_sans_seance(act, deja)):
            out["name"] = n
    if est_course and act["distance"] > 0:
        if not act.get("description"):
            bl = _blocs(laps, cible) if titre and workout_type(titre) == 3 else []
            ecart = sum(sec / (dist / 1000) - cible for dist, sec in bl) / len(bl) if bl else None
            wt = workout_type(titre) if titre else act.get("workout_type")
            out["description"] = humour.phrase(act, ecart, wt, deja)
        if not act.get("private_note"):
            out["private_note"] = recap(act, titre, laps, cible, fcsl)
    return out or None


def recap(act: dict, titre: str | None, laps: list[dict], cible: int = TARGET_SEC, fcsl: int | None = None) -> str:
    """Récap de la séance pour la note privée Strava : séance prévue, verdict, bilan, blocs ou analyse."""
    b = bilan(act, titre, laps, cible, fcsl)
    v = verdict(act, titre, laps, cible)
    return "\n".join(([f"Séance prévue : {re.sub(r'^CAP:\s*', '', titre)}"] if titre else []) + ([v] if v else []) + ["Bilan : " + b[0]] + b[1:])


def debriefing(act: dict, titre: str | None, laps: list[dict], demain: str | None, conf: dict, agenda: str | None = None,
               cible: int = TARGET_SEC, fcsl: int | None = None, deja: dict | None = None) -> tuple[str, str]:
    prop = proposer(act, titre, laps, cible, fcsl, deja)
    nom = (prop or {}).get("name") or texte.nom_fr(act["name"])
    b = bilan(act, titre, laps, cible, fcsl)
    recup = ("Repas complet dans l'heure, hydratation, étirements légers"
             if (titre and workout_type(titre) > 0) or act["distance"] >= 12000 else None)

    def sans_cap(s):
        return re.sub(r"\bCAP:\s*", "", s) if s else s

    m = act["moving_time"]
    bilan_ligne = f"{b[0]}, {m // 3600} h {m % 3600 // 60:02d}" if m >= 3600 else f"{b[0]} en {m // 60} min"
    if act.get("max_heartrate"):
        bilan_ligne += f" (FC max {act['max_heartrate']:.0f})"
    corps = texte.message(
        texte.bloc("Prévu", [x for x in (sans_cap(titre), reperes(titre)) if x]),
        texte.bloc("Verdict", verdict(act, titre, laps, cible)),
        texte.bloc("Bilan", bilan_ligne),
        texte.bloc("Blocs", b[1:]) if len(b) > 1 and b[1].startswith("Bloc") else texte.bloc("Analyse", b[1:]),
        texte.bloc("Récupération", recup), texte.bloc("Agenda", agenda and agenda.capitalize()),
        texte.bloc("Demain", sans_cap(demain) or "Repos ou séance libre"))
    return f"Séance terminée : {nom}", corps


MASQUER = ("Walk", "Yoga", "Pilates")   # le renfo reste dans le fil : Strava y détaille chaque exercice (choix de Tom, 10/11)
RENFO = ("WeightTraining", "Workout")


def velo_interieur(act: dict) -> bool:
    return act.get("sport_type", act.get("type")) in ("Ride", "VirtualRide") and not act.get("start_latlng")


def champs_auto(act: dict, paire: str | None = None) -> dict:
    """Champs posés par le coach à la première lecture : balades, yoga et vélo d'appartement masqués du fil (ils restent sur le profil),
    vélo d'appartement marqué home trainer, paire de chaussures prévue par le plan. Une valeur déjà choisie par Tom n'est pas touchée."""
    out = {}
    interieur = velo_interieur(act)
    if (act.get("sport_type", act.get("type")) in MASQUER or interieur) and not act.get("hide_from_home"):
        out["hide_from_home"] = True
    if interieur and not act.get("trainer"):
        out["trainer"] = True
    if paire and act.get("gear_id") != paire:
        out["gear_id"] = paire
    return out


def paire_strava(nom_plan: str | None, paires: dict[str, str]) -> str | None:
    """Identifiant Strava de la paire nommée par le plan (« Adidas Evo SL (paire 2) »). Aucune ou plusieurs paires qui conviennent : None."""
    if not nom_plan:
        return None
    def norm(s):
        return re.sub(r"[^a-z0-9 ]", " ", s.lower())
    numero = re.search(r"paire (\d)", nom_plan.lower())
    mots = [m for m in norm(re.sub(r"\(.*?\)", "", nom_plan)).split() if len(m) > 1 or m.isdigit()]
    ok = [g for g, n in paires.items() if all(m in norm(n).split() for m in mots)
          and (not numero or re.search(rf"(paire|\#|n°|no)?\s*{numero[1]}\b", n.lower()))]
    return ok[0] if len(ok) == 1 else None


def paire_prevue(act: dict, date: str, titre: str | None, conf: dict, paires: dict[str, str], access: str | None = None) -> str | None:
    """Paire du jour : Metaspeed le jour d'une course sur route (semi, 10 km, 5 km), sinon celle du plan ; l'ancienne Evo SL cède la place
    à la paire 2 dès qu'elle dépasse COACH_GEAR_MAX_KM (750 km)."""
    from . import plan
    route = [o["date"] for o in plan.OBJECTIFS if "24h" not in o["nom"].lower()]
    nom = plan.CARBONE if date in route and act.get("sport_type", act.get("type")) == "Run" else getattr(_planif_entree(date, titre), "chaussures", None)
    gid = paire_strava(nom, paires)
    if gid and nom == plan.EF_PAIRE and access:
        km = strava.call(access, f"/gear/{gid}").get("distance", 0) / 1000
        if km >= int(conf.get("COACH_GEAR_MAX_KM", 750)):
            return paire_strava(plan.SEUIL_BAS, paires)
    return gid


def _planif_entree(date: str, titre: str | None):
    from . import planif
    return planif.entree_du_plan(date, titre)


def renfo_du_jour(date: str, heure: str | None = None) -> str | None:
    """Renfo ou activation de l'agenda ce jour-là, le plus proche de l'heure de départ (pour nommer l'activité de musculation)."""
    seances = [p for p in map(baikal.parse, baikal.lister(date)) if p and p["heure"] != "journée" and p["titre"].startswith(("Renfo", "Activation"))]
    if heure:
        seances.sort(key=lambda p: abs(minutes_hm(p["heure"]) - minutes_hm(heure)))
    return seances[0]["titre"] if seances else None


def velo_du_jour(date: str) -> str | None:
    """Séance de vélo d'appartement de l'agenda ce jour-là (pour nommer l'activité)."""
    return next((p["titre"] for p in map(baikal.parse, baikal.lister(date)) if p and "vélo d'appartement" in p["titre"].lower()), None)


def paires_connues(state: dict, access: str, acts: list[dict]) -> dict[str, str]:
    """Paires de chaussures Strava (identifiant -> nom) : celles vues sur les activités récentes, lues une fois chacune."""
    paires = state.setdefault("paires", {})
    for gid in {a.get("gear_id") for a in acts if str(a.get("gear_id") or "").startswith("g")} - set(paires):
        paires[gid] = strava.call(access, f"/gear/{gid}").get("name", "")
    return paires


def humour_vu(state: dict) -> dict[str, str]:
    """Phrases d'humour et noms déjà posés sur Strava (phrase -> activité), pour ne jamais les répéter. Amorcé une fois avec l'existant."""
    if "humour_vu" not in state:
        vu: dict[str, str] = {}
        for source in ("done", "backfill"):
            for aid, rec in state.get(source, {}).items():
                apres = rec.get("apres") or {}
                tete = humour.sans_smiley((apres.get("description") or "").split("\n", 1)[0])
                for x in (tete, apres.get("name")):
                    if x and not x.startswith(("Bilan", "Séance prévue")):
                        vu.setdefault(x, aid)
        state["humour_vu"] = vu
    return state["humour_vu"]


def run(apply: bool = False, conf=None) -> int:
    conf = load_config() if conf is None else conf
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    state.setdefault("done", {})
    deja = humour_vu(state)
    state.setdefault("debrief", {})
    state.setdefault("agenda", {})

    def save():
        ecrire_json(STATE, state)

    access = strava.token(conf)
    from . import planif as _planif
    # FC au seuil : dernière valeur Garmin relevée au briefing du matin, sinon COACH_FCSL ; sans elle, pas de verdict par bloc
    fcsl = (_planif.charger().get("seuil") or {}).get("fc") or int(conf.get("COACH_FCSL", 0)) or None
    now = dt.datetime.now(dt.UTC)
    after = int((dt.datetime.now(PARIS) - dt.timedelta(days=3)).timestamp())
    acts = sorted(strava.activities(access, per_page=10, after=after), key=lambda a: a["start_date"])
    scope_err, n, vue = None, 0, False
    for act in acts:
        aid = str(act["id"])
        est_course = act.get("sport_type", act.get("type")) in COURSE
        if aid in state["done"] and (not est_course or (aid in state["debrief"] and aid in state["agenda"])):
            continue
        act = {**act, **strava.call(access, f"/activities/{act['id']}")}  # la liste n'a ni description ni note
        date = act["start_date_local"][:10]
        titre = (seance_du_jour(date, act["start_date_local"][11:16]) if est_course
                 else velo_du_jour(date) if velo_interieur(act)
                 else renfo_du_jour(date, act["start_date_local"][11:16]) if act.get("sport_type", act.get("type")) in RENFO else None)
        laps = strava.call(access, f"/activities/{act['id']}/laps") if est_course else []
        famille, cible = famille_et_cible(date, titre) if est_course else (None, TARGET_SEC)

        note_agenda = None
        if est_course and aid not in state["agenda"]:
            try:
                etat, note_agenda = caler_agenda(act, conf, apply)
                if apply:
                    state["agenda"][aid] = etat
                    save()
            except Exception as e:  # Baïkal en panne : on réessaiera au prochain passage, le reste continue
                print(f"[AGENDA] {aid} échec : {e}", file=sys.stderr)

        recent = now - dt.datetime.fromisoformat(act["start_date"].replace("Z", "+00:00")) < dt.timedelta(hours=12)
        if apply and est_course and aid not in state["debrief"]:
            vue = True
            if recent:
                dem = baikal.lister((dt.date.fromisoformat(date) + dt.timedelta(days=1)).isoformat())
                from . import course as _course
                if _course.est_course(act, race_date(conf)):
                    titre_msg, corps = _course.bilan(act, laps)
                else:
                    titre_msg, corps = debriefing(act, titre, laps, baikal.court(dem[0]) if dem else None, conf, note_agenda, cible, fcsl, deja)
                ntfy.envoyer(conf, titre_msg, corps)
                print(f"[DEBRIEF] {aid} envoyé")
            from . import club as _club
            if _club.au_club(act):   # séance du club reconnue par sa localisation : le coach adapte les séances voisines
                from . import planif
                planif.enregistrer_club(date, _club.est_fractionne(laps))
            if famille:   # bilan de la séance de qualité pour la progression des prochaines allures
                bl = _blocs(laps, cible)
                if bl:
                    from . import planif
                    planif.enregistrer_bilan(date, famille, cible, sum(sec / (dist / 1000) - cible for dist, sec in bl) / len(bl),
                                             act.get("average_heartrate"))
            state["debrief"][aid] = True  # même hors fenêtre de 12 h : pas de débrief tardif
            save()

        if aid in state["done"]:
            continue
        prop = proposer(act, titre, laps, cible, fcsl, deja) or {}
        try:   # chaussures prévues par le plan (catalogue des paires lu une fois par paire, puis gardé)
            paire = paire_prevue(act, date, titre, conf, paires_connues(state, access, acts), access) if est_course else None
        except Exception as e:
            print(f"[CHAUSSURES] {aid} : {e}", file=sys.stderr)
            paire = None
        prop = {**prop, **champs_auto(act, paire)} or None
        if not prop:
            state["done"][aid] = {"skipped": True}
            if apply:
                save()
            continue
        print(f"[{'APPLY' if apply else 'DRY'}] {aid} {act['name']!r} -> {json.dumps(prop, ensure_ascii=False)}")
        if apply:
            try:
                strava.call(access, f"/activities/{act['id']}", "PUT", prop)
            except strava.ScopeError as e:
                scope_err = e  # le débrief est déjà parti ; on réessaiera le renommage au prochain passage
                continue
            state["done"][aid] = {"avant": {k: act.get(k) for k in prop}, "apres": prop}
            save()
            n += 1
    if apply and acts:
        derniere = str(acts[-1]["id"])
        if derniere != state.get("ha_last") or n:  # nouvelle activité ou renommage : capteurs Home Assistant à jour
            try:
                from .strava_sync import sync_strava_to_ha
                sync_strava_to_ha(conf)
                state["ha_last"] = derniere
                save()
            except Exception as e:
                print(f"[HA] échec : {e}", file=sys.stderr)
    if apply and vue:
        try:
            from . import materiel
            materiel.verifier(conf, access)
        except Exception as e:  # une alerte matériel ratée ne bloque ni le débrief ni le renommage
            print(f"[MATERIEL] échec : {e}", file=sys.stderr)
    if scope_err:
        raise scope_err
    return n


def backfill(jours: int = 60, apply: bool = False, conf=None) -> int:
    """Passage unique sur l'historique : noms génériques en français, description vide complétée.

    Pas de débrief, pas de recalage d'agenda. Ancienne valeur gardée dans l'état pour revenir en arrière.
    """
    import time
    conf = load_config() if conf is None else conf
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    state.setdefault("backfill", {})
    deja = humour_vu(state)
    access = strava.token(conf)
    after = int((dt.datetime.now(PARIS) - dt.timedelta(days=jours)).timestamp())
    n = 0
    for act in sorted(strava.activities(access, per_page=100, after=after), key=lambda a: a["start_date"]):
        aid = str(act["id"])
        if aid in state["backfill"]:
            continue
        est_course = act.get("sport_type", act.get("type")) in COURSE
        if not est_course and not generique(act["name"]):
            continue  # rien à faire : on évite l'appel de détail
        act = {**act, **strava.call(access, f"/activities/{act['id']}")}
        # Historique : aucun titre Baïkal (une séance du même jour peut ne rien avoir à faire avec l'activité)
        prop = proposer(act, None, [], deja=deja)
        time.sleep(0.3)  # quota Strava : 100 requêtes / 15 min
        if not prop:
            continue
        print(f"[{'APPLY' if apply else 'DRY'}] {act['start_date_local'][:10]} {act['name']!r} -> "
              f"{prop.get('name', '(nom inchangé)')}" + (" + description" if "description" in prop else ""))
        if apply:
            strava.call(access, f"/activities/{act['id']}", "PUT", prop)
            state["backfill"][aid] = {"avant": {k: act.get(k) for k in prop}, "apres": prop}
            ecrire_json(STATE, state)
        n += 1
    return n


def humour_retroactif(apply: bool = False, conf=None) -> int:
    """Ajoute la phrase d'humour aux descriptions écrites par le coach avant son arrivée.

    Ne touche qu'à une description strictement identique à celle que le coach a posée (jamais un texte retouché par Tom).
    """
    import time
    conf = load_config() if conf is None else conf
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    state.setdefault("humour", {})
    deja = humour_vu(state)
    access = strava.token(conf)
    n = 0
    for source in ("done", "backfill"):
        for aid, rec in state.get(source, {}).items():
            desc = (rec.get("apres") or {}).get("description")
            if not desc or aid in state["humour"]:
                continue
            if not desc.startswith(("Bilan", "Séance prévue")):  # déjà une phrase d'humour en tête
                state["humour"][aid] = "déjà faite"
                continue
            act = strava.call(access, f"/activities/{aid}")
            time.sleep(0.3)
            if act.get("description") != desc:
                state["humour"][aid] = "modifiée par Tom, ignorée"
                continue
            ecarts = [int(x) for x in re.findall(r"\(([+-]\d+) ?s", desc)]
            ecart = sum(ecarts) / len(ecarts) if ecarts else None
            wt = (rec.get("apres") or {}).get("workout_type", act.get("workout_type"))
            nouvelle = humour.phrase(act, ecart, wt, deja) + "\n\n" + desc
            print(f"[{'APPLY' if apply else 'DRY'}] {act['start_date_local'][:10]} {act['name']!r} : {nouvelle.splitlines()[0]}")
            if apply:
                strava.call(access, f"/activities/{aid}", "PUT", {"description": nouvelle})
                state["humour"][aid] = "ok"
                ecrire_json(STATE, state)
            n += 1
    return n
