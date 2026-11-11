"""Sauvegarde quotidienne des fichiers du coach (état, configuration, jetons, crontab) : un restore sans restaurer tout le CT."""
import datetime as dt
import os
import subprocess
import tarfile
from pathlib import Path

DEST = Path(os.environ.get("COACH_BACKUP_DIR", "/root/backups/coach"))
FICHIERS = ["/root/.config/coach.env", "/root/.config/garmin_tokens.json", "/root/.config/baikal-agent.env", "/etc/nftables.conf"]
GARDER = 14


def sauvegarder(maintenant: dt.datetime | None = None, state_dir: Path = Path("/root/.local/state")) -> Path:
    maintenant = maintenant or dt.datetime.now()
    DEST.mkdir(parents=True, exist_ok=True)
    DEST.chmod(0o700)
    cible = DEST / f"coach-{maintenant:%Y%m%d}.tar.gz"
    cron = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
    with tarfile.open(cible, "w:gz") as t:
        for f in sorted(state_dir.glob("coach-*")) + [Path(x) for x in FICHIERS]:
            if f.is_file():
                t.add(f, arcname=str(f).lstrip("/"))
        tmp = DEST / "crontab.tmp"
        tmp.write_text(cron)
        t.add(tmp, arcname="crontab.txt")
        tmp.unlink()
    cible.chmod(0o600)
    for ancien in sorted(DEST.glob("coach-*.tar.gz"))[:-GARDER]:
        ancien.unlink()
    return cible
