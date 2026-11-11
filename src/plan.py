"""Le plan en données : objectifs, semaines jusqu'au semi, circuits de renforcement.

Les dates du fichier docs/PLAN_ENTRAINEMENT_LOURDES_TARBES.md sont décalées d'un jour (le « samedi 15/11 » est un dimanche) :
les sorties longues sont placées le samedi (14/11 et 21/11), 8 jours avant la course pour la dernière.
Après le semi : semaine de récupération, bloc La Rhune (7/12 au 22/01, docs/RHUNE_24H.md), puis bloc 10 km (25/01 au 25/04, docs/PLAN_10KM.md).
"""
from dataclasses import dataclass
from .profil import charger_profil

_p = charger_profil()
OBJECTIFS = _p.objectifs

# Chaussures (noms retrouvés sur Strava par le coach, voir strava_enrich.paire_strava) :
SEUIL_BAS = _p.chaussures.get("seuil_bas", "Adidas Evo SL (paire 2)")
EF_PAIRE = _p.chaussures.get("ef_paire", "Adidas Adizero Evo SL")
CARBONE = _p.chaussures.get("carbone", "ASICS Metaspeed Sky Paris")


@dataclass
class Entree:
    jour: int          # 0 = lundi
    kind: str          # ef | seuil | as21 | longue | velo | renfo | activation | course
    titre: str
    duree: int         # minutes, échauffement et retour au calme compris
    corps: str = ""
    chaussures: str = SEUIL_BAS
    prefs: tuple = ("08:30", "18:30")
    dure: bool = False
    etapes: tuple = ()           # séance structurée pour la montre (voir garmin_course.py)
    famille: str | None = None   # "seuil" | "as21" : famille suivie par la progression
    allure_base: int | None = None  # allure cible de la famille, en s/km


# Étapes d'une séance de course pour la montre. Allures en secondes par km, durées en secondes, distances en mètres.
def W(minutes): return ("w", minutes * 60)                       # échauffement
def C(minutes): return ("c", minutes * 60)                       # retour au calme
def E(minutes, lo=315, hi=335): return ("e", minutes * 60, lo, hi)   # footing facile avec fourchette d'allure
def ID(metres, allure, tol=3): return ("id", metres, allure, tol)    # effort à la distance
def IT(secondes, allure, tol=3): return ("it", secondes, allure, tol)  # effort au temps
def R(secondes): return ("r", secondes)                          # récupération en trot
def REP(n, *steps): return ("rep", n, list(steps))               # répétitions


def lignes_droites(n): return (REP(n, ID(80, 240, 10), R(40)),) if n else ()


