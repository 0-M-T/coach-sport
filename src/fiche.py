"""Mise en forme des descriptions d'événements : texte brut lisible partout (téléphone, Thunderbird, Baïkal) et HTML pour Thunderbird et Outlook.

Une fiche = un titre et des sections (titre, lignes). Une ligne qui finit par « : » est une introduction, les autres sont des puces.
Le texte libre du plan est découpé ici : une phrase par ligne, et pour le renfo un exercice par ligne (coupure après chaque série, « 3x8 »).
"""

import html
import re

SERIE = r"\d+\s?x\s?\d+(?:-\d+)?(?: ?(?:s|min|m|pas))?(?: par (?:côté|jambe|pied))?(?: \([^)]*\))*"


def ajouter(corps: str, phrase: str) -> str:
    """Ajoute une phrase au texte d'une séance avec sa ponctuation (sans point, les deux phrases se fondraient en une seule ligne)."""
    corps = (corps or "").strip()
    return f"{corps.rstrip('.')}. {phrase}" if corps else phrase


def phrases(texte: str) -> list[str]:
    """Une phrase par ligne, sans le point final."""
    return [p.strip().rstrip(".") for p in re.split(r"(?<=[.!?])\s+(?=[A-ZÉÈÀÂÎÔÛ0-9«])", (texte or "").strip()) if p.strip()]


def exercices(phrase: str) -> list[str]:
    """« Charge réduite, 2 séries : a 2x8, b 2x10 » -> ["Charge réduite, 2 séries :", "a 2x8", "b 2x10"]. Une phrase sans série reste entière."""
    tete, sep, reste = phrase.partition(" : ")
    if not (sep and re.search(SERIE, reste)) or re.search(SERIE, tete):   # « mollets : x 3x10 » au milieu d'une liste n'est pas une introduction
        tete, reste = "", phrase
    out, cur = [], ""
    for frag in reste.split(", "):
        cur = f"{cur}, {frag}" if cur else frag
        if re.search(SERIE + r"$", cur):
            out.append(cur)
            cur = ""
    if cur:
        out.append(cur)
    return ([f"{tete} :"] if tete else []) + out


def lignes_renfo(texte: str) -> list[str]:
    return [x for p in phrases(texte) for x in exercices(p)]


def texte(titre: str, sections: list[tuple[str, list[str]]], pied: str = "") -> str:
    blocs = [titre]
    for nom, lignes in sections:
        if lignes:
            blocs.append(nom.upper() + "\n" + "\n".join(l if l.endswith(":") else f"• {l}" for l in lignes))
    if pied:
        blocs.append(pied)
    return "\n\n".join(blocs)


def en_html(titre: str, sections: list[tuple[str, list[str]]], pied: str = "") -> str:
    e = html.escape
    out = [f"<p><b>{e(titre)}</b></p>"]
    for nom, lignes in sections:
        if not lignes:
            continue
        out.append(f"<p><b>{e(nom)}</b></p>")
        items = []
        for l in lignes:
            if l.endswith(":"):
                if items:
                    out.append("<ul>" + "".join(items) + "</ul>")
                    items = []
                out.append(f"<p>{e(l)}</p>")
            else:
                items.append(f"<li>{e(l)}</li>")
        if items:
            out.append("<ul>" + "".join(items) + "</ul>")
    if pied:
        out.append(f"<p><i>{e(pied)}</i></p>")
    return "<html><body>" + "".join(out) + "</body></html>"
