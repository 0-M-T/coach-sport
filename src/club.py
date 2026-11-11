"""Séances club reconnues par leur lieu : départ à moins de 500 m du stade, avec d'autres athlètes."""
import datetime as dt
import math
import statistics
from .profil import charger_profil

_p = charger_profil()
STADE = _p.club_stade   # Coordonnées du stade
RAYON_M = 500


def distance_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    p = math.pi / 180
    h = math.sin((b[0] - a[0]) * p / 2) ** 2 + math.cos(a[0] * p) * math.cos(b[0] * p) * math.sin((b[1] - a[1]) * p / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


def au_club(act: dict) -> bool:
    """Départ au stade avec au moins un autre athlète, mardi ou jeudi 17 h à 19 h 30, samedi ou dimanche matin."""
    if not charger_profil().club_actif:
        return False
    ll = act.get("start_latlng")
    if not ll or act.get("athlete_count", 1) < 2 or distance_m(STADE, ll) > RAYON_M:
        return False
    d = dt.datetime.fromisoformat(act["start_date_local"][:19])
    h = d.hour + d.minute / 60
    return (d.weekday() in (1, 3) and 17 <= h <= 19.5) or (d.weekday() in (5, 6) and 8 <= h <= 12)


def est_fractionne(laps: list[dict]) -> bool:
    """Au moins 3 tours plus rapides de 40 s/km que les tours lents (3e quartile) : fractionné plutôt que footing."""
    allures = [l["moving_time"] / (l["distance"] / 1000) for l in laps if l.get("distance", 0) >= 150 and l.get("moving_time", 0) > 0]
    if len(allures) < 6:
        return False
    lent = statistics.quantiles(allures, n=4)[2]
    return sum(1 for a in allures if a <= lent - 40) >= 3