CIRCUITS = {
    "A1": ("Renfo A1, bas du corps", 35, "Squat gobelet ou barre 3x8, soulevé de terre roumain 3x8, fentes marchées lestées 3x12 pas, "
           "montées de banc unilatérales 3x10, mollets : unilatéraux lestés (haltère) genou tendu 3x10 puis assis genou fléchi 3x12 (soléaire, tempo 3 s en montée, 1 s en haut, 3 s en descente), "
           "gainage latéral 2x30 s par côté."),
    "A2": ("Renfo A2, bas du corps allégé", 30, "Charge réduite d'un tiers, 2 séries : soulevé de terre unilatéral 2x8, fentes arrière 2x10, "
           "pont fessier lesté 2x12, mollets lestés genou tendu 2x10 et assis 2x12 (tempo lent), planche 2x45 s. Dernière charge lourde avant la course."),
    "A3": ("Renfo A3, bas du corps et descente", 35, "Prépare les 6 700 m de descente. Squat gobelet descente lente de 4 s 3x8, montées de banc "
           "avec descente contrôlée de 3 s 3x8 par jambe, fentes arrière 3x8 par jambe, mollets unilatéraux lestés descente de 4 s 3x12 puis assis 3x12, "
           "chaise isométrique 3x45 s. Toujours après l'échauffement, charge modérée, jamais à fond la semaine d'une grosse sortie."),
    "B1": ("Renfo B1, haut du corps et gainage", 25, "Développé couché haltères 3x8, tirage élastique ou tractions 3x8, ab-wheel 3x8-10, "
           "planche 3x40 s, pompes tempo 2x10."),
    "B2": ("Renfo B2, haut du corps et gainage", 25, "Développé incliné haltères 3x8, rowing haltère unilatéral 3x10, dead bug 3x10, "
           "ab-wheel 3x8, planche latérale 2x30 s par côté."),
    "B3": ("Renfo B3, haut du corps pour les bâtons", 25, "Les bâtons travaillent les épaules, les triceps et le dos pendant 24 h. Développé épaules haltères 3x8, "
           "rowing haltère 3x10, extension triceps 3x10, tirage de face à l'élastique 3x12, marche du fermier 3x40 s, planche latérale 2x30 s par côté."),
    "C1": ("Activation C1", 15, "Corde à sauter 3x2 min, mollets en isométrie 3x30 s, pont fessier unilatéral 2x12, ab-wheel 2x8."),
    "C2": ("Activation C2", 15, "Gammes (talons-fesses, montées de genoux) 3x20 m, renforcement du pied (pied court) 2x10, mollets unilatéraux lents 2x15, "
           "planche latérale 2x30 s, mobilité de hanches 5 min."),
    "D1": ("Étirements D1, chaîne postérieure", 20,
           "Échauffement 5 min (marche ou vélo d'appartement sans résistance). Mollets, genou tendu puis genou fléchi, 2x45 s par côté. "
           "Ischio-jambiers allongé avec sangle 2x45 s par côté. Fessiers et piriforme (figure 4) 2x45 s par côté. "
           "Voûte plantaire sur le rouleau 2 min par pied. Bas du dos, genoux à la poitrine, 1 min."),
    "D2": ("Étirements D2, hanches et avant de cuisse", 20,
           "Échauffement 5 min (marche ou vélo d'appartement sans résistance). Psoas en fente basse 2x45 s par côté. "
           "Quadriceps debout 2x45 s par côté. Adducteurs en papillon 2x45 s (prévention des pubalgies). "
           "Bandelette ilio-tibiale au rouleau 1 min par côté. Ouverture thoracique 1 min, respiration lente 2 min."),
    "D3": ("Étirements doux de récupération", 15,
           "Marche 10 min ou vélo très léger. Étirements passifs, jamais à fond : mollets 1x30 s par côté (antécédents de déchirure), "
           "ischio-jambiers, fessiers et psoas 1x30 s par côté. Rouleau très léger sur les cuisses, respiration lente 2 min."),
}


def etirements(jour: int, code: str, prefs=("19:30", "19:00")) -> Entree:
    titre, duree, corps = CIRCUITS[code]
    return Entree(jour, "etirements", titre, duree, corps, prefs=prefs)


def renfo(jour: int, code: str, prefs=("19:00", "18:00")) -> Entree:
    titre, duree, corps = CIRCUITS[code]
    return Entree(jour, "renfo", titre, duree, corps, prefs=prefs)


def ef(jour: int, minutes: int, ld: int = 0, prefs=("08:30", "18:30")) -> Entree:
    corps = f"{minutes} min en aisance respiratoire" + (f", puis {ld} lignes droites progressives de 80 m" if ld else "")
    return Entree(jour, "ef", f"Footing EF {minutes} min", minutes + 5, corps, chaussures=EF_PAIRE, prefs=prefs,
                  etapes=(E(minutes),) + lignes_droites(ld))


