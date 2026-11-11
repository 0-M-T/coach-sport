"""Diagnostic des intégrations et de la configuration du coach."""
import sys
from . import chemins
from .config import load_config
from .profil import charger_profil, chercher_fichier_profil


def diagnostiquer() -> dict[str, tuple[bool, str]]:
    conf = load_config()
    prof = charger_profil()
    f_prof = chercher_fichier_profil()

    resultats: dict[str, tuple[bool, str]] = {}

    # 1. Système & Python
    py_ok = sys.version_info >= (3, 11)
    resultats["Python"] = (py_ok, f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")

    # 2. Profil
    if f_prof:
        resultats["Profil"] = (True, f"{prof.prenom} ({f_prof})")
    else:
        resultats["Profil"] = (False, f"Défaut en mémoire ({prof.prenom}), aucun profile.yaml trouvé")

    # 3. Dossiers
    resultats["État local"] = (chemins.state_dir().is_dir(), str(chemins.state_dir()))

    # 4. Garmin
    has_garmin = bool(conf.get("GARMIN_EMAIL") or conf.get("GARMIN_TOKENS"))
    resultats["Garmin"] = (has_garmin, "Actif (identifiants présents)" if has_garmin else "Inactif (optionnel)")

    # 5. Strava
    has_strava = bool(conf.get("STRAVA_CLIENT_ID") and (conf.get("STRAVA_REFRESH_TOKEN") or chemins.strava_token_path().exists()))
    resultats["Strava"] = (has_strava, "Actif (API configurée)" if has_strava else "Inactif (optionnel)")

    # 5b. Intervals.icu (Coros, Suunto, Polar, Wahoo)
    has_intervals = bool(conf.get("INTERVALS_API_KEY") and conf.get("INTERVALS_ATHLETE_ID"))
    resultats["Intervals.icu"] = (has_intervals, "Actif (Coros/Suunto/Polar)" if has_intervals else "Inactif (optionnel)")

    # 6. Agenda / CalDAV
    has_caldav = bool(conf.get("BAIKAL_URL") or conf.get("CALDAV_URL"))
    resultats["Agenda CalDAV"] = (has_caldav, "Actif" if has_caldav else "Inactif (mode local / fichier .ics)")

    # 7. Notifications ntfy
    has_ntfy = bool(conf.get("NTFY_URL"))
    resultats["Notifications ntfy"] = (has_ntfy, conf.get("NTFY_URL", "Inactif (sortie terminal seule)"))

    # 8. Home Assistant
    has_ha = bool(conf.get("HA_URL") and conf.get("HA_TOKEN"))
    resultats["Home Assistant"] = (has_ha, conf.get("HA_URL", "Inactif (optionnel)"))

    # 9. Parcours GPX
    gpx_p = chemins.gpx_dir()
    nb_gpx = len(list(gpx_p.glob("*.gpx"))) if gpx_p.is_dir() else 0
    resultats["Boucles GPX"] = (nb_gpx > 0, f"{nb_gpx} parcours trouvés dans {gpx_p}")

    return resultats


def afficher_rapport() -> int:
    rapport = diagnostiquer()
    print("=== Diagnostic Coach Sportif ===")
    tous_ok = True
    for composant, (ok, detail) in rapport.items():
        symbole = "[OK]" if ok else "[--]"
        print(f"{symbole} {composant:<20} : {detail}")
    return 0 if tous_ok else 1
