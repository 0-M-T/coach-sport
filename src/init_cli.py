"""Questionnaire interactif en terminal pour l'onboarding initial (sans agent IA)."""
from .profil import Profil, sauvegarder_profil
from . import chemins


def run_init() -> int:
    print("=== Configuration initiale de Coach Sportif ===")
    print("Répondez à quelques questions pour calibrer votre entraînement (Entrée = valeur par défaut).\n")

    prenom = input("Votre prénom [Athlète] : ").strip() or "Athlète"

    print("\nVotre objectif principal :")
    print("1. Reprise progressive (post-blessure ou reprise d'activité)")
    print("2. 5 km")
    print("3. 10 km")
    print("4. Semi-marathon")
    print("5. Marathon / Trail")
    choix_obj = input("Choix (1-5) [1] : ").strip() or "1"

    objectifs_map = {
        "1": [{"nom": "Reprise progressive course à pied", "date": "2026-12-31", "priorite": "A"}],
        "2": [{"nom": "5 km sous 25 min", "date": "2027-03-31", "priorite": "A"}],
        "3": [{"nom": "10 km sous 50 min", "date": "2027-04-30", "priorite": "A"}],
        "4": [{"nom": "Semi-marathon", "date": "2027-05-31", "priorite": "A"}],
        "5": [{"nom": "Marathon / Trail", "date": "2027-10-31", "priorite": "A"}],
    }
    objectifs = objectifs_map.get(choix_obj, objectifs_map["1"])

    blessure = input("\nAvez-vous une douleur ou blessure récente à signaler ? (o/N) : ").strip().lower()
    if blessure.startswith("o"):
        print("Note : Le plan intègrera des séances douces marche/course et des rappels de prudence.")

    print("\nQuel équipement utilisez-vous principalement ?")
    print("1. Aucune montre (téléphone seul)")
    print("2. Garmin")
    print("3. Coros / Suunto / Polar (via Intervals.icu)")
    print("4. Strava seul")
    choix_montre = input("Choix (1-4) [1] : ").strip() or "1"
    montre_map = {"1": "aucune", "2": "garmin", "3": "intervals", "4": "strava"}
    montre = montre_map.get(choix_montre, "aucune")

    # Création du profil
    nouveau_profil = Profil(
        prenom=prenom,
        objectifs=objectifs,
        montre=montre,
    )

    dest = chemins.config_dir() / "profile.yaml"
    cible = sauvegarder_profil(nouveau_profil, chemin=dest)

    print(f"\n[OK] Profil enregistré avec succès dans : {cible}")
    print("Pour consulter la séance du jour : coach next")
    print("Pour exporter votre calendrier : coach export-ics")
    print("Pour vérifier les connexions : coach doctor")
    return 0