# Semaines indexées par leur lundi. Mobilité de 10 min le soir : ligne de chaque description, pas un événement.
SEMAINES: dict[str, list[Entree]] = {
    # Semaine du pic de charge. L'allure semi (AS21) a déjà été faite le lundi 9 : elle n'est pas replanifiée.
    "2026-11-09": [
        ef(1, 40),
        renfo(1, "B1"),
        ef(2, 35),   # mercredi : footing facile (la séance de lundi a coûté une charge de 254 et 70 h de récupération annoncées par Garmin)
        renfo(2, "A2"),
        Entree(3, "seuil", "Seuil 3x3000m à 4'20/km", 80,
               "Décalé du mercredi au jeudi : 72 h après la séance de lundi. Échauffement 20 min (5 min de mobilité, 15 min progressifs 5'45 à 5'15, gammes, 3 lignes droites). "
               "Corps : 3x3000m à 4'20/km, récupération 2'30 en trot. Retour au calme 10 min. Au club ASM (fractionné du groupe prépare un semi ou un 10 km) ou seul.",
               prefs=("18:30", "17:30"), dure=True, etapes=(W(20), REP(3, ID(3000, 260), R(150)), C(10)), famille="seuil", allure_base=260),
        etirements(4, "D1"),
        Entree(5, "longue", "Sortie longue 1h30 vallonnée", 100,
               "Pic de charge, dernière sortie très longue. Départ à 5'25/km, 20 minutes à 4'30/km au milieu, retour souple. "
               "Eau et 1 gel à mi-parcours.", chaussures=EF_PAIRE, prefs=("09:00", "16:00"), dure=True,
               etapes=(E(20, 325, 345), IT(1200, 270, 4), E(50, 320, 340))),
        Entree(6, "velo", "Vélo route souple 1h", 60, "Cadence 90 rpm, zone 2, sans forcer. Home trainer s'il pleut.", prefs=("10:00", "15:00")),
        renfo(6, "C1", prefs=("18:00", "17:00")),
    ],
    # Affûtage : volume réduit, intensité maintenue courte.
    "2026-11-16": [
        ef(0, 45, ld=5),
        Entree(1, "seuil", "Seuil court 5x1000m à 4'10/km", 65,
               "Échauffement 20 min, 5x1000m à 4'10/km, récupération 1'30 en trot, retour au calme 10 min.", dure=True,
               etapes=(W(20), REP(5, ID(1000, 250), R(90)), C(10)), famille="seuil", allure_base=250),
        renfo(1, "A2"),
        Entree(2, "velo", "Vélo souple 40 min", 40, "Décharge articulaire, sans résistance, après la journée Hunger games.", prefs=("18:30", "19:00")),
        ef(3, 30, prefs=("18:30", "19:15")),
        etirements(4, "D2"),
        Entree(5, "as21", "Sortie 1h05 avec 2x8' à allure semi", 70,
               "Échauffement 20 min, 2x8 min à 4'25/km (récupération 3 min de trot), retour au calme 10 min. "
               "Essai des chaussures de course et du ravitaillement du jour J.", chaussures=CARBONE, prefs=("09:00", "16:00"), dure=True,
               etapes=(W(20), REP(2, IT(480, 265), R(180)), C(23)), famille="as21", allure_base=265),
        Entree(6, "velo", "Vélo ou footing très souple 45 min", 45, "Récupération, rien de nouveau.", prefs=("10:00", "15:00")),
        renfo(6, "C2", prefs=("18:00", "17:00")),
    ],
    # Semaine de la course. Pas de renfo lourd, rien de nouveau.
    "2026-11-23": [
        ef(0, 35, ld=4),
        Entree(1, "as21", "Rappel d'allure 3x1000m à 4'25/km", 50,
               "Échauffement 20 min, 3x1000m à 4'25/km, récupération 2 min, retour au calme 10 min. Séance courte, tu dois finir frais.",
               chaussures=CARBONE, dure=True,
               etapes=(W(20), REP(3, ID(1000, 265), R(120)), C(10)), famille="as21", allure_base=265),
        renfo(1, "C2", prefs=("18:30", "18:00")),
        Entree(2, "velo", "Vélo très souple 30 min ou repos", 30, "Facultatif.", prefs=("18:30", "10:00")),
        ef(3, 25, ld=4),
        etirements(4, "D3"),
        Entree(5, "ef", "Décrassage de la veille 15 min", 20,
               "15 min très souples + 4 lignes droites. Prépare dossard, chaussures, gels, tenue. Repas riche en glucides le soir.",
               chaussures=EF_PAIRE, prefs=("10:00", "17:00"),
               etapes=(E(15, 330, 360),) + lignes_droites(4)),
    ],
    # Récupération après le semi : volume bas, aucune qualité.
    "2026-11-30": [
        etirements(0, "D3"),
        ef(1, 30), ef(3, 35),
        Entree(2, "velo", "Vélo ou natation souple 40 min", 40, "Récupération active, sans impact.", prefs=("10:00", "15:00")),
        renfo(4, "C1", prefs=("18:00", "17:00")),
        ef(5, 45, prefs=("09:30", "16:00")),
        etirements(6, "D2"),
    ],
}


