"""Client API Intervals.icu pour coureurs équipés de montres Coros, Suunto, Polar ou Wahoo.

API REST ouverte : https://intervals.icu/api/v1/
Authentification : Basic Auth avec utilisateur 'API_KEY' et la clé comme mot de passe.
"""
import base64
import json
import urllib.error
import urllib.request
from typing import Any

API_BASE = "https://intervals.icu/api/v1"


def _headers(api_key: str) -> dict[str, str]:
    auth = base64.b64encode(f"API_KEY:{api_key}".encode()).decode()
    return {
        "Authorization": f"Basic {auth}",
        "User-Agent": "Coach-Sport/1.0",
        "Accept": "application/json",
    }


def verifier_connexion(athlete_id: str, api_key: str) -> tuple[bool, str]:
    """Vérifie l'accès au compte Intervals.icu."""
    url = f"{API_BASE}/athlete/{athlete_id}"
    req = urllib.request.Request(url, headers=_headers(api_key))
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            nom = data.get("name") or data.get("firstname") or athlete_id
            return True, f"Connecté : {nom}"
    except urllib.error.HTTPError as e:
        return False, f"Erreur HTTP {e.code}"
    except Exception as e:
        return False, str(e)


def wellness(athlete_id: str, api_key: str, date_iso: str) -> dict[str, Any] | None:
    """Récupère les métriques de forme (VFC/HRV, FC repos, sommeil) à une date."""
    url = f"{API_BASE}/athlete/{athlete_id}/wellness/{date_iso}"
    req = urllib.request.Request(url, headers=_headers(api_key))
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return None


def forme(athlete_id: str, api_key: str, date_iso: str) -> dict[str, Any] | None:
    """Convertit le wellness Intervals.icu au format standard du noyau coach."""
    w = wellness(athlete_id, api_key, date_iso)
    if not w:
        return None

    sleep_secs = w.get("sleepSecs") or 0
    sleep_hours = round(sleep_secs / 3600.0, 2)
    hrv = w.get("hrv")  # rMSSD
    resting_hr = w.get("restingHR")

    return {
        "source": "intervals",
        "date": date_iso,
        "sleep_hours": sleep_hours,
        "hrv": hrv,
        "resting_hr": resting_hr,
        "fatigue_score": w.get("fatigue"),
        "soreness": w.get("soreness"),
    }


def activites(athlete_id: str, api_key: str, debut_iso: str, fin_iso: str) -> list[dict[str, Any]]:
    """Récupère les activités d'une période."""
    url = f"{API_BASE}/athlete/{athlete_id}/activities?oldest={debut_iso}&newest={fin_iso}"
    req = urllib.request.Request(url, headers=_headers(api_key))
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return []
