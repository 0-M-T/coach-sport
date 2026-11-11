"""Noms français et consignes des exercices de renfo, pour la fiche de la séance : la montre et l'appli Garmin sont en anglais, sans fiche pour certains exercices.

Clé = nom Garmin exact de `garmin_renfo.CIRCUITS_GARMIN`. Valeur = (nom français, consigne, lien).
Lien None : recherche YouTube en français (jamais d'identifiant de vidéo inventé).
"""

from urllib.parse import quote_plus

FR = {
    "Alternating Box Dumbbell Step-ups": ("Montées sur banc alternées avec haltères", "Un pied sur le banc, monte en poussant dans le talon, redescends lentement, une jambe puis l'autre.", None),
    "Banded Row": ("Tirage horizontal à l'élastique", "Assis ou debout, élastique accroché devant toi, tire les coudes vers l'arrière en serrant les omoplates.", None),
    "Dead Bug": ("Insecte mort (gainage au sol)", "Sur le dos, bras et genoux en l'air, étends bras et jambe opposés en gardant le bas du dos collé au sol.", None),
    "Dumbbell Bench Press": ("Développé couché avec haltères", "Sur le banc, descends les haltères à hauteur de poitrine, coudes à 45°, puis pousse.", None),
    "Dumbbell Lying Triceps Extension": (
        "Extension des triceps allongé avec haltères",
        "Sur le banc, bras tendus, plie les coudes sans les écarter pour descendre les haltères près du front, puis étends.",
        None,
    ),
    "Dumbbell Reverse Lunge": ("Fente arrière avec haltères", "Recule une jambe, descends à la verticale, genou arrière près du sol, remonte en poussant dans le talon avant.", None),
    "Dumbbell Row": ("Rowing avec haltère", "Une main et un genou sur le banc, dos plat, tire l'haltère vers la hanche.", None),
    "Dumbbell Shoulder Press": ("Développé épaules avec haltères", "Assis ou debout, pousse les haltères au-dessus de la tête sans cambrer.", None),
    "Face Pull": ("Tirage visage à l'élastique", "Élastique à hauteur du visage, tire vers le front en écartant les coudes.", None),
    "Farmer's Walk": ("Marche du fermier", "Un haltère lourd dans chaque main, marche droit, épaules basses, gainé.", None),
    "Goblet Squat": ("Squat gobelet", "Haltère tenu contre la poitrine, descends en gardant le dos droit et les talons au sol, remonte.", None),
    "Hip Raise": ("Pont fessier", "Sur le dos, genoux fléchis, monte le bassin en serrant les fessiers 1 s, redescends sans poser.", None),
    "Incline Dumbbell Bench Press": ("Développé incliné avec haltères", "Banc incliné, même geste que le développé couché, dirigé vers le haut de la poitrine.", None),
    "Jump Rope": ("Corde à sauter", "Petits sauts légers, poignets qui tournent la corde, rebonds sur l'avant-pied.", None),
    "Kneeling Ab Wheel": ("Roue abdominale à genoux", "Roule vers l'avant en gardant le dos plat, reviens en contractant les abdos. Amplitude progressive.", None),
    "Plank": ("Planche (gainage)", "Appui sur les avant-bras, corps aligné de la tête aux talons, abdos et fessiers serrés.", None),
    "Push-up": ("Pompes", "Mains sous les épaules, corps gainé, poitrine près du sol, puis pousse.", None),
    "Romanian Deadlift": ("Soulevé de terre roumain", "Jambes presque tendues, charge qui descend le long des cuisses, dos plat, hanches vers l'arrière, remonte en poussant les hanches.", None),
    "Seated Calf Raise": (
        "Mollets assis",
        "Assis, charge sur les cuisses, monte sur la pointe des pieds, pause 1 s, redescends en 3 s. Cible le soléaire.",
        "https://www.musculation-halteres.fr/mollets-assis-halteres/",
    ),
    "Side Plank": ("Planche latérale", "Appui sur un avant-bras, corps aligné de profil, bassin haut, tiens le temps indiqué de chaque côté.", None),
    "Single-arm Neutral-grip Dumbbell Row": ("Rowing à un bras, prise neutre", "Une main sur le banc, dos plat, tire l'haltère vers la hanche, paume tournée vers le corps.", None),
    "Single-leg Romanian Deadlift with Dumbbell": (
        "Soulevé de terre roumain à une jambe avec haltère",
        "Sur une jambe, penche le buste en reculant l'autre jambe tendue, dos plat, bassin face au sol, remonte en poussant la hanche. Deux côtés.",
        "https://www.youtube.com/watch?v=A6MYR61mLTo",
    ),
    "Single-leg Standing Calf Raise": ("Mollets debout sur une jambe", "Sur une jambe, monte sur la pointe du pied, pause 1 s, redescends en 3 s, talon bas. Main sur un mur pour l'équilibre.", None),
    "Single-leg Standing Dumbbell Calf Raise": (
        "Mollets debout sur une jambe avec haltère",
        "Comme les mollets debout, haltère dans la main du côté travaillé. Pars sans charge si le geste n'est pas en place.",
        "https://www.superphysique.org/exercices/127",
    ),
    "Walking Dumbbell Lunge": ("Fentes marchées avec haltères", "Fente vers l'avant, genou avant au-dessus de la cheville, puis passe la jambe arrière devant et enchaîne en marchant.", None),
}


# Charge prévue : (kg par haltère, nombre d'haltères). (0, 0) = sans poids. Absent = pas de charge prévue.
# Source : charges déclarées par Tom le 2026-11-11 (docs/CHARGES_RENFO.md), à tenir à jour avec le journal.
CHARGES = {
    "Single-leg Romanian Deadlift with Dumbbell": (4, 1),
    "Dumbbell Reverse Lunge": (2, 2),
    "Hip Raise": (0, 0),
    "Single-leg Standing Dumbbell Calf Raise": (0, 0),
    "Seated Calf Raise": (10, 1),
}


def charge_kg(nom_garmin: str) -> float | None:
    """Charge totale soulevée, pour la montre (shortcut : total des haltères, pas par haltère ; à revoir si l'affichage prête à confusion)."""
    kg, nb = CHARGES.get(nom_garmin, (0, 0))
    return float(kg * nb) or None


def charge_texte(nom_garmin: str) -> str:
    if nom_garmin not in CHARGES:
        return ""
    kg, nb = CHARGES[nom_garmin]
    if not nb:
        return "sans poids"
    return f"1 seul haltère de {kg} kg" if nb == 1 else f"{nb} haltères de {kg} kg chacun (un dans chaque main)"


def lien(nom_garmin: str) -> str:
    fr, _, url = FR[nom_garmin]
    return url or f"https://www.youtube.com/results?search_query={quote_plus(fr + ' technique')}"


def lignes(code: str) -> list[str]:
    """Une ligne par exercice du circuit : nom Garmin = nom français, consigne, lien. Vide si le circuit n'existe pas côté Garmin."""
    from .garmin_renfo import CIRCUITS_GARMIN  # import tardif : garmin_renfo charge garminconnect

    lignes = []
    for nom, _, _ in CIRCUITS_GARMIN.get(code, []):
        fr, consigne, _ = FR[nom]
        charge = charge_texte(nom)
        lignes.append(f"{nom} = {fr} : {consigne}" + (f" Charge : {charge}." if charge else "") + f" {lien(nom)}")
    return lignes