# --- Bloc 24h de La Rhune (23/01/2027) -------------------------------------------------------------------------------
# Boucle 9,78 km, 845 m de D+ et 838 m de D-, une boucle toutes les 3 h (8 boucles, environ 78 km et 6 760 m de D+).
# Le D- cumulé (6 700 m) est la contrainte principale : descente, excentrique et sorties enchaînées.
SCOTT = _p.chaussures.get("scott", "Scott Kinabalu Trail")               # trail long et tranquille, simulations des 24 h
NNORMAL = _p.chaussures.get("nnormal", "NNormal Kjerag")                   # terrain technique et pentu, côtes, trail rapide


def T(minutes): return ("t", minutes * 60)


def cotes(jour: int, n: int, secondes: int, recup: int, corps: str, prefs=("08:30", "18:30")) -> Entree:
    effort = f"{secondes} s" if secondes < 120 else f"{secondes // 60} min"
    return Entree(jour, "cotes", f"Côtes {n}x{effort}", 20 + 10 + n * (secondes + recup) // 60, corps, chaussures=NNORMAL, prefs=prefs,
                  dure=True, etapes=(W(20), REP(n, T(secondes / 60), R(recup)), C(10)))


def trail(jour: int, minutes: int, dplus: int, corps: str, prefs=("09:00", "14:00"), dure: bool = True) -> Entree:
    h, m = divmod(minutes, 60)
    return Entree(jour, "longue", f"Trail {h}h{m:02d} avec {dplus} m de D+", minutes + 10,
                  corps + f" Objectif : {dplus} m de D+. Montées en marche active si la pente dépasse 12 %, descentes relâchées, "
                  "pas courts. Mange et bois toutes les 30 min : c'est l'entraînement du ravitaillement des 24 h. "
                  "Les bâtons sont autorisés à La Rhune : teste-les dès que la pente dépasse 12 %.",
                  chaussures=SCOTT, prefs=prefs, dure=dure, etapes=(W(15), T(minutes - 15)))


def rey(jour: int, minutes: int, corps: str, titre: str, prefs=("08:30", "09:30")) -> Entree:
    """Séance au Pic du Rey (Béarn, 1 h de route de Pau) : montée au profil proche de La Rhune."""
    return Entree(jour, "longue", titre, minutes + 10, corps + " Note le dénivelé et le temps réels de la montée pour caler la suite. "
                  "Bâtons autorisés à La Rhune : à tester ici. Mange et bois toutes les 30 min.",
                  chaussures=SCOTT, prefs=prefs, dure=True, etapes=(W(15), T(minutes - 15)))


