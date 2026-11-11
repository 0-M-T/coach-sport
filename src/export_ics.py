"""Génération de fichiers calendrier iCalendar (.ics, RFC 5545) autonome sans dépendance."""
import datetime as dt
import uuid
from pathlib import Path
from .plan import SEMAINES


def _format_ics_dt(d: dt.date, heure_str: str) -> str:
    h, m = heure_str.split(":")
    return f"{d.strftime('%Y%m%d')}T{int(h):02d}{int(m):02d}00"


def generer_ics(debut: dt.date | None = None, jours: int = 28) -> str:
    debut = debut or dt.date.today()
    fin = debut + dt.timedelta(days=jours)

    lignes = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Coach Sportif//FR",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Entraînements Coach",
    ]

    cur = debut
    while cur <= fin:
        # Trouver le lundi de la semaine
        lundi = cur - dt.timedelta(days=cur.weekday())
        lundi_str = lundi.isoformat()
        seances = [s for s in SEMAINES.get(lundi_str, []) if s.jour == cur.weekday()]

        for s in seances:
            heure_debut = s.prefs[0] if s.prefs else "08:30"
            dt_start = _format_ics_dt(cur, heure_debut)
            h_deb, m_deb = map(int, heure_debut.split(":"))
            duree_min = s.duree or 45
            fin_dt = dt.datetime(cur.year, cur.month, cur.day, h_deb, m_deb) + dt.timedelta(minutes=duree_min)
            dt_end = f"{fin_dt.strftime('%Y%m%d')}T{fin_dt.strftime('%H%M%S')}"

            uid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{cur.isoformat()}-{s.titre}"))
            description = (s.corps or s.titre).replace("\n", "\\n")

            lignes.extend([
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{dt.datetime.now(dt.UTC).strftime('%Y%m%dT%H%M%SZ')}",
                f"DTSTART:{dt_start}",
                f"DTEND:{dt_end}",
                f"SUMMARY:{s.titre}",
                f"DESCRIPTION:{description}",
                "CATEGORIES:Sport,Course",
                "END:VEVENT",
            ])

        cur += dt.timedelta(days=1)

    lignes.append("END:VCALENDAR")
    return "\r\n".join(lignes) + "\r\n"


def exporter_fichier(chemin: Path | str, debut: dt.date | None = None, jours: int = 28) -> Path:
    p = Path(chemin)
    p.parent.mkdir(parents=True, exist_ok=True)
    contenu = generer_ics(debut=debut, jours=jours)
    p.write_text(contenu, encoding="utf-8")
    return p
