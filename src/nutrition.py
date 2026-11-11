"""Conseils de repas selon les séances du jour. Tom ne boit pas de café : jamais de café ni de caféine."""
import re

from . import baikal

DURES = ("seuil", "as21", "côte", "cote", "fraction", "rappel d'allure", "longue", "trail", "simulation", "semi", "course", "rando")
FACILES = ("ef", "footing", "décrassage", "decrassage", "souple")
JEUN_MAX_MIN = 45   # shortcut: seuil unique pour tous, à affiner si Tom le supporte mal
LONG_MIN = 75       # au-delà : glucides pendant l'effort


def _minutes(titre: str) -> int | None:
    t = titre.lower()
    if m := re.search(r"(\d+)\s*min", t):
        return int(m[1])
    if m := re.search(r"(\d+)\s*h\s*(\d{2})?", t):
        return int(m[1]) * 60 + int(m[2] or 0)
    return None


def classer(ligne: str) -> tuple[str, int | None, str] | None:
    """(niveau, minutes, heure) : 'dur' ou 'facile' pour une séance de course ou de vélo, None pour renfo, étirements, activation."""
    d = baikal.debut(ligne)
    t = baikal.court(ligne).lower()
    if not d or d[1] == "journée" or any(k in t for k in ("renfo", "activation", "étirement", "etirement")):
        return None
    titre = t.split(" ", 1)[1]
    minutes = _minutes(titre)
    if any(k in titre for k in DURES) or (minutes or 0) >= 90:
        return "dur", minutes, d[1]
    if "cap:" in titre and re.search(r"\b(" + "|".join(FACILES) + r")\b", titre):
        return "facile", minutes, d[1]
    return "facile", minutes, d[1]


def a_jeun(ligne: str, fatigue: bool = False) -> bool:
    """Footing facile court avant 10 h 30, sans signe de fatigue : séance à jeun possible."""
    c = classer(ligne)
    return bool(c and c[0] == "facile" and "cap:" in ligne.lower() and not fatigue
                and (c[1] or 99) <= JEUN_MAX_MIN and c[2] < "10:30")


def _moins(h: str, minutes: int) -> str:
    t = (int(h[:2]) * 60 + int(h[3:]) - minutes) % 1440
    return f"{t // 60:02d}:{t % 60:02d}"


def repas_jour(lignes: list[str], fatigue: bool = False) -> list[str]:
    """Repas du jour, une séance de course ou de vélo à la fois (renfo et étirements ne changent rien)."""
    out = []
    for l in lignes:
        c = classer(l)
        if not c:
            continue
        niveau, minutes, h = c
        if a_jeun(l, fatigue):
            out += [f"Séance à jeun à {h} : rien à manger avant, un grand verre d'eau au réveil, allure facile",
                    "Après : petit-déjeuner complet dans l'heure (2 oeufs, banane, céréales)"]
        elif h < "11:00":
            if niveau == "dur":
                out += [f"{_moins(h, 150)} : petit-déjeuner complet (2 oeufs, banane, 70 à 80 g de céréales avec du lait ou un yaourt)"]
            else:
                out += [f"{_moins(h, 90)} : petit-déjeuner léger (banane, 50 g de céréales), les oeufs après la séance"]
            if fatigue and niveau == "facile":
                out += ["Fatigue détectée : mange avant de courir, pas de séance à vide aujourd'hui"]
        elif h < "16:00":
            out += [f"{_moins(h, 180)} : repas riche en glucides (pâtes ou riz), peu de gras et de fibres", f"{_moins(h, 60)} : banane ou compote"]
        else:
            out += ["Déjeuner riche en glucides (pâtes ou riz), peu de gras et de fibres", f"{_moins(h, 60)} : banane ou compote, pas d'oeufs"]
        if minutes and minutes >= LONG_MIN:
            out += ["Pendant : eau, et 30 à 45 g de glucides par heure (pâte de fruits, compote) au-delà d'1 h 15"]
        if niveau == "dur" or not a_jeun(l, fatigue):
            out += ["Après : glucides et protéines dans l'heure (yaourt et céréales, ou oeufs et pain)"]
    return list(dict.fromkeys(out))


def repas_veille(lignes_demain: list[str]) -> list[str]:
    """Briefing du soir : ce qu'il faut manger ce soir, et si la séance de demain se fait à jeun."""
    out = []
    for l in lignes_demain:
        c = classer(l)
        if not c:
            continue
        if c[0] == "dur":
            out.append("Dîner riche en glucides (pâtes, riz ou patate douce, 200 g cuits), peu de gras et de fibres")
        if a_jeun(l):
            out.append(f"Demain {c[2]} : séance à jeun, rien avant, un verre d'eau (pas à jeun si tu te réveilles fatigué)")
    return list(dict.fromkeys(out))