SEMAINES.update({
    # Reprise après le semi : le corps réapprend le terrain. Pas d'intensité, un peu de côtes, le renfo reprend léger.
    "2026-12-07": [
        ef(1, 40), renfo(1, "B1"),
        cotes(2, 6, 45, 90, "Côtes courtes, effort à 8 sur 10, descente en trot. Sert à réveiller les jambes sans fatiguer."),
        renfo(2, "A2"),
        ef(3, 35),
        etirements(4, "D1"),
        trail(5, 75, 400, "Sortie de reprise, allure facile."),
        Entree(6, "velo", "Vélo souple 1h", 60, "Cadence 90 rpm, zone 2.", prefs=("10:00", "15:00")),
        renfo(6, "C1", prefs=("18:00", "17:00")),
    ],
    # Montée en D+ et premières séances d'excentrique pour les descentes.
    "2026-12-14": [
        ef(0, 40, ld=4),
        cotes(1, 8, 45, 90, "Côtes courtes, effort à 8 sur 10."), renfo(1, "A3"),
        ef(2, 45), renfo(2, "B3"),
        cotes(3, 5, 240, 180, "Côtes longues : 5 montées de 4 min à effort soutenu (7 sur 10), redescente en trot facile. "
              "C'est la séance qui ressemble le plus à la montée de La Rhune (environ 55 à 65 min en marche active)."),
        etirements(4, "D2"),
        rey(5, 125, "Retour au Pic du Rey (9,9 km, 935 m de D+, tes références : 2 h 01 en août 2025 avec 64 min de montée, 1 h 24 en "
            "avril 2026). Allure facile, montée en marche active, essaie les bâtons en montée et compare ton temps de montée.",
            "Pic du Rey : montée et descente (référence)"),
        Entree(6, "velo", "Vélo ou randonnée souple 1h", 60, "Récupération active.", prefs=("10:00", "15:00")),
        renfo(6, "C2", prefs=("18:00", "17:00")),
    ],
    # Semaine de Noël : sorties enchaînées (samedi puis dimanche), le 25 est un vrai repos.
    "2026-12-21": [
        ef(0, 40),
        cotes(1, 6, 90, 120, "Côtes de 1 min 30 à effort soutenu, redescente en trot."), renfo(1, "A3"),
        ef(2, 40), renfo(2, "B2"),
        etirements(3, "D1"),
        trail(5, 120, 800, "Première journée d'un enchaînement : allure facile, tu dois pouvoir courir demain."),
        trail(6, 75, 400, "Deuxième jour d'enchaînement : jambes lourdes attendues, c'est le but. Descente prudente.", dure=False),
    ],
    # Semaine allégée (environ moins 30 %) : on absorbe avant le gros bloc.
    "2026-12-28": [
        etirements(0, "D3"),
        ef(1, 40),
        cotes(2, 6, 45, 90, "Rappel court, effort à 8 sur 10."), renfo(2, "A2"),
        ef(3, 30),
        trail(5, 90, 500, "Sortie plaisir, allure facile."),
        Entree(6, "rando", "Rando avec bâtons 3 h 30", 220,
               "Marche active sur chemins de montagne, 600 à 800 m de D+, rythme de conversation. Peu d'impact, beaucoup de temps debout : c'est le pont "
               "entre les sorties de 2 h et la simulation de 5 h. Bâtons obligatoires, repas et boissons comme en course (toutes les 30 min), "
               "change sec dans le sac. Aucun footing, la rando suffit.", chaussures=SCOTT, prefs=("08:30", "09:30")),
    ],
    # Pic : séance de nuit, côtes longues, simulation de deux boucles.
    "2027-01-04": [
        ef(0, 40),
        cotes(1, 5, 240, 180, "Côtes longues, effort soutenu."), renfo(1, "A3"),
        ef(2, 40), renfo(2, "B3"),
        Entree(3, "ef", "Footing de nuit 1h à la frontale", 65,
               "Frontale chargée, couche chaude, même nutrition qu'en course. Sert à tester la lampe, l'allure de nuit et le froid.",
               chaussures=EF_PAIRE, prefs=("19:00", "19:30")),
        etirements(4, "D2"),
        Entree(5, "longue", "Simulation 24 h : 2 boucles au Pic du Rey (935 m de D+ chacune)", 300,
               "Deux boucles avec 1 h de pause entre elles : pause comme chez Tom (repas, vêtements secs, 10 min les jambes en l'air). "
               "Montée en marche active, descente relâchée. Photo au sommet. Objectif : repartir frais après la pause et "
               "tester ce que tu manges. Si La Rhune est trop loin : 2 fois la meilleure côte de 800 m de D+ de la région.",
               chaussures=SCOTT, prefs=("08:30", "09:30"), dure=True, etapes=(REP(2, T(105), R(60)),)),
        ef(6, 45, prefs=("09:30", "16:00")),
    ],
    # Dernière grosse semaine : volume conservé, intensité en baisse, aucune nouveauté.
    "2027-01-11": [
        etirements(0, "D3"),
        ef(1, 40),
        cotes(2, 8, 45, 90, "Côtes courtes, effort à 8 sur 10."), renfo(2, "A2"),
        ef(3, 35),
        etirements(4, "D1"),
        rey(5, 120, "Dernière longue sortie : une montée complète, travaille la descente (pas courts, bâtons au besoin). "
            "Chaussures, tenue et nutrition de la course.", "Pic du Rey : dernière sortie, descente"),
        ef(6, 40, prefs=("09:30", "16:00")),
    ],
    # Affûtage : le travail est fait. Fraîcheur, sommeil, logistique.
    "2027-01-18": [
        ef(0, 35, ld=4),
        cotes(1, 4, 60, 90, "Rappel court : 4 côtes d'une minute, effort à 7 sur 10, tu finis frais."),
        renfo(1, "C2", prefs=("18:30", "18:00")),
        Entree(2, "velo", "Vélo très souple 30 min ou repos", 30, "Facultatif.", prefs=("18:30", "10:00")),
        ef(3, 25, ld=4),
        etirements(4, "D3"),
    ],
})


