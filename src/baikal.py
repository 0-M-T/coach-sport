import re
import subprocess

from .config import baikal_cmd


def lister(date: str, end: str | None = None, cal: str = "Sport", fins: bool = False) -> list[str]:
    """Événements du calendrier Baïkal. Lève une erreur au lieu de renvoyer une liste vide."""
    res = subprocess.run([baikal_cmd(), "lister", date, end or date, "-c", cal] + (["--fins"] if fins else []),
                         capture_output=True, text=True, timeout=60)
    if res.returncode != 0:
        raise RuntimeError(f"baikal-event lister a échoué ({res.returncode}) : {res.stderr.strip()[:200]}")
    return [l for l in res.stdout.splitlines() if l.strip() and "aucun" not in l.lower()]


_EV = re.compile(r"^(?P<date>\d{4}-\d{2}-\d{2})\s+(?P<heure>\d{2}:\d{2}|journée)(?:→(?P<fin>\d{2}:\d{2}))?\s+\[(?P<cal>[^\]]+)\]\s+(?P<titre>.+?)(?:\s+@\s+(?P<lieu>.+?))?(?:\s+—\s+\S+)?$")


def court(ligne: str) -> str:
    """'2026-11-09 07:30  [Sport] CAP: Seuil @ Route  — uid.ics' -> '07:30 CAP: Seuil (Route)'."""
    m = _EV.match(ligne.strip())
    if not m:
        return ligne
    return f"{m['heure']} {m['titre']}" + (f" ({m['lieu']})" if m["lieu"] else "")


def lieu(ligne: str) -> str | None:
    m = _EV.match(ligne.strip())
    return m["lieu"] if m else None


def debut(ligne: str) -> tuple[str, str] | None:
    m = _EV.match(ligne.strip())
    return (m["date"], m["heure"]) if m else None


def ident(ligne: str) -> str | None:
    m = re.search(r"—\s+(\S+)$", ligne.strip())
    return m[1] if m else None


def deplacer(ident_: str, debut_iso: str, fin_iso: str) -> None:
    res = subprocess.run([baikal_cmd(), "modifier", ident_, "--debut", debut_iso, "--fin", fin_iso],
                         capture_output=True, text=True, timeout=60)
    if res.returncode != 0:
        raise RuntimeError(f"baikal-event modifier a échoué ({res.returncode}) : {(res.stderr or res.stdout).strip()[:200]}")


def parse(ligne: str) -> dict | None:
    m = _EV.match(ligne.strip())
    if not m:
        return None
    return {"date": m["date"], "heure": m["heure"], "fin": m["fin"], "cal": m["cal"], "titre": m["titre"], "lieu": m["lieu"], "id": ident(ligne)}


def creer(name: str, start: str, end: str, desc: str, url: str | None = None, cal: str = "Sport", categorie: str | None = None,
          html: str | None = None) -> str:
    """Crée l'événement et renvoie son identifiant (nom du fichier .ics). `html` : version HTML de la description (Thunderbird)."""
    cmd = [baikal_cmd(), "ajouter", name, start, end, "-c", cal, "--description", desc] + (["--html", html] if html else [])
    if url:
        cmd += ["--url", url]
    if categorie:
        cmd += ["--categorie", categorie]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if res.returncode != 0:
        raise RuntimeError(f"baikal-event création a échoué : {(res.stderr or res.stdout).strip()[:200]}")
    m = re.search(r"\(([^()\s]+\.ics)\)", res.stdout)
    if not m:
        raise RuntimeError(f"identifiant introuvable dans : {res.stdout.strip()[:200]}")
    return m[1]


def modifier(ident_: str, **champs) -> None:
    cmd = [baikal_cmd(), "modifier", ident_]
    for k, v in champs.items():
        cmd += [f"--{k}", v]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if res.returncode != 0:
        raise RuntimeError(f"baikal-event modifier a échoué : {(res.stderr or res.stdout).strip()[:200]}")


def supprimer(ident_: str) -> None:
    res = subprocess.run([baikal_cmd(), "supprimer", ident_], capture_output=True, text=True, timeout=60)
    if res.returncode != 0:
        raise RuntimeError(f"baikal-event supprimer a échoué : {(res.stderr or res.stdout).strip()[:200]}")
