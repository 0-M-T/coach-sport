"""Planification autonome : les séances du plan, placées dans l'agenda selon les contraintes, ajustées chaque jour.

Principes (voir docs/PLAN_AUTONOMIE_COACH.md) :
- le coach ne modifie que les événements qu'il a créés et qui n'ont pas été touchés par Tom ;
- `[fixe]` dans le titre, ou un horaire/titre modifié à la main, verrouille l'événement ;
- une séance dure n'est jamais déplacée en silence : elle change de créneau dans la journée ou elle est signalée.
"""
import dataclasses
import datetime as dt
import hashlib
import json
import os
import re
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from . import baikal, chemins, decision, exercices_fr, fiche, garmin_renfo, nutrition, progression
from .plan import SEMAINES, Entree, ef

PARIS = ZoneInfo("Europe/Paris")

STATE = chemins.planif_path()
CATEGORIE = "coach-auto"
BLOQUE_MATIN = ("forum", "hunger", "chantier", "breut", "entretien")
MARQUE = "Généré par le coach. Modifie librement ; ajoute [fixe] au titre pour verrouiller."


@dataclass
class Seance:
    date: str
    heure: str
    duree: int
    titre: str
    description: str
    kind: str
    dure: bool
    origine_cle: str | None = None   # clé d'origine si la séance a été déplacée à un autre jour
    etapes: tuple = ()               # séance structurée pour la montre
    html: str = ""                   # description en HTML (Thunderbird, Outlook), dérivée de `description`

    @property
    def cle(self) -> str:
        return f"{self.date}|{self.kind}"

    @property
    def empreinte(self) -> str:
        return hashlib.sha1(f"{self.heure}|{self.duree}|{self.titre}|{self.description}|{json.dumps(self.etapes, default=list)}".encode()).hexdigest()[:12]

    @property
    def fin(self) -> str:
        d = dt.datetime.fromisoformat(f"{self.date}T{self.heure}") + dt.timedelta(minutes=self.duree)
        return d.strftime("%Y-%m-%dT%H:%M")


def minutes(h: str) -> int:
    return int(h[:2]) * 60 + int(h[3:])


def fiche_seance(e: Entree, date: str = "", heure: str = "") -> tuple[str, list[tuple[str, list[str]]]]:
    """Titre et sections de la description d'une séance (voir `fiche.py`)."""
    if e.kind == "velo_maison":
        materiel = ("Vélo d'appartement, résistance légère, cadence 85 à 95 tr/min. FC sous 128 : tu dois pouvoir parler sans effort. "
                    "Plus dur que ça, ce n'est plus de la récupération.")
        apres = "Rien de plus : du volume d'endurance sans impact, pas une séance."
    elif e.kind == "etirements":
        materiel = "Tapis, rouleau de massage, sangle ou élastique. Étirements statiques de 30 à 45 s, jamais jusqu'à la douleur, pas de rebond."
        apres = "Boire, repos. Jour de récupération : pas d'effort en plus."
    elif e.kind in ("renfo", "activation"):
        materiel = ("Banc, haltères, élastiques, ab-wheel, corde, tapis, rouleau, vélo d'appartement. "
                    + ("Échauffement : 15 min de vélo d'appartement souple (FC sous 128, cadence 85 à 95), compris dans la durée, "
                       if e.kind == "renfo" and e.titre.startswith("Renfo") and "Enchaîné juste après" not in e.corps else "Échauffement 8 min (corde ou vélo) ")
                    + "avant toute charge, jamais d'excentrique à froid (mollets).")
        apres = "Rouleau 5 min, mobilité du soir."
        if e.kind == "renfo" and "mollets" in e.corps.lower():
            materiel += (" Mollets : ils se renforcent, on ne les ménage pas. Ajoute 1 à 2 kg quand les séries sont propres et lentes ; une douleur vive ou une tension aiguë "
                         "arrête l'exercice.")
    else:
        materiel = f"Chaussures : {e.chaussures}. Eau, montre chargée, FC en brassard si besoin."
        apres = "Repas complet dans l'heure, mobilité du soir 10 min (mollets, triceps sural, psoas)."
    repas = nutrition.repas_jour([f"{date} {heure}  [Sport] {titre_agenda(e)}  — x.ics"]) if heure and e.kind in KINDS_COURSE + ("velo",) else []
    corps = fiche.lignes_renfo(e.corps) if e.kind in ("renfo", "activation", "etirements") else fiche.phrases(e.corps)
    exos = exercices_fr.lignes(garmin_renfo.code_de(e.titre) or "") if e.kind == "renfo" else []
    return e.titre, [("Séance", corps), ("Exercices (noms de la montre)", exos), ("Matériel", fiche.phrases(materiel)),
                     ("Repas", repas + (["Le briefing du matin confirme (pas à jeun si fatigue)"] if repas else [])), ("Après", fiche.phrases(apres))]


def description(e: Entree, date: str = "", heure: str = "") -> str:
    return fiche.texte(*fiche_seance(e, date, heure), MARQUE)


def description_html(e: Entree, date: str = "", heure: str = "") -> str:
    return fiche.en_html(*fiche_seance(e, date, heure), MARQUE)


def titre_agenda(e: Entree) -> str:
    return f"CAP: {e.titre}" if e.kind in ("ef", "seuil", "as21", "longue", "cotes") else e.titre