# --- Après La Rhune : 10 km sous 40 min (4'00/km), test sur 5 km sous 20 min (3'59/km) --------------------------------
# Base : 10 km en 42'30, 5 km en 20'04, VMA 17,5 à 18 km/h (environ 3'20 au km). 4'00/km représente 83 à 86 % de la VMA :
# le facteur limitant est l'endurance à cette allure, pas la vitesse maximale. Le bloc Rhune a construit la base aérobie.
# Les dates des courses sont une hypothèse (10 km le 25/04/2027, test 5 km le 04/04) à confirmer par Tom.
from .garmin_course import _duree  # noqa: E402

CLUB_LIGNE = _p.club_ligne


def piste(jour: int, kind: str, titre: str, corps: str, etapes: tuple, famille=None, base=None, chaussures=SEUIL_BAS, club=True) -> Entree:
    duree = int(sum(_duree(e) for e in etapes) / 60) + 5
    return Entree(jour, kind, titre, duree, corps + (CLUB_LIGNE if club else ""), chaussures=chaussures, prefs=("18:30", "17:30"),
                  dure=True, etapes=etapes, famille=famille, allure_base=base)


def longue(jour: int, minutes: int, corps: str = "Allure facile, sur le plat ou vallonné.", tempo: int = 0) -> Entree:
    etapes = (E(minutes - tempo),) + ((IT(tempo * 60, 250, 4),) if tempo else ())
    return Entree(jour, "longue", f"Sortie longue {minutes // 60}h{minutes % 60:02d}" + (f" avec {tempo} min à allure seuil" if tempo else ""), minutes + 5,
                  corps + (f" Les {tempo} dernières minutes à 4'10/km." if tempo else ""), chaussures=EF_PAIRE, prefs=("09:00", "09:30"), dure=True,
                  etapes=etapes)


def vma(n: int, m: int, allure: int, rec: int, jour: int = 1) -> Entree:
    t = f"{m}m" if m < 1000 else f"{m // 1000}000m" if m % 1000 == 0 else f"{m}m"
    return piste(jour, "cotes", f"Fractionné {n}x{t} à {allure // 60}'{allure % 60:02d}/km",
                 f"Vitesse : {n}x{m} m à {allure // 60}'{allure % 60:02d}/km, récupération {rec} s en trot. Échauffement 20 min avec gammes, retour au calme 10 min.",
                 (W(20), REP(n, ID(m, allure), R(rec)), C(10)), base=allure)


