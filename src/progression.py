"""Progression des allures cibles d'après les bilans des dernières séances d'une famille (seuil, allure semi).

Règles (bornées, jamais d'allure semi plus lente que 4'27) :
- écart moyen des blocs de la dernière séance au moins 3 s/km plus rapide que la cible, FC non montée de plus de 5 bpm : cible 2 s plus rapide ;
- écart d'au moins 5 s/km plus lent que la cible : cible 3 s plus lente ;
- sinon : on garde.
"""
import dataclasses

from . import fiche
from .plan import Entree

BORNES = {"seuil": (-6, 9), "as21": (-3, 2), "dix_km": (-4, 3)}   # correction cumulée par rapport à l'allure de base, en s/km


def fmt(s: int) -> str:
    return f"{s // 60}'{s % 60:02d}"


def correction(bilans: list[dict], famille: str, base: int) -> tuple[int, str]:
    """(correction cumulée en s/km, raison) à appliquer à la prochaine séance de la famille."""
    h = [b for b in bilans if b.get("famille") == famille][-2:]
    if not h:
        return 0, ""
    dernier = h[-1]
    actuelle = int(dernier["cible"]) - base
    lo, hi = BORNES[famille]
    e = dernier["ecart"]
    fc_ok = len(h) < 2 or not (h[0].get("fc") and dernier.get("fc")) or dernier["fc"] <= h[0]["fc"] + 5
    if e <= -3 and fc_ok:
        nouvelle, raison = actuelle - 2, f"dernière séance {abs(e):.0f} s/km plus rapide que prévu"
    elif e >= 5:
        nouvelle, raison = actuelle + 3, f"dernière séance {e:.0f} s/km plus lente que prévu"
    else:
        nouvelle, raison = actuelle, ""
    return max(lo, min(hi, nouvelle)), raison


def _remplacer(etape, base: int, nouvelle: int):
    k = etape[0]
    if k in ("id", "it") and etape[2] == base:
        return (k, etape[1], nouvelle, etape[3])
    if k == "rep":
        return ("rep", etape[1], [_remplacer(e, base, nouvelle) for e in etape[2]])
    return tuple(etape) if not isinstance(etape, tuple) else etape


def appliquer(e: Entree, bilans: list[dict]) -> Entree:
    """Entrée avec l'allure ajustée (étapes, titre, texte). Inchangée sans bilan ou hors famille suivie."""
    if not (e.famille and e.allure_base):
        return e
    corr, raison = correction(bilans, e.famille, e.allure_base)
    if corr == 0:
        return e
    base, nouvelle = e.allure_base, e.allure_base + corr
    note = f"Allure ajustée par le coach : {fmt(nouvelle)}/km ({corr:+d} s/km)" + (f", {raison}." if raison else ".")
    return dataclasses.replace(
        e, titre=e.titre.replace(fmt(base), fmt(nouvelle)), corps=fiche.ajouter(e.corps.replace(fmt(base), fmt(nouvelle)), note),
        etapes=tuple(_remplacer(x, base, nouvelle) for x in e.etapes), allure_base=nouvelle)