def occupations_range(debut: str, fin: str) -> dict[str, list[dict]]:
    """Événements Travail, Personnel et Famille de la fenêtre, groupés par jour (4 requêtes pour toute la fenêtre).

    Une « journée » bloque le matin si c'est un vrai engagement. Sans heure de fin connue : 90 min.
    """
    out: dict[str, list[dict]] = {}
    miens = set(charger().get("evenements", {}))
    for cal in ("Travail", "Personnel", "Famille", "Sport"):  # Sport : les séances que Tom a ajoutées lui-même occupent aussi le créneau
        for l in baikal.lister(debut, fin, cal=cal, fins=True):
            p = baikal.parse(l)
            if not p or (cal == "Sport" and (p["id"] in miens or p["heure"] == "journée")):
                continue
            bloque = any(k in p["titre"].lower() for k in BLOQUE_MATIN)
            if p["heure"] == "journée":
                ev = {"debut": None, "fin": None, "bloque": bloque, "titre": p["titre"]}
            else:
                d = minutes(p["heure"])
                ev = {"debut": d, "fin": minutes(p["fin"]) if p["fin"] else d + 90, "bloque": bloque, "titre": p["titre"]}
            out.setdefault(p["date"], []).append(ev)
    return out


MOTS_GROUPE = ("groupe", "potes", "rhune", "[fixe]", "club", "asm")
VELO = re.compile(r"\b(vélo|velo|vtt|cyclo|gravel)\b", re.I)
FACILE = re.compile(r"\b(ef|facile|footing|souple|rando|marche|balade)\b", re.I)
KINDS_COURSE = ("ef", "seuil", "as21", "longue", "cotes")


def groupes_range(debut: str, fin: str) -> dict[str, dict]:
    """Séances de sport ajoutées par Tom (pas par le coach) qui portent « groupe », « potes », « Rhune » ou « [fixe] » dans le titre.

    Elles remplacent la séance de course prévue ce jour-là. Sauf mot « facile », « souple », « rando »... elles comptent comme séance dure.
    """
    etat = charger()
    miens = set(etat.get("evenements", {}))
    veille = (dt.date.fromisoformat(debut) - dt.timedelta(days=1)).isoformat()
    out: dict[str, dict] = {d: {"titre": "Club ASM (détecté par la localisation)", "dure": v["dure"]}
                            for d, v in etat.get("club", {}).items() if d >= veille}
    for l in baikal.lister(veille, fin, cal="Sport", fins=True):
        p = baikal.parse(l)
        if not p or p["id"] in miens or p["heure"] == "journée":
            continue
        t = p["titre"].lower()
        if any(k in t for k in MOTS_GROUPE):
            velo = bool(VELO.search(p["titre"]))
            duree = (minutes(p["fin"]) - minutes(p["heure"])) if p["fin"] else 0
            # Sortie de vélo de groupe : elle occupe le créneau mais ne remplace pas la course et n'allège rien, sauf si elle dure 3 h ou plus
            dure = (duree >= 180) if velo else not FACILE.search(p["titre"])
            out[p["date"]] = {"titre": p["titre"], "dure": dure, "velo": velo}
    return out


def libre(heure: str, duree: int, occupe: list[dict]) -> bool:
    """15 min de battement autour de chaque événement, sauf `marge` explicite (séance enchaînée : 0)."""
    h, fin = minutes(heure), minutes(heure) + duree
    for ev in occupe:
        m = ev.get("marge", 15)
        if ev["debut"] is None:
            if ev["bloque"] and h < 12 * 60:
                return False
        elif h < ev["fin"] + m and fin > ev["debut"] - m:
            return False
    return True


