"""Briefings du jour de course et bilan : semi-marathon Lourdes-Tarbes (point à point de 21,1 km, objectif 1 h 34)."""
import datetime as dt

from . import meteo, texte

LOURDES = (43.0942, -0.0456)       # départ place Capdevielle
OBJECTIF_S = 94 * 60               # 1 h 34 min 00
CIBLE_S = 265                      # 4'25/km
DISTANCE_KM = 21.0975
DEPART_DEFAUT = "09:00"


def fmt_chrono(s: float) -> str:
    s = round(s)
    return f"{s // 3600} h {s % 3600 // 60:02d} min {s % 60:02d} s"


def fmt_ecart(s: float) -> str:
    """Écart court sans heures : « 30 s », « 1 min 05 s » (fmt_chrono donnait « 0 30 s » après nettoyage)."""
    s = round(abs(s))
    return f"{s // 60} min {s % 60:02d} s" if s >= 60 else f"{s} s"


def pace(s: float) -> str:
    return f"{int(s // 60)}'{int(s % 60):02d}"


def repere_5km() -> list[str]:
    """Temps de passage à 4'25/km tous les 5 km et à l'arrivée."""
    out = [f"{k} km : {fmt_chrono(k * CIBLE_S)}" for k in (5, 10, 15, 20)]
    out.append(f"Arrivée : {fmt_chrono(DISTANCE_KM * CIBLE_S)} (objectif : moins de {fmt_chrono(OBJECTIF_S)}, soit 4'27/km de moyenne)")
    return out


def heure_moins(depart: str, minutes: int) -> str:
    h, m = map(int, depart.split(":"))
    t = (h * 60 + m - minutes) % 1440
    return f"{t // 60:02d}:{t % 60:02d}"


def message_veille(w_demain: dict | None, depart: str = DEPART_DEFAUT) -> str:
    conseils = meteo.conseils(w_demain) if w_demain else None
    return texte.message(
        texte.bloc("Demain : Lourdes-Tarbes", f"Départ à {depart}, place Capdevielle à Lourdes. Objectif : moins de 1 h 34 (4'27/km), cible 4'25/km."),
        texte.bloc("À préparer ce soir", ["Dossard, épingles, puce", "Chaussures de course (ASICS MetaSpeed Sky Paris), tenue, gels, pâtes de fruits",
                                          "Repas riche en glucides, peu de fibres, pas de gras", "Eau riche en magnésium, 2,5 L sur la journée",
                                          f"Réveil à {heure_moins(depart, 195)}, coucher à 22 h 30"], puces=True),
        texte.bloc("Météo à prévoir", meteo.resume(w_demain) if w_demain else None),
        texte.bloc("Tenue", conseils, puces=True),
        texte.bloc("Ce soir", "Rien de nouveau : mêmes aliments, mêmes chaussures, mêmes vêtements que les séances."))


def message_jour_j(w: dict | None, depart: str = DEPART_DEFAUT, forme: dict | None = None) -> str:
    forme = forme or {}
    return texte.message(
        texte.bloc("Départ", f"{depart}, Lourdes place Capdevielle, arrivée à Tarbes. Moins de 1 h 34 : 4'27/km de moyenne, cible 4'25/km."),
        texte.bloc("Météo", meteo.resume(w) if w else None),
        texte.bloc("Tenue", meteo.conseils(w) if w else None, puces=True),
        texte.bloc("Réveil et repas", [f"{heure_moins(depart, 195)} : réveil, petit-déjeuner (gâteau énergétique ou pain blanc, miel, compote, thé ou eau, pas de café, ni laitage ni gras)",
                                       f"{heure_moins(depart, 45)} : arrivée sur place, dossard, toilettes",
                                       f"{heure_moins(depart, 30)} : gorgées d'eau",
                                       f"{heure_moins(depart, 15)} : 1 pâte de fruits"], puces=True),
        texte.bloc("Échauffement", [f"{heure_moins(depart, 25)} : 10 à 15 min de footing très souple, gammes, 3 accélérations progressives",
                                    "Ne pas partir plus vite qu'à l'entraînement"], puces=True),
        texte.bloc("Allures", ["Km 1 à 3 : 4'30 (faux-plats de Lourdes), ne pas s'enflammer", "Ensuite : 4'22 à 4'25, régulier, faux-plat descendant",
                               "Km 16, Juillan : relance, sans forcer avant"] + repere_5km(), puces=True),
        texte.bloc("Ravitaillement", ["Eau : 1 à 2 gorgées à chaque poste (km 5, 10, 15), sans attendre la soif",
                                      "Km 7 : 1 gel (20 à 25 g de glucides) et 2 à 3 gorgées d'eau", "Km 14, avant Juillan : 1 gel sans caféine (tu ne bois pas de café) et de l'eau"], puces=True),
        texte.bloc("Forme", f"Sommeil {forme.get('sleep_score') or 'n/d'}/100, batterie corporelle {forme.get('body_battery') or 'n/d'}/100"
                   if forme else None))


def est_course(act: dict, date_course: dt.date) -> bool:
    return (act["start_date_local"][:10] == date_course.isoformat() and 20000 <= act["distance"] <= 23000
            and act.get("sport_type", act.get("type")) in ("Run", "TrailRun"))


def bilan(act: dict, laps: list[dict]) -> tuple[str, str]:
    """(titre, corps) du débrief de la course : chrono contre objectif, passages tous les 5 km, FC."""
    t = act.get("elapsed_time") or act["moving_time"]
    moyenne = t / (act["distance"] / 1000)
    ecart = t - OBJECTIF_S
    passages, cumul_d, cumul_t, prochain = [], 0.0, 0.0, 5000
    for l in laps:
        cumul_d += l.get("distance", 0)
        cumul_t += l.get("elapsed_time") or l.get("moving_time", 0)
        while cumul_d >= prochain and prochain <= 20000:
            passages.append(f"{prochain // 1000} km : {fmt_chrono(cumul_t)}")
            prochain += 5000
    verdict = f"Objectif atteint : {fmt_ecart(ecart)} sous 1 h 34" if ecart <= 0 else f"Objectif manqué de {fmt_ecart(ecart)}"
    lignes = [f"{fmt_chrono(t)} sur {act['distance'] / 1000:.2f} km, allure moyenne {pace(moyenne)}/km", verdict]
    if act.get("average_heartrate"):
        lignes.append(f"FC moyenne {int(act['average_heartrate'])} bpm" + (f", maximale {int(act['max_heartrate'])} bpm" if act.get("max_heartrate") else ""))
    reco = ["Trois jours faciles : marche, vélo très souple, étirements D3", "Repas complet et hydratation dans l'heure", "Reprise du plan lundi (semaine de récupération)"]
    return ("Semi de Lourdes-Tarbes : bilan",
            texte.message(texte.bloc("Résultat", lignes), texte.bloc("Passages", passages, puces=True), texte.bloc("Récupération", reco, puces=True)))
