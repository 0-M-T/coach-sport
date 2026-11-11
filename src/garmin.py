import datetime as dt
import sys

from garminconnect import Garmin

from .config import load_config


_SESSIONS: dict[str, "Garmin | Exception"] = {}


def client(conf: dict[str, str] | None = None) -> Garmin:
    """Client Garmin connecté, une seule connexion par processus (un passage de cron) : Garmin bloque les comptes qui se connectent trop.

    Un échec est gardé aussi : les sources suivantes du même passage ne retentent pas la connexion."""
    conf = load_config() if conf is None else conf
    tokens = conf.get("GARMIN_TOKENS", "/root/.config/garmin_tokens.json")
    s = _SESSIONS.get(tokens)
    if s is None:
        try:
            s = Garmin(conf.get("GARMIN_EMAIL"), conf.get("GARMIN_PASS"))
            s.login(tokens)
        except Exception as e:
            s = e
        _SESSIONS[tokens] = s
    if isinstance(s, Exception):
        raise s
    return s


def fc_nuit_matin(c: Garmin, day: str) -> tuple[int, int]:
    """Nombre de mesures de FC entre 0 h et 5 h, puis après 5 h (heure de Paris). Portée la nuit : ~150 mesures la nuit."""
    import datetime as dt
    from zoneinfo import ZoneInfo
    paris = ZoneInfo("Europe/Paris")
    vals = [x for x in ((c.get_heart_rates(day) or {}).get("heartRateValues") or []) if x and x[1]]
    heures = [dt.datetime.fromtimestamp(x[0] / 1000, paris).hour for x in vals]
    return sum(h < 5 for h in heures), sum(h >= 5 for h in heures)


def forme(c: Garmin, day: str, charges: dict | None = None, avec_charge: bool = True) -> dict:
    """Body Battery, sommeil (score et heures), statut VFC. Une clé absente vaut None, jamais 'N/A'."""
    stats = c.get_user_summary(day) or {}
    sleep = (c.get_sleep_data(day) or {}).get("dailySleepDTO", {}) or {}
    hrv = (c.get_hrv_data(day) or {}).get("hrvSummary", {}) or {}
    secs = sleep.get("sleepTimeSeconds")
    charge_veille = None
    if charges is not None:   # charges déjà lues pour une période (rejeu) : pas d'appel par jour
        charge_veille = charges.get((dt.date.fromisoformat(day) - dt.timedelta(days=1)).isoformat(), 0)
    elif avec_charge:
        try:
            veille = (dt.date.fromisoformat(day) - dt.timedelta(days=1)).isoformat()
            charge_veille = sum(a.get("activityTrainingLoad") or 0 for a in (c.get_activities_by_date(veille, veille) or []))
        except Exception as e:  # signal fin facultatif : on continue, mais on le dit
            print(f"[GARMIN] charge de la veille indisponible : {e}", file=sys.stderr)
    fc_nuit = fc_matin = None
    if not secs:  # sans sommeil : la FC de nuit dit si la montre était portée
        try:
            fc_nuit, fc_matin = fc_nuit_matin(c, day)
        except Exception as e:
            print(f"[GARMIN] FC de la nuit indisponible : {e}", file=sys.stderr)
    return {
        "fc_nuit": fc_nuit, "fc_matin": fc_matin,
        "bb_wake": stats.get("bodyBatteryAtWakeTime"), "fc_repos": stats.get("restingHeartRate"),
        "fc_repos_7j": stats.get("lastSevenDaysAvgRestingHeartRate"),
        "hrv_nuit": hrv.get("lastNightAvg"), "hrv_bas": (hrv.get("baseline") or {}).get("balancedLow"),
        "charge_veille": charge_veille,
        "sleep_date": sleep.get("calendarDate"),
        "body_battery": stats.get("bodyBatteryMostRecentValue"),
        "sleep_score": ((sleep.get("sleepScores") or {}).get("overall") or {}).get("value"),
        "sleep_hours": round(secs / 3600, 2) if secs else None,
        "hrv_status": hrv.get("status"),
    }


def nuit_prete(c: Garmin, day: str) -> bool:
    """Un seul appel : le score de sommeil du jour existe-t-il ? (évite 2 appels et la météo à chaque passage du réveil)"""
    sleep = (c.get_sleep_data(day) or {}).get("dailySleepDTO", {}) or {}
    return bool(sleep.get("sleepTimeSeconds")) and ((sleep.get("sleepScores") or {}).get("overall") or {}).get("value") is not None \
        and sleep.get("calendarDate") in (None, day)


def seuil(c: Garmin) -> dict | None:
    """Dernier seuil lactique détecté par Garmin : FC, allure (s/km), date. Garmin donne la vitesse en dizaines de m/s."""
    s = (c.get_lactate_threshold(latest=True) or {}).get("speed_and_heart_rate") or {}
    if not s.get("heartRate"):
        return None
    v = (s.get("speed") or 0) * 10
    return {"fc": int(s["heartRate"]), "allure": round(1000 / v) if v else None, "date": (s.get("calendarDate") or "")[:10]}