def hm(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


VELO_ECHAUFFEMENT = 15   # min de vélo d'appartement en tête de renfo
VELO_FC = (100, 128)      # récupération : sous la FC du footing EF (145)


def velo_minutes(date: dt.date) -> int | None:
    """Vélo d'appartement autorisé ce jour-là : 20 min, 15 min la semaine d'un objectif (J-6 à J-3), rien les deux jours avant ni le jour même."""
    from .plan import OBJECTIFS
    ecarts = [(dt.date.fromisoformat(o["date"]) - date).days for o in OBJECTIFS]
    if any(0 <= x <= 2 for x in ecarts):
        return None
    return 15 if any(3 <= x <= 6 for x in ecarts) else 20


def velo_maison(date: dt.date, apres_dure: bool, avant: Seance | None) -> Entree | None:
    """Vélo d'appartement d'un jour sans course, sans vélo et sans renfo : récupération le lendemain d'une séance dure, facultatif sinon.

    Collé juste avant les étirements s'il y en a (ils commencent par 5 min de vélo)."""
    m = velo_minutes(date)
    if m is None:
        return None
    titre = f"Vélo d'appartement {m} min" + (" (récupération)" if apres_dure else " (facultatif)")
    corps = (f"{m} min souples, FC de {VELO_FC[0]} à {VELO_FC[1]}, cadence 85 à 95 tr/min. "
             + ("Lendemain de séance dure : fait circuler le sang dans les jambes sans ajouter de fatigue." if apres_dure
                else "Jour sans course : du volume d'endurance sans impact, seulement si tu en as envie."))
    prefs = ((hm(minutes(avant.heure) - m),) if avant else ()) + ("16:00", "17:00", "10:00", "15:00")
    return Entree(date.weekday(), "velo_maison", titre, m, corps, prefs=prefs, etapes=(("fc", m * 60, VELO_FC[0], VELO_FC[1]),))


def enchainement(e: Entree, course: Seance | None) -> Entree | None:
    """Renfo collé à la course du jour (même sortie de la maison) : activation C juste avant, renfo B juste après un footing EF du matin.

    Jamais le renfo A (bas du corps lourd, mollets fragiles) ni autour d'une séance au club (Tom n'est pas à la maison)."""
    if not course or "club" in course.titre.lower():
        return None
    if e.titre.startswith("Activation"):
        return dataclasses.replace(e, prefs=(hm(minutes(course.heure) - e.duree),) + tuple(e.prefs),
                                   corps=fiche.ajouter(e.corps, "Juste avant la course : sert de début d'échauffement, garde ensuite le footing progressif et les gammes."))
    if e.titre.startswith("Renfo B") and course.kind == "ef" and course.heure < "12:00":
        return dataclasses.replace(e, prefs=(hm(minutes(course.heure) + course.duree),) + tuple(e.prefs),
                                   corps=fiche.ajouter(e.corps, "Enchaîné juste après le footing : l'échauffement est fait, pas de corde ni de vélo avant."))
    return None


# fenêtres de départ acceptables selon le type de séance (minutes depuis minuit) : jamais en plein milieu de journée
MATIN = (6 * 60 + 30, 10 * 60 + 30)
SOIR = (17 * 60, 19 * 60 + 30)
PLAGES = {"etirements": [(14 * 60 + 30, 19 * 60)], "renfo": [(14 * 60 + 30, 19 * 60)], "activation": [(14 * 60 + 30, 19 * 60)],
          "velo": [(7 * 60, 11 * 60), (15 * 60, 19 * 60)]}


def creneaux(e: Entree) -> list[str]:
    """Préférences d'abord, puis tout créneau de 30 min des fenêtres, du plus proche de la première préférence au plus loin."""
    ref = minutes(e.prefs[0])
    cand = sorted((m for lo, hi in PLAGES.get(e.kind, [MATIN, SOIR]) for m in range(lo, hi + 1, 30)), key=lambda m: abs(m - ref))
    out: list[str] = []
    for h in list(e.prefs) + [f"{m // 60:02d}:{m % 60:02d}" for m in cand]:
        if h not in out:
            out.append(h)
    return out


def placer(e: Entree, date: dt.date, occupe: list[dict], maintenant: dt.datetime,
           gel: dt.timedelta = dt.timedelta(hours=2), force: bool = False) -> tuple[Seance | None, str | None]:
    """Premier créneau libre. Séance du jour passée ou imminente (moins de `gel`) : intouchée, sauf `force` (conflit)."""
    premier = dt.datetime.fromisoformat(f"{date.isoformat()}T{e.prefs[0]}").replace(tzinfo=PARIS)
    if premier < maintenant + gel and not force:
        return None, None
    for h in creneaux(e):
        debut = dt.datetime.fromisoformat(f"{date.isoformat()}T{h}").replace(tzinfo=PARIS)
        if debut < maintenant + (dt.timedelta(minutes=30) if force else gel):
            continue
        if libre(h, e.duree, occupe):
            return Seance(date.isoformat(), h, e.duree, titre_agenda(e), description(e, date.isoformat(), h), e.kind, e.dure, etapes=e.etapes,
                          html=description_html(e, date.isoformat(), h)), None
    return None, f"{e.titre} le {date.isoformat()} : aucun créneau libre"


def voisin_ok(e: Entree, cible: dt.date, occupe: list[dict], dures: set[str], maintenant: dt.datetime) -> Seance | None:
    """Jour voisin acceptable : jamais deux séances dures de suite."""
    if cible < maintenant.date():
        return None
    if e.dure and any((cible + dt.timedelta(days=k)).isoformat() in dures for k in (-1, 0, 1)):
        return None
    s, _ = placer(e, cible, occupe, maintenant)
    return s


def apres_midi(e: Entree) -> Entree:
    """Renfo, activation et étirements l'après-midi (16:00 par défaut, `COACH_RENFO_APRES_MIDI`), jamais tard le soir.

    Les jours de footing au club (retour après 19 h 30) : 15:00, repli le matin. Sur un jour avec séance dure le matin, l'écart dépasse 6 h.
    """
    if e.kind not in ("renfo", "activation", "etirements"):
        return e
    base = os.environ.get("COACH_RENFO_APRES_MIDI", "16:00")
    h, m = map(int, base.split(":"))
    decale = f"{(h * 60 + m + 30) // 60:02d}:{(h * 60 + m + 30) % 60:02d}"
    return dataclasses.replace(e, prefs=(decale if e.kind == "etirements" else base, "17:00", "15:00"))


def club_ef(e: Entree) -> Entree:
    """Footing EF du mardi ou du jeudi : proposé au club ASM à 18:30 (groupe d'allure EF), repli seul le matin à 08:30.

    Désactivable avec COACH_EF_AU_CLUB=0. Tom reste libre : déplacer l'événement le verrouille.
    """
    if os.environ.get("COACH_EF_AU_CLUB", "1") == "0" or e.kind != "ef" or e.jour not in (1, 3) or e.prefs[0] >= "12:00":
        return e
    return dataclasses.replace(
        e, titre=f"{e.titre} au club ASM", prefs=("18:30", "08:30"),
        corps=fiche.ajouter(e.corps, "Au club ASM, groupe de footing EF de 18 h 30 (plusieurs allures : prends celui de 5'15 à 5'35/km). "
                        "Si tu n'y vas pas, fais-le seul : le coach garde un créneau à 08:30, ou déplace l'événement."))


def construire(debut: dt.date, jours: int, maintenant: dt.datetime, deja: set[str] | None = None,
               occ: dict | None = None, etat: dict | None = None, dures_init: set[str] | None = None,
               groupes: dict | None = None, verrouilles: dict | None = None) -> tuple[list[Seance], list[str]]:
    """Séances de la fenêtre [debut, debut + jours[ : placement, puis jour voisin pour celles sans créneau."""
    deja = deja or set()
    fin = debut + dt.timedelta(days=jours)
    occ = occ if occ is not None else occupations_range(debut.isoformat(), (fin + dt.timedelta(days=1)).isoformat())
    etat = etat if etat is not None else charger()
    groupes = groupes if groupes is not None else groupes_range(debut.isoformat(), (fin + dt.timedelta(days=1)).isoformat())
    seances, notes, echecs = [], [], []

    def occ_du_jour(jour: str) -> list[dict]:
        """Événements de l'agenda plus les séances du coach déjà placées ce jour-là (deux séances ne se recouvrent jamais)."""
        deja = [{"debut": minutes(x.heure), "fin": minutes(x.heure) + x.duree, "bloque": False, "titre": x.titre} for x in seances if x.date == jour]
        verrou = [{"debut": minutes(h), "fin": minutes(h) + dur, "bloque": False, "titre": "séance verrouillée"}
                  for (dj, h, dur) in (verrouilles or {}).values() if dj == jour]
        return list(occ.get(jour, [])) + deja + verrou

    for lundi_iso, entrees in SEMAINES.items():
        lundi = dt.date.fromisoformat(lundi_iso)
        # les séances de course d'abord, pour savoir si la journée a une séance le soir avant de placer le renfo
        for e in sorted(entrees, key=lambda x: (x.jour, x.kind not in KINDS_COURSE)):
            if e.kind in ("renfo", "activation", "etirements"):
                e = apres_midi(e)
                jour_iso = (lundi + dt.timedelta(days=e.jour)).isoformat()
                soir = any(x.date == jour_iso and x.kind in KINDS_COURSE and x.heure >= "17:00" for x in seances) or \
                    any(dj == jour_iso and h >= "17:00" for (dj, h, _) in (verrouilles or {}).values())
                if soir:
                    # séance de course le soir (club, piste) : renfo, activation et étirements le matin ; Tom rentre tard
                    e = dataclasses.replace(e, prefs=("08:30", "09:30", "15:00"))
                colle = next((x for x in seances if x.date == jour_iso and x.kind in KINDS_COURSE), None)
                en = enchainement(e, colle)
                if en:
                    e = en
                else:
                    colle = None
                    if e.titre.startswith("Renfo"):
                        e = dataclasses.replace(e, duree=e.duree + VELO_ECHAUFFEMENT)
            else:
                colle = None
            d = lundi + dt.timedelta(days=e.jour)
            if not (debut <= d < fin):
                continue
            if e.kind in ("as21", "seuil") and e.kind in deja:
                notes.append(f"{e.titre} le {d.isoformat()} : déjà réalisée cette semaine, non replanifiée")
                continue
            g = groupes.get(d.isoformat())
            if g and e.kind in KINDS_COURSE and not g.get("velo"):
                notes.append(f"{e.titre} le {d.isoformat()} : remplacée par la séance de groupe « {g['titre']} »")
                continue
            veille_lendemain = [groupes.get((d + dt.timedelta(days=k)).isoformat()) for k in (-1, 1)]
            if e.dure and any(x and x["dure"] for x in veille_lendemain) and e.kind in KINDS_COURSE:
                notes.append(f"{e.titre} le {d.isoformat()} : remplacée par un footing facile (séance de groupe dure la veille ou le lendemain)")
                e = dataclasses.replace(ef(e.jour, 40, prefs=e.prefs), prefs=e.prefs)
            e = club_ef(e)
            if f"{d.isoformat()}|{e.kind}" in (verrouilles or {}):
                continue   # séance verrouillée par Tom : elle est où il l'a mise, elle occupe son créneau, on ne la replanifie pas
            e = progression.appliquer(e, etat.get("bilans", []))
            occupe = occ_du_jour(d.isoformat())
            if colle:
                # enchaînement : pas de battement avec la course concernée (les autres événements gardent le leur)
                occupe = [dict(x, marge=0) if (x["debut"], x["titre"]) == (minutes(colle.heure), colle.titre) else x for x in occupe]
            s, raison = placer(e, d, occupe, maintenant)
            if s is None and raison is None:
                # séance du jour imminente : intouchée, sauf si un événement ajouté la recouvre maintenant
                rec = next((r for r in etat["evenements"].values() if r["cle"] == f"{d.isoformat()}|{e.kind}"), None)
                if rec and not libre(rec["heure"], e.duree, [x for x in occupe if x["titre"] != rec["titre"]]):
                    s, raison = placer(e, d, occupe, maintenant, force=True)
            if s:
                seances.append(s)
            elif raison and d >= maintenant.date():
                echecs.append((e, d, raison))
    dures = {s.date for s in seances if s.dure} | (dures_init or set()) | {k for k, v in groupes.items() if v["dure"]}
    for e, d, raison in echecs:
        for k in (1, -1):
            cible = d + dt.timedelta(days=k)
            s = voisin_ok(e, cible, occ_du_jour(cible.isoformat()), dures, maintenant)
            if s and not any(x.cle == s.cle for x in seances):
                s.origine_cle = f"{d.isoformat()}|{e.kind}"
                seances.append(s)
                if e.dure:
                    dures.add(s.date)
                notes.append(f"{e.titre} déplacée du {d.isoformat()} au {cible.isoformat()} (agenda chargé)")
                break
        else:
            notes.append(raison)
    # vélo d'appartement : les jours sans course, sans vélo et sans renfo (ce dernier commence déjà par 15 min de vélo)
    charges_ailleurs = {s.origine_cle.split("|")[0] for s in seances if s.origine_cle} | {d for n in notes for d in re.findall(r"le (\d{4}-\d{2}-\d{2}) : aucun créneau", n)}
    for i in range(jours):
        d = debut + dt.timedelta(days=i)
        jour = d.isoformat()
        du_jour = [s for s in seances if s.date == jour]
        if any(s.kind in KINDS_COURSE + ("velo", "renfo", "activation", "velo_maison") for s in du_jour) or f"{jour}|velo_maison" in (verrouilles or {}) \
                or any(dj == jour for (dj, _, _) in (verrouilles or {}).values()) or jour in groupes \
                or any(x["debut"] is None and x["bloque"] for x in occ.get(jour, [])) or jour in charges_ailleurs:
            continue   # journée chargée (engagement, séance déplacée faute de place) : rien en plus
        etir = next((s for s in du_jour if s.kind == "etirements"), None)
        e = velo_maison(d, (d - dt.timedelta(days=1)).isoformat() in dures, etir)
        if not e:
            continue
        occupe = occ_du_jour(jour)
        if etir:
            occupe = [dict(x, marge=0) if (x["debut"], x["titre"]) == (minutes(etir.heure), etir.titre) else x for x in occupe]
        s, _ = placer(e, d, occupe, maintenant)
        if s:
            seances.append(s)
    return seances, notes


# --- état et synchronisation avec Baïkal -------------------------------------------------

def charger() -> dict:
    return json.loads(STATE.read_text()) if STATE.exists() else {"evenements": {}, "journal": []}


def sauver(etat: dict) -> None:
    from .config import ecrire_json
    ecrire_json(STATE, etat)


def journaliser(etat: dict, action: str, detail: str) -> None:
    etat["journal"] = (etat.get("journal", []) + [{"ts": dt.datetime.now(PARIS).isoformat(timespec="minutes"), "action": action, "detail": detail}])[-60:]


def synchroniser(seances: list[Seance], debut: dt.date, fin: dt.date, apply: bool) -> list[str]:
    """Crée, met à jour ou retire les événements du coach. Renvoie le compte rendu (une ligne par décision).

    L'état est enregistré même si Baïkal échoue en cours de route : sinon les événements déjà créés seraient recréés en double."""
    etat = charger()
    try:
        return _synchroniser(etat, seances, debut, fin, apply)
    finally:
        if apply:
            sauver(etat)


def _synchroniser(etat: dict, seances: list[Seance], debut: dt.date, fin: dt.date, apply: bool) -> list[str]:
    actuels = {}
    for l in baikal.lister(debut.isoformat(), fin.isoformat()):
        p = baikal.parse(l)
        if p and p["id"]:
            actuels[p["id"]] = p
    compte = []
    voulues = {s.cle for s in seances}
    for s in seances:
        ident, rec = next(((i, r) for i, r in etat["evenements"].items() if r["cle"] == s.cle), (None, None))
        if not rec and s.origine_cle:  # séance déplacée à un autre jour : on déplace le même événement
            ident, rec = next(((i, r) for i, r in etat["evenements"].items() if r["cle"] == s.origine_cle), (None, None))
            if rec:
                rec = {**rec, "empreinte": "deplacement"}
        if rec:
            p = actuels.get(ident)
            if p is None:
                compte.append(f"{s.cle} : supprimée par Tom, non recréée")
                continue
            modifie = (p["date"], p["heure"], p["titre"]) != (rec["date"], rec["heure"], rec["titre"]) or "[fixe]" in p["titre"].lower()
            if modifie:
                compte.append(f"{s.cle} : modifiée par Tom, verrouillée")
                continue
            if rec["empreinte"] == "allege":
                compte.append(f"{s.cle} : allégée par le coach, conservée")
                continue
            if rec["empreinte"] == s.empreinte:
                continue
            if (rec["date"], rec["heure"], rec["titre"]) == (s.date, s.heure, s.titre):   # contenu seul : on actualise sans prévenir
                compte.append(f"{s.cle} : description actualisée")
            else:
                compte.append(f"{s.cle} : mise à jour ({rec['heure']} -> {s.heure}, {s.titre})")
            if apply:
                baikal.modifier(ident, titre=s.titre, debut=f"{s.date}T{s.heure}", fin=s.fin, description=s.description, html=s.html)
                etat["evenements"][ident] = {"cle": s.cle, "date": s.date, "heure": s.heure, "titre": s.titre, "empreinte": s.empreinte,
                                             "etapes": json.loads(json.dumps(s.etapes, default=list))}
                journaliser(etat, "maj", f"{s.cle} {s.titre} {rec['heure']}->{s.heure}")
        else:
            compte.append(f"{s.cle} : créée à {s.heure} ({s.titre})")
            if apply:
                ident = baikal.creer(s.titre, f"{s.date}T{s.heure}", s.fin, s.description, cal="Sport", categorie=CATEGORIE, html=s.html)
                etat["evenements"][ident] = {"cle": s.cle, "date": s.date, "heure": s.heure, "titre": s.titre, "empreinte": s.empreinte,
                                             "etapes": json.loads(json.dumps(s.etapes, default=list))}
                journaliser(etat, "creation", f"{s.cle} {s.titre} {s.heure}")
    # séances du coach qui ne sont plus voulues (agenda changé, séance déjà faite) : retirées si Tom n'y a pas touché
    for ident, rec in list(etat["evenements"].items()):
        # jamais le jour même : une séance imminente n'est plus dans `seances` sans être pour autant « hors plan »
        # fenêtre [debut, fin[ : le dernier jour n'est pas construit, donc pas retirable
        if max(debut.isoformat(), (dt.datetime.now(PARIS).date() + dt.timedelta(days=1)).isoformat()) <= rec["date"] < fin.isoformat() \
                and rec["cle"] not in voulues:
            p = actuels.get(ident)
            if p and (p["date"], p["heure"], p["titre"]) == (rec["date"], rec["heure"], rec["titre"]) and "[fixe]" not in p["titre"].lower():
                compte.append(f"{rec['cle']} : retirée (plus au plan)")
                if apply:
                    baikal.supprimer(ident)
                    del etat["evenements"][ident]
                    journaliser(etat, "retrait", f"{rec['cle']} {rec['titre']}")
    return compte


def _verrouilles(debut: dt.date, jours: int) -> dict[str, tuple[str, str, int]]:
    """Séances du coach que Tom a modifiées (titre, horaire) ou verrouillées avec [fixe] : clé -> (jour réel, heure réelle, durée)."""
    etat = charger()
    out = {}
    for l in baikal.lister(debut.isoformat(), (debut + dt.timedelta(days=jours + 1)).isoformat(), cal="Sport", fins=True):
        p = baikal.parse(l)
        rec = etat.get("evenements", {}).get(p["id"]) if p and p["id"] else None
        if not rec or p["heure"] == "journée":
            continue
        if (p["date"], p["heure"], p["titre"]) != (rec["date"], rec["heure"], rec["titre"]) or "[fixe]" in p["titre"].lower():
            duree = (minutes(p["fin"]) - minutes(p["heure"])) if p["fin"] else 60
            out[rec["cle"]] = (p["date"], p["heure"], duree)
    return out


def dures_recentes(debut: dt.date) -> set[str]:
    """Jour d'une séance dure faite la veille ou prévue dans l'agenda juste avant la fenêtre : on ne colle pas une autre séance dure."""
    veille = (debut - dt.timedelta(days=1)).isoformat()
    try:
        return {veille} if any(k in l.lower() for l in baikal.lister(veille) for k in ("seuil", "as21", "vma", "longue", "côtes")) else set()
    except Exception:
        return set()


def planifier(conf: dict | None = None, jours: int = 14, apply: bool = False, maintenant: dt.datetime | None = None,
              deja: set[str] | None = None, dures_init: set[str] | None = None) -> tuple[list[str], list[str]]:
    maintenant = maintenant or dt.datetime.now(PARIS)
    debut = maintenant.date()
    seances, notes = construire(debut, jours, maintenant, deja, dures_init=dures_init if dures_init is not None else dures_recentes(debut),
                                verrouilles=_verrouilles(debut, jours))
    compte = synchroniser(seances, debut, debut + dt.timedelta(days=jours), apply)
    if apply:
        compte += _garmin(compte, maintenant)
    return compte, notes


def _garmin(compte: list[str], maintenant: dt.datetime) -> list[str]:
    """Séances de renfo sur la montre : seulement si l'agenda a bougé ou une fois par jour (limite les connexions Garmin)."""
    from . import garmin, garmin_renfo
    etat = charger()
    aujourdhui = maintenant.date().isoformat()
    if not compte and etat.get("garmin_derniere") == aujourdhui:
        return []
    try:
        lignes = garmin_renfo.synchroniser(garmin.client(), etat, aujourdhui)
        etat["garmin_derniere"] = aujourdhui
        journaliser(etat, "garmin", "; ".join(lignes) or "à jour") if lignes else None
        sauver(etat)
        return lignes
    except Exception as e:  # la montre est un plus : une panne Garmin ne bloque ni l'agenda ni les briefings
        print(f"[GARMIN renfo] échec : {e}", flush=True)
        return []


def reels_dur_semaine(acts: list[dict], lundi: dt.date) -> set[str]:
    """Types de séance dure déjà réalisés depuis lundi, d'après les noms et descriptions des courses Strava."""
    fait = set()
    for a in acts:
        if a["start_date_local"][:10] < lundi.isoformat() or a.get("sport_type", a.get("type")) not in ("Run", "TrailRun"):
            continue
        txt = f"{a.get('name', '')} {a.get('description') or ''}".lower()
        if "as21" in txt:
            fait.add("as21")
        elif "seuil" in txt:
            fait.add("seuil")
    return fait


def ajuster_jour(forme: dict, maintenant: dt.datetime, apply: bool = True) -> list[str]:
    """Allège la séance dure du jour si la forme est mauvaise. Ne touche qu'à un événement du coach, intact, à plus de 2 h."""
    if forme.get("sleep_hours") is None and forme.get("hrv_status") is None:
        return []  # forme inconnue : on n'invente rien
    if not decision.fatigue(forme.get("sleep_hours"), forme.get("hrv_status"), forme):
        return []
    raisons = decision.signaux(forme)
    etat = charger()
    aujourdhui = maintenant.date().isoformat()
    notes = []
    for l in baikal.lister(aujourdhui):
        p = baikal.parse(l)
        rec = etat["evenements"].get(p["id"]) if p and p["id"] else None
        if not rec or rec["date"] != aujourdhui or (p["date"], p["heure"], p["titre"]) != (rec["date"], rec["heure"], rec["titre"]):
            continue
        if "[fixe]" in p["titre"].lower() or not any(k in rec["cle"] for k in ("seuil", "as21", "longue", "cotes")):
            continue
        if dt.datetime.fromisoformat(f"{aujourdhui}T{p['heure']}").replace(tzinfo=PARIS) < maintenant + dt.timedelta(hours=2):
            continue
        minutes_ef = 60 if "longue" in rec["cle"] else 40
        titre = f"CAP: Footing EF {minutes_ef} min (séance allégée)"
        sections = [("Séance", [f"{minutes_ef} min en aisance respiratoire", "Endurance fondamentale : 5'15 à 5'35/km, FC sous 145 bpm"]),
                    ("Pourquoi", ["Séance remplacée par le coach : récupération insuffisante (sommeil ou variabilité cardiaque)",
                                  "La séance prévue n'est pas rattrapée"] + raisons)]
        desc = fiche.texte(f"Footing EF {minutes_ef} min (séance allégée)", sections, MARQUE)
        desc_html = fiche.en_html(f"Footing EF {minutes_ef} min (séance allégée)", sections, MARQUE)
        notes.append(f"Séance allégée : {rec['titre']} remplacée par un footing EF de {minutes_ef} min (récupération insuffisante"
                     + (f" : {', '.join(raisons)}" if len(raisons) >= 2 else "") + ")")
        if apply:
            baikal.modifier(p["id"], titre=titre, description=desc, html=desc_html)
            etat["evenements"][p["id"]] = {**rec, "titre": titre, "empreinte": "allege", "etapes": [["e", minutes_ef * 60, 315, 335]]}
            journaliser(etat, "allegement", f"{rec['cle']} {rec['titre']} -> {titre}")
            sauver(etat)   # tout de suite : un échec de Baïkal sur l'événement suivant ne doit pas effacer celui-ci
    if apply and notes:
        _garmin(["allègement"], maintenant)   # la montre doit afficher le footing, pas la séance dure
    return notes


def annuler(apply: bool = False) -> list[str]:
    """Retire tous les événements futurs créés par le coach et encore intacts (retour arrière)."""
    etat = charger()
    aujourdhui = dt.datetime.now(PARIS).date().isoformat()
    actuels = {}
    for l in baikal.lister(aujourdhui, "2027-12-31"):
        p = baikal.parse(l)
        if p and p["id"]:
            actuels[p["id"]] = p
    compte = []
    for ident, rec in list(etat["evenements"].items()):
        p = actuels.get(ident)
        if rec["date"] >= aujourdhui and p and (p["date"], p["heure"], p["titre"]) == (rec["date"], rec["heure"], rec["titre"]):
            compte.append(f"{rec['cle']} : supprimée ({rec['titre']})")
            if apply:
                baikal.supprimer(ident)
                del etat["evenements"][ident]
                sauver(etat)
    if apply:
        journaliser(etat, "annulation", f"{len(compte)} événement(s)")
        sauver(etat)
    return compte


def resume_changements(compte: list[str], notes: list[str], ajustements: list[str]) -> list[str]:
    """Lignes à montrer à Tom : ce qui a bougé et ce qui n'a pas pu être placé."""
    return ([l for l in compte if re.search(r" : (créée à|mise à jour|retirée)", l)][:6] + ajustements
            + [f"A voir : {n}" for n in notes][:4])


def reagir(conf: dict | None = None, maintenant: dt.datetime | None = None) -> int:
    """Passage périodique (cron, 15 min) : rejoue le placement et prévient Tom seulement de ce qui bouge ou bloque.

    Un ajout de dernière minute dans l'agenda déplace la séance concernée, même moins de 2 h avant le départ.
    Chaque problème n'est annoncé qu'une fois tant qu'il dure.
    """
    from . import ntfy
    from .config import load_config
    from . import texte
    conf = load_config() if conf is None else conf
    maintenant = maintenant or dt.datetime.now(PARIS)
    compte, notes = planifier(conf, 10, True, maintenant)
    try:   # capteurs Home Assistant du coach (prochaine séance, jours avant l'objectif...)
        from . import ha
        ha.pousser(conf, maintenant)
    except Exception as e:
        print(f"[HA] échec : {e}", flush=True)
    deplacements = [l for l in compte if "mise à jour" in l or "retirée" in l]
    etat = charger()
    deja = set(etat.get("notifie", []))
    nouvelles = [n for n in notes if n not in deja and "déjà réalisée" not in n]
    etat["notifie"] = [n for n in notes if "déjà réalisée" not in n]
    sauver(etat)
    if not (deplacements or nouvelles):
        return 0
    imminent = any(l.split("|")[0] == maintenant.date().isoformat() for l in deplacements)
    ntfy.envoyer(conf, "Coach : plan modifié",
              texte.message(texte.bloc("Plan", deplacements + [f"A voir : {n}" for n in nouvelles], puces=True),
                            texte.bloc("Pourquoi", "Un événement de ton agenda recouvre une séance ou a changé. Ajoute [fixe] au titre d'une séance pour la verrouiller.")),
              priority="high" if imminent else "default")
    return 0


def cible_du_jour(etat: dict, date: str, famille: str) -> int | None:
    """Allure cible (s/km) de la séance du coach ce jour-là, lue dans ses étapes ; None si le coach n'en avait pas prévu."""
    for rec in etat.get("evenements", {}).values():
        if rec["date"] == date and rec["cle"].endswith("|" + famille) and rec.get("etapes"):
            def cherche(es):
                for e in es:
                    if e[0] in ("id", "it"):
                        return e[2]
                    if e[0] == "rep":
                        r = cherche(e[2])
                        if r:
                            return r
            return cherche(rec["etapes"])
    return None


def enregistrer_bilan(date: str, famille: str, cible: int, ecart: float, fc: float | None) -> None:
    """Bilan d'une séance de qualité (écart moyen des blocs à la cible, négatif = plus rapide) pour la progression."""
    etat = charger()
    b = etat.setdefault("bilans", [])
    if not any(x["date"] == date and x["famille"] == famille for x in b):
        b.append({"date": date, "famille": famille, "cible": cible, "ecart": round(ecart, 1), "fc": fc})
        etat["bilans"] = b[-20:]
        sauver(etat)


def compatible_club(titre: str) -> str | None:
    """Une séance du plan peut-elle se faire au club ASM ? Le club propose à chaque séance du footing et du fractionné, à plusieurs allures
    et avec des programmes différents selon la préparation : on choisit le groupe qui correspond à l'allure du plan."""
    t = titre.lower()
    if any(k in t for k in ("côtes", "trail", "pic du rey", "rando", "vélo", "renfo", "activation", "étirement", "simulation")):
        return None
    m = re.search(r"(\d+'\d{2})/km", titre)
    if any(k in t for k in ("seuil", "rappel d'allure", "allure semi", "as21")):
        allure = f" à {m[1]}/km" if m else ""
        return f"fractionné au club : choisis le groupe dont le programme prépare un semi ou un 10 km, allure{allure}"
    if "footing" in t or "décrassage" in t:
        return "footing au club : choisis le groupe d'allure EF (5'15 à 5'35/km)"
    return None


def enregistrer_club(date: str, dure: bool) -> None:
    """Séance du club reconnue par la localisation (déjà faite) : la séance dure du lendemain sera allégée."""
    etat = charger()
    club = etat.setdefault("club", {})
    if date not in club:
        club[date] = {"dure": dure}
        etat["club"] = dict(sorted(club.items())[-20:])
        sauver(etat)


def enregistrer_charge(ch: dict) -> None:
    """Dernière charge calculée au briefing du matin : les capteurs Home Assistant la relisent sans appeler Garmin."""
    etat = charger()
    etat["charge"] = ch
    sauver(etat)


def entree_du_plan(date: str, titre: str | None) -> Entree | None:
    """Séance du plan qui correspond à un titre d'agenda ce jour-là (club, progression et vélo compris), None sinon."""
    if not titre:
        return None
    jour = dt.date.fromisoformat(date)
    lundi = (jour - dt.timedelta(days=jour.weekday())).isoformat()
    for e in SEMAINES.get(lundi, []):
        if e.jour == jour.weekday():
            for x in (e, club_ef(e)):
                if titre_agenda(x) == titre or x.titre == titre:
                    return x
    return None


def seances_du_jour(date: str, evenements: list[dict | None]) -> list[str]:
    """Événements du jour lisibles ; ceux du coach avec objectif, corps de séance et chaussures du plan (`coach.py next`)."""
    etat = charger()
    jour = dt.date.fromisoformat(date)
    lundi = (jour - dt.timedelta(days=jour.weekday())).isoformat()
    plan = {e.kind: e for e in SEMAINES.get(lundi, []) if e.jour == jour.weekday()}
    out = []
    for p in evenements:
        if not p:
            continue
        ligne = f"{p['heure']} {p['titre']}" + (f" ({p['lieu']})" if p.get("lieu") else "")
        rec = etat.get("evenements", {}).get(p["id"] or "")
        e = plan.get(rec["cle"].split("|")[1]) if rec else None
        if e and rec.get("empreinte") != "allege":
            ligne += f"\n    {e.corps}" + (f"\n    Chaussures : {e.chaussures}" if e.kind in KINDS_COURSE else "")
        elif rec and rec.get("empreinte") == "allege":
            ligne += "\n    Séance allégée par le coach (récupération insuffisante) : footing en aisance respiratoire."
        out.append(ligne)
    return out


def memoriser(cle: str, valeur) -> None:
    """Valeur relevée au briefing du matin (seuil Garmin...) : relue ensuite sans appel Garmin (débrief Strava, Home Assistant)."""
    etat = charger()
    etat[cle] = valeur
    sauver(etat)


def enregistrer_fc_repos(date: str, fc: int | None) -> dict[str, int]:
    """Historique de la FC au repos (60 jours) pour repérer une hausse qui dure ; renvoie l'historique."""
    etat = charger()
    h = etat.setdefault("fc_repos", {})
    if fc:
        h[date] = int(fc)
        etat["fc_repos"] = dict(sorted(h.items())[-60:])
        sauver(etat)
    return etat["fc_repos"]
