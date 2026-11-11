"""Règles du coach (docs/BOUCLE_AUTONOME_COACH.md) : conseil affiché, aucune écriture dans Baïkal."""

HARD = ("seuil", "as21", "semi", "vma", "400m", "piste")
BAD_HRV = {"LOW", "POOR"}   # mauvais à eux seuls ; « UNBALANCED » ne l'est qu'avec un sommeil court (rejeu du 2026-11-09 : 46 % de jours
                            # jugés fatigués si UNBALANCED suffisait, dont six jours de suite avec 8 à 9 h de sommeil)


def signaux(forme: dict | None) -> list[str]:
    """Signaux de fatigue plus fins que le sommeil et le statut de VFC (mesurés sur 45 jours de l'historique de Tom, voir rejeu).

    Chacun seul ne prouve rien ; deux ensemble, oui.
    """
    f = forme or {}
    out = []
    bb, sh = f.get("bb_wake"), f.get("sleep_hours")
    if bb is not None and bb < 65 and (sh or 0) >= 7:
        out.append(f"Body Battery {bb} au réveil malgré {sh:.0f} h de sommeil")
    fr, f7 = f.get("fc_repos"), f.get("fc_repos_7j")
    if fr and f7 and fr - f7 >= 3:
        out.append(f"FC au repos {fr} bpm ({fr - f7:+d} sur sa moyenne de 7 jours)")
    hn, hb = f.get("hrv_nuit"), f.get("hrv_bas")
    if hn and hb and hn < hb:
        out.append(f"VFC de la nuit {hn} ms sous la zone équilibrée ({hb} ms)")
    ch = f.get("charge_veille")
    if ch and ch >= 150:
        out.append(f"grosse séance hier (charge {ch:.0f})")
    return out


def fatigue(sleep_hours, hrv_status, forme: dict | None = None) -> bool:
    """Sommeil sous 6 h 30, VFC basse ou faible, VFC déséquilibrée avec un sommeil sous 7 h, ou au moins deux signaux fins (Body Battery au réveil,
    FC au repos, VFC sous la zone, charge de la veille)."""
    h = (hrv_status or "").upper()
    return ((sleep_hours is not None and sleep_hours < 6.5) or h in BAD_HRV
            or (h == "UNBALANCED" and sleep_hours is not None and sleep_hours < 7.0)
            or len(signaux(forme)) >= 2)


def conseil(seance: str | None, sleep_hours, hrv_status, wind, precip, forme: dict | None = None) -> list[str]:
    s = (seance or "").lower()
    out: list[str] = []
    if fatigue(sleep_hours, hrv_status, forme) and any(k in s for k in HARD):
        raisons = signaux(forme)
        motif = ", ".join(raisons) if len(raisons) >= 2 else "sommeil < 6h30, VFC basse, ou VFC déséquilibrée avec sommeil < 7h"
        out.append(f"Récupération insuffisante ({motif}) : remplacer la séance dure par un footing EF (5'15-5'35, FC < 145) ou du repos.")
    if (wind or 0) > 30 or (precip or 0) > 1:
        if any(k in s for k in ("vélo", "velo", "route")) and "cap" not in s:
            out.append("Pluie ou rafales > 30 km/h : vélo route en home trainer, VTT ou renfo.")
        else:
            out.append("Pluie ou vent fort : adapter l'échauffement, prévoir une couche coupe-vent.")
    return out


def conseil_sans_donnees(seance: str | None) -> list[str]:
    """Montre non portée la nuit : forme inconnue, on n'invente rien."""
    if any(k in (seance or "").lower() for k in HARD):
        return ["Forme inconnue (pas de données de la nuit) : l'échauffement décide. Si les jambes sont lourdes "
                "à la fin, bascule en footing d'endurance (5'15-5'35, FC sous 145)."]
    return []


def fc_repos_elevee(historique: dict[str, int], jour: str, jours: int = 3, ecart: int = 4) -> str | None:
    """FC au repos au moins `ecart` bpm au-dessus de sa moyenne des 30 jours précédents, `jours` jours de suite jusqu'à `jour` inclus.

    Un jour isolé ne dit rien (une grosse séance la veille suffit) ; trois de suite, c'est une fatigue qui s'installe.
    Moyenne de référence sur au moins 14 mesures, sans les jours examinés."""
    import datetime as dt
    j = dt.date.fromisoformat(jour)
    recents = [historique.get((j - dt.timedelta(days=i)).isoformat()) for i in range(jours)]
    base = [v for d, v in historique.items() if (j - dt.timedelta(days=jours + 30)).isoformat() <= d < (j - dt.timedelta(days=jours - 1)).isoformat()]
    if None in recents or len(base) < 14:
        return None
    moy = sum(base) / len(base)
    if all(v >= moy + ecart for v in recents):
        return (f"FC au repos haute {jours} jours de suite ({', '.join(str(v) for v in reversed(recents))} bpm contre {moy:.0f} en moyenne) : "
                "fatigue qui s'installe, garde les séances faciles vraiment faciles et dors plus")
    return None
