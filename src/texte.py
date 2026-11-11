"""Mise en forme des notifications : sections lisibles sur téléphone, vocabulaire français."""
import re

HRV = {"BALANCED": "équilibrée", "UNBALANCED": "déséquilibrée", "LOW": "basse", "POOR": "faible"}
_PARTIE = {"Morning": "du matin", "Lunch": "du midi", "Afternoon": "de l'après-midi", "Evening": "du soir", "Night": "de nuit"}
_SPORT = {"Run": "Course", "Trail Run": "Trail", "Mountain Bike Ride": "Sortie VTT", "Gravel Ride": "Sortie gravel",
          "Virtual Ride": "Vélo d'appartement", "Ride": "Sortie vélo", "Walk": "Marche", "Hike": "Randonnée",
          "Workout": "Séance", "Weight Training": "Renforcement", "Swim": "Natation", "Yoga": "Yoga"}


def nom_fr(nom: str) -> str:
    """« Afternoon Mountain Bike Ride » -> « Sortie VTT de l'après-midi ». Un nom déjà français reste tel quel."""
    m = re.fullmatch(r"(Morning|Lunch|Afternoon|Evening|Night) (.+)", nom)
    if m and m[2] in _SPORT:
        return f"{_SPORT[m[2]]} {_PARTIE[m[1]]}"
    return _SPORT.get(nom, nom)


def duree_h(h) -> str:
    if h is None:
        return "n/d"
    m = round(h * 60)
    return f"{m // 60} h {m % 60:02d}"


# Demandés explicitement par Tom pour les notifications ntfy (pas pour les docs ni les commits).
EMOJI = {
    "Séance": "🏃", "Séances": "🏃", "Météo": "🌤️", "Météo de demain": "🌤️", "Forme": "🔋", "Attention": "⚠️", "À prévoir": "🎒", "Repas": "🍌", "Chaussures": "👟",
    "Dernière sortie": "🏁", "Demain": "📅", "Ce soir": "🌙", "Sources en panne": "🚨", "Prévu": "🎯", "Verdict": "✅", "Bilan": "📊", "Blocs": "⏱️", "Analyse": "🔍", "Récupération": "💧",
    "Course à pied": "🏃", "Vélo et autres": "🚴", "Séances prévues": "✅", "Sommeil": "😴", "Charge": "📈", "Plan": "🧭", "Décisions du coach": "🧭",
    "Club ASM (mardi et jeudi, 17:30 fractionné, 18:30 au choix)": "🏟️",
    "Départ": "🏁", "Demain : Lourdes-Tarbes": "🏁", "À préparer ce soir": "🎒", "Météo à prévoir": "🌤️", "Tenue": "👕", "Réveil et repas": "🍽️", "Échauffement": "🔥",
    "Allures": "⏱️", "Ravitaillement": "🥤", "Résultat": "🏅", "Passages": "📍", "Parcours conseillé": "🗺️", "Agenda": "🕒", "À faire": "📝", "Semaine à venir": "🗓️",
    "Contraintes": "💼",
}


def bloc(titre: str, lignes, puces: bool = False) -> str:
    lignes = [l for l in ([lignes] if isinstance(lignes, str) else lignes or []) if l]
    if not lignes:
        return ""
    corps = [f"- {l}" for l in lignes] if puces else lignes
    icone = EMOJI.get(titre)
    return (f"{icone} " if icone else "") + titre.upper() + "\n" + "\n".join(corps)


def message(*blocs: str) -> str:
    return "\n\n".join(b for b in blocs if b)


JOURS = ["lun", "mar", "mer", "jeu", "ven", "sam", "dim"]


def jour_court(date: str) -> str:
    import datetime as dt
    d = dt.date.fromisoformat(date)
    return f"{JOURS[d.weekday()]} {d.day:02d}/{d.month:02d}"