def seuil(n: int, m: int, allure: int, rec: int, jour: int = 3) -> Entree:
    return piste(jour, "seuil", f"Seuil {n}x{m}m à {allure // 60}'{allure % 60:02d}/km",
                 f"Endurance à vitesse élevée : {n}x{m} m à {allure // 60}'{allure % 60:02d}/km, récupération {rec} s. Échauffement 20 min, retour au calme 10 min.",
                 (W(20), REP(n, ID(m, allure), R(rec)), C(10)), famille="seuil", base=allure)


def dix(n: int, m: int, allure: int, rec: int, jour: int = 1) -> Entree:
    return piste(jour, "as21", f"10 km : {n}x{m}m à {allure // 60}'{allure % 60:02d}/km",
                 f"Allure de course : {n}x{m} m à {allure // 60}'{allure % 60:02d}/km, récupération {rec} s. Échauffement 20 min, retour au calme 10 min.",
                 (W(20), REP(n, ID(m, allure), R(rec)), C(10)), famille="dix_km", base=allure, chaussures=CARBONE)


def strides(jour: int, minutes: int, n: int = 6) -> Entree:
    e = ef(jour, minutes)
    return Entree(e.jour, "ef", e.titre, e.duree, e.corps + f" Termine par {n} lignes droites de 20 s relâchées.", chaussures=EF_PAIRE, prefs=e.prefs,
                  etapes=(E(minutes), REP(n, IT(20, 235, 8), R(40))))


