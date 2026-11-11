"""Gestion centralisée et multiplateforme des chemins (XDG / platformdirs / COACH_HOME).

Rétrocompatibilité totale avec l'environnement existant de Tom sur CT 510.
"""
import os
import sys
from pathlib import Path

try:
    import platformdirs
    _USER_CONFIG = Path(platformdirs.user_config_dir("coach-sport"))
    _USER_STATE = Path(platformdirs.user_data_dir("coach-sport")) / "state"
    _USER_LOGS = Path(platformdirs.user_log_dir("coach-sport"))
except ImportError:
    _USER_CONFIG = Path.home() / ".config" / "coach-sport"
    _USER_STATE = Path.home() / ".local" / "state" / "coach-sport"
    _USER_LOGS = _USER_STATE / "logs"


def _safe_exists(p: Path) -> bool:
    try:
        return p.exists()
    except (PermissionError, OSError):
        return False


def _safe_is_dir(p: Path) -> bool:
    try:
        return p.is_dir()
    except (PermissionError, OSError):
        return False


def coach_home() -> Path | None:
    val = os.environ.get("COACH_HOME")
    if val:
        return Path(val)
    return None


def config_dir() -> Path:
    home = coach_home()
    if home and _safe_exists(home / "profile.yaml"):
        return home
    if _safe_exists(Path("/root/.config/coach.env")):
        return Path("/root/.config")
    return _USER_CONFIG


def state_dir() -> Path:
    home = coach_home()
    if home:
        p = home / "state"
        p.mkdir(parents=True, exist_ok=True)
        return p
    if _safe_exists(Path("/root/.local/state")):
        return Path("/root/.local/state")
    _USER_STATE.mkdir(parents=True, exist_ok=True)
    return _USER_STATE


def log_dir() -> Path:
    if _safe_is_dir(Path("/var/log")) and os.access("/var/log", os.W_OK):
        return Path("/var/log")
    _USER_LOGS.mkdir(parents=True, exist_ok=True)
    return _USER_LOGS


def planif_path() -> Path:
    return Path(os.environ.get("COACH_PLANIF", state_dir() / "coach-planif.json"))


def state_path() -> Path:
    return Path(os.environ.get("COACH_STATE", state_dir() / "coach-sport.json"))


def boucles_path() -> Path:
    return Path(os.environ.get("COACH_BOUCLES", state_dir() / "coach-boucles.json"))


def strava_token_path() -> Path:
    return Path(os.environ.get("COACH_STRAVA_TOKEN", state_dir() / "coach-strava-token.json"))


def scope_alert_path() -> Path:
    return Path(os.environ.get("COACH_ALERTE_PORTEE", state_dir() / "coach-sport-scope-alert"))


def gpx_dir() -> Path:
    if "COACH_GPX_DIR" in os.environ:
        return Path(os.environ["COACH_GPX_DIR"])
    home = coach_home()
    if home:
        return home / "boucles"
    if _safe_exists(Path("/root/coach-gpx")):
        return Path("/root/coach-gpx")
    return state_dir() / "gpx"


def backup_dir() -> Path:
    if "COACH_BACKUP_DIR" in os.environ:
        return Path(os.environ["COACH_BACKUP_DIR"])
    home = coach_home()
    if home:
        return home / "backups"
    if _safe_exists(Path("/root/backups/coach")):
        return Path("/root/backups/coach")
    return state_dir() / "backups"


def lock_path() -> Path:
    if "COACH_LOCK" in os.environ:
        return Path(os.environ["COACH_LOCK"])
    if sys.platform != "win32" and _safe_is_dir(Path("/run/lock")) and os.access("/run/lock", os.W_OK):
        return Path("/run/lock/coach-sport.lock")
    return state_dir() / "coach-sport.lock"
