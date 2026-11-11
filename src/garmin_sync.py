#!/usr/bin/env python3
import datetime as dt
from . import baikal, fiche, garmin
from .config import load_config

def fiche_garmin(name: str, garmin_url: str) -> tuple[str, list[tuple[str, list[str]]]]:
    """Séance du calendrier Garmin sans équivalent dans le plan du coach : repères selon son type (voir `fiche.py`)."""
    n = name.lower()
    if "as21" in n or "semi" in n or "seuil" in n:
        sections = [("Objectif", ["Allure semi : 4'20 à 4'27/km, cible 4'25/km"]),
                    ("Échauffement · 20 min", ["5 min de mobilité articulaire", "15 min de footing progressif, de 5'45 à 5'15/km", "Gammes et 3 accélérations progressives"]),
                    ("Corps de séance", [f"{name}, récupération active de 2 à 3 min en trot souple"]),
                    ("Retour au calme · 10 min", ["Footing très souple, au-dessus de 6'00/km"]),
                    ("Matériel", ["Chaussures : Adidas Evo SL ou ASICS Metaspeed Sky Paris"])]
    elif "vma" in n or "400m" in n or "piste" in n:
        sections = [("Objectif", ["VMA courte ou piste ASM : 1'20 au 400 m ou 2'50 au 800 m"]),
                    ("Échauffement · 25 min", ["15 min de footing lent, gammes complètes"]), ("Retour au calme · 10 min", ["Footing très souple"])]
    elif "ef" in n or "footing" in n:
        sections = [("Objectif", ["Endurance fondamentale : 5'15 à 5'35/km, FC sous 145"]), ("Matériel", ["Chaussures : Adidas Evo SL"])]
    elif "trail" in n or "cote" in n:
        sections = [("Objectif", ["Dénivelé et renforcement spécifique"]), ("Matériel", ["Chaussures : NNormal Kjerag ou Scott Kinabalu"])]
    else:
        sections = []
    return name, sections + [("Garmin", [garmin_url])]


def generate_workout_description(name: str, garmin_url: str) -> str:
    return fiche.texte(*fiche_garmin(name, garmin_url))


def heure_seance(h: str, conf: dict) -> str:
    """Le créneau matinal de 07:30 est décalé à 08:30 (COACH_HEURE_MATIN_DE / COACH_HEURE_MATIN)."""
    return conf.get("COACH_HEURE_MATIN", "08:30") if h == conf.get("COACH_HEURE_MATIN_DE", "07:30") else h


def sync_garmin_to_baikal(conf=None):
    conf = load_config() if conf is None else conf
    c = garmin.client(conf)
    today = dt.date.today()
    from . import garmin_renfo, planif
    gerees = garmin_renfo.ids_programmes(planif.charger())
    events = c.get_calendar_events(today.strftime("%Y-%m-%d"), (today + dt.timedelta(days=30)).strftime("%Y-%m-%d")) or []
    creees = 0
    for ev in events:
        name = ev.get("eventName") or ev.get("title") or "Entraînement Garmin"
        date_str = ev.get("date")
        if not date_str:
            continue
        wid, eid = ev.get("workoutId"), ev.get("id")
        if wid in gerees:  # séance de renfo posée par le coach : l'événement Baïkal existe déjà
            continue
        if wid:
            garmin_url = f"https://connect.garmin.com/modern/workout/{wid}"
        elif eid:
            garmin_url = f"https://connect.garmin.com/modern/event/{eid}"
        else:
            garmin_url = "https://connect.garmin.com/modern/calendar"
        t = ev.get("eventTimeLocal")
        time_str = t.get("startTimeHhMm", "08:00") if isinstance(t, dict) else "08:00"
        time_str = heure_seance(time_str, conf)
        sh, sm = map(int, time_str.split(":"))
        if not any(name in l for l in baikal.lister(date_str)):
            baikal.creer(name, f"{date_str}T{time_str}", f"{date_str}T{(sh + 1) % 24:02d}:{sm:02d}",
                         generate_workout_description(name, garmin_url), garmin_url, html=fiche.en_html(*fiche_garmin(name, garmin_url)))
            creees += 1
    print(f"Sync Garmin -> Baikal OK ({creees} créée(s))")


if __name__ == "__main__":
    sync_garmin_to_baikal()