SEMAINES.update({
    # Récupération après les 24 h : aucune intensité, aucun renfo lourd. Le corps a encaissé 6 700 m de descente.
    "2027-01-25": [
        Entree(0, "velo", "Marche ou vélo très souple 40 min", 40, "Récupération active, sans impact.", prefs=("10:00", "15:00")),
        etirements(1, "D3"), ef(2, 30), etirements(4, "D3"),
        ef(5, 35, prefs=("09:30", "16:00")),
        renfo(6, "C1", prefs=("18:00", "17:00")),
    ],
    # Reprise : le volume remonte en douceur, premières lignes droites, renfo à charge modérée.
    "2027-02-01": [
        ef(0, 35), strides(1, 40), renfo(1, "A2"),
        ef(2, 45), renfo(2, "B1"),
        ef(3, 35), etirements(4, "D1"),
        longue(5, 60), Entree(6, "velo", "Vélo souple 1h", 60, "Cadence 90 rpm.", prefs=("10:00", "15:00")),
    ],
    "2027-02-08": [
        ef(0, 40), strides(1, 45), renfo(1, "A1"),
        ef(2, 45), renfo(2, "B2"),
        cotes(3, 8, 30, 90, "Côtes courtes de 30 s à effort élevé (8 sur 10), redescente en trot. Prépare la puissance sans l'intensité des 400 m.", prefs=("18:30", "17:30")),
        etirements(4, "D2"),
        longue(5, 75), ef(6, 40, prefs=("09:30", "16:00")),
    ],
    "2027-02-15": [
        ef(0, 40), piste(1, "seuil", "Fartlek 10x1 min vif", "10 fois 1 min vif (environ 4'05/km) pour 1 min de trot. Échauffement 20 min, retour au calme 10 min.",
                         (W(20), REP(10, IT(60, 245, 6), R(60)), C(10)), famille="seuil", base=245), renfo(1, "A1"),
        ef(2, 45), renfo(2, "B1"),
        ef(3, 40), etirements(4, "D1"),
        longue(5, 80), ef(6, 40, prefs=("09:30", "16:00")),
    ],
    # Développement : la vitesse de base (VMA) et l'endurance à allure élevée.
    "2027-02-22": [
        ef(0, 40), vma(8, 400, 200, 75), renfo(1, "A3"),
        ef(2, 45), renfo(2, "B1"),
        ef(3, 45), etirements(4, "D2"),
        longue(5, 80), ef(6, 40, prefs=("09:30", "16:00")),
    ],
    "2027-03-01": [
        ef(0, 40), vma(10, 400, 200, 75), renfo(1, "A1"),
        ef(2, 45), renfo(2, "B2"),
        seuil(4, 1500, 250, 120), etirements(4, "D1"),
        longue(5, 90), ef(6, 40, prefs=("09:30", "16:00")),
    ],
    # Semaine allégée : on absorbe avant le bloc spécifique.
    "2027-03-08": [
        ef(0, 35), vma(6, 400, 200, 75), renfo(1, "A2"),
        ef(2, 40), ef(3, 40), etirements(4, "D3"),
        longue(5, 60), Entree(6, "velo", "Vélo souple 1h", 60, "Récupération.", prefs=("10:00", "15:00")),
    ],
    "2027-03-15": [
        ef(0, 40), vma(6, 800, 212, 90), renfo(1, "A1"),
        ef(2, 45), renfo(2, "C1"),
        seuil(3, 2000, 250, 120), etirements(4, "D2"),
        longue(5, 90, tempo=15), ef(6, 40, prefs=("09:30", "16:00")),
    ],
    # Spécifique : l'allure du 10 km (4'00/km) devient familière.
    "2027-03-22": [
        ef(0, 40), dix(5, 1000, 235, 90), renfo(1, "A2"),
        ef(2, 45), renfo(2, "B1"),
        seuil(3, 2500, 248, 120), etirements(4, "D1"),
        longue(5, 90), ef(6, 40, prefs=("09:30", "16:00")),
    ],
    "2027-03-29": [
        ef(0, 40), dix(6, 1000, 238, 75), renfo(1, "A2"),
        ef(2, 45), ef(3, 40), etirements(4, "D3"),
        ef(5, 30, prefs=("09:30", "16:00")),
        Entree(6, "as21", "Test 5 km : objectif sous 20 min (3'59/km)", 35,
               "Course ou contre-la-montre sur 5 km, à fond mais régulier (3'59/km). Échauffement 15 min, gammes, 3 accélérations. Mesure ton niveau avant le 10 km. "
               "Date du test à confirmer (4 avril supposé).", chaussures=CARBONE, prefs=("09:00", "09:30"), dure=True,
               etapes=(W(15), ID(5000, 239, 5), C(10)), famille="dix_km", allure_base=239),
    ],
    "2027-04-05": [
        ef(0, 35), dix(4, 1500, 240, 120), renfo(1, "A2"),
        ef(2, 45), renfo(2, "C2"),
        seuil(3, 2000, 248, 120), etirements(4, "D1"),
        longue(5, 80), ef(6, 40, prefs=("09:30", "16:00")),
    ],
    "2027-04-12": [
        ef(0, 40), dix(3, 2000, 240, 120), renfo(1, "C2"),
        ef(2, 40), ef(3, 35), etirements(4, "D2"),
        longue(5, 60), ef(6, 35, prefs=("09:30", "16:00")),
    ],
    # Affûtage : volume réduit, quelques rappels à allure de course, fraîcheur.
    "2027-04-19": [
        ef(0, 35, ld=4), dix(4, 1000, 240, 120), renfo(1, "C2", prefs=("18:30", "18:00")),
        Entree(2, "velo", "Vélo très souple 30 min ou repos", 30, "Facultatif.", prefs=("18:30", "10:00")),
        ef(3, 25, ld=4), etirements(4, "D3"),
        Entree(5, "ef", "Décrassage de la veille 15 min", 20, "15 min très souples + 4 lignes droites. Prépare dossard, chaussures, nutrition.",
               chaussures=EF_PAIRE, prefs=("10:00", "17:00"), etapes=(E(15, 330, 360),) + lignes_droites(4)),
    ],
})
