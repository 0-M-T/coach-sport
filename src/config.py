import json
import os
import shutil
import sys
import time
from pathlib import Path
from . import chemins

DEFAULT_ENV_PATHS = [
    Path(os.environ.get("COACH_ENV", "")),
    chemins.config_dir() / "coach.env",
    Path("/root/.config/coach.env"),
    Path(__file__).resolve().parent.parent / ".env",
    Path.home() / ".config/coach.env",
]

# Identifiants agent-jarvis partagés avec baikal-event : un seul fichier à changer lors d'une rotation.
BAIKAL_ENV = Path(os.environ.get("BAIKAL_ENV", "/root/.config/baikal-agent.env"))

PREFIXES = ("NTFY_", "GARMIN_", "STRAVA_", "HA_", "BAIKAL_", "CALDAV_", "COACH_")
HA_URL_DEFAUT = os.environ.get("HA_URL", "http://192.168.1.15:8123")
BAIKAL_WEB = os.environ.get("BAIKAL_URL", "https://baikal.homelab.lan/")


def env_file() -> Path | None:
    for path in DEFAULT_ENV_PATHS:
        try:
            if path and path.is_file():
                return path
        except (PermissionError, OSError):
            continue
    return None


def load_config() -> dict[str, str]:
    conf: dict[str, str] = {}
    for path in (env_file(), BAIKAL_ENV):
        if path and path.is_file():
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        conf[k.strip()] = v.strip().strip("'\"")
    for key, val in os.environ.items():
        if key.startswith(PREFIXES):
            conf[key] = val
    return conf


def race_date(conf: dict[str, str]):
    import datetime as dt
    return dt.date.fromisoformat(conf.get("COACH_RACE_DATE", "2026-11-29"))


def baikal_cmd() -> str:
    """Chemin absolu de baikal-event : le PATH de cron ne contient pas /usr/local/bin partout."""
    for cand in ("/usr/local/bin/baikal-event", shutil.which("baikal-event")):
        if cand and os.path.exists(cand):
            return cand
    raise FileNotFoundError("baikal-event introuvable (attendu : /usr/local/bin/baikal-event)")


def ecrire_atomique(path: Path, texte: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with os.fdopen(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as f:
        f.write(texte)
    if path.exists():
        tmp.chmod(path.stat().st_mode & 0o777)
    tmp.replace(path)


def ecrire_json(path: Path, data) -> None:
    ecrire_atomique(path, json.dumps(data, ensure_ascii=False, indent=1))


def verrou(chemin: str | None = None, attente_s: float = 300):
    """Verrou exclusif multiplateforme (POSIX fcntl ou fallback exclusif Windows)."""
    target = Path(chemin) if chemin else chemins.lock_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    fin = time.monotonic() + attente_s

    if sys.platform != "win32":
        import fcntl
        f = open(target, "a")  # noqa: SIM115
        while True:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return f
            except BlockingIOError:
                if time.monotonic() >= fin:
                    f.close()
                    raise TimeoutError(f"verrou {target} tenu depuis plus de {attente_s:.0f} s") from None
                time.sleep(1)
    else:
        # Windows fallback locking
        import msvcrt
        f = open(target, "a+")  # noqa: SIM115
        while True:
            try:
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                return f
            except (OSError, PermissionError):
                if time.monotonic() >= fin:
                    f.close()
                    raise TimeoutError(f"verrou {target} tenu depuis plus de {attente_s:.0f} s") from None
                time.sleep(1)
