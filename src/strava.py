import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from . import chemins
from .config import ecrire_atomique, env_file

API = "https://www.strava.com/api/v3"


class QuotaError(RuntimeError):
    """Quota Strava atteint (100 requêtes par 15 min, 1000 par jour) : réessayer plus tard."""


class ScopeError(RuntimeError):
    """Le jeton n'a pas activity:write : il faut ré-autoriser l'application."""


def _persist_refresh(new: str) -> None:
    path = env_file()
    if not path:
        return
    txt = path.read_text(encoding="utf-8")
    out = re.sub(r"(?m)^STRAVA_REFRESH_TOKEN=.*$", f"STRAVA_REFRESH_TOKEN={new}", txt)
    assert out != txt or f"STRAVA_REFRESH_TOKEN={new}" in txt, "STRAVA_REFRESH_TOKEN absent du fichier env"
    ecrire_atomique(path, out)


CACHE = chemins.strava_token_path()


def token(conf: dict[str, str]) -> str:
    """Jeton d'accès mis en cache jusqu'à 5 min avant expiration (6 h) : une requête OAuth de moins par passage."""
    try:
        c = json.loads(CACHE.read_text())
        if c["expires_at"] - time.time() > 300 and c.get("refresh") == conf.get("STRAVA_REFRESH_TOKEN"):
            return c["access"]
    except (OSError, ValueError, KeyError):
        pass
    tok = _renouveler(conf)
    ecrire_atomique(CACHE, json.dumps({"access": tok["access_token"], "expires_at": tok["expires_at"],
                                       "refresh": tok.get("refresh_token", conf["STRAVA_REFRESH_TOKEN"])}))
    return tok["access_token"]


def _renouveler(conf: dict[str, str]) -> dict:
    for k in ("STRAVA_CLIENT_ID", "STRAVA_CLIENT_SECRET", "STRAVA_REFRESH_TOKEN"):
        if not conf.get(k):
            raise ValueError(f"{k} manquant")
    data = urllib.parse.urlencode({
        "client_id": conf["STRAVA_CLIENT_ID"], "client_secret": conf["STRAVA_CLIENT_SECRET"],
        "grant_type": "refresh_token", "refresh_token": conf["STRAVA_REFRESH_TOKEN"],
    }).encode()
    with urllib.request.urlopen(urllib.request.Request(f"{API.rsplit('/api', 1)[0]}/oauth/token", data=data), timeout=10) as r:
        tok = json.loads(r.read())
    if tok.get("refresh_token") and tok["refresh_token"] != conf["STRAVA_REFRESH_TOKEN"]:
        _persist_refresh(tok["refresh_token"])  # Strava peut faire tourner le refresh token
    return tok


def call(access: str, path: str, method: str = "GET", body: dict | None = None):
    req = urllib.request.Request(
        f"{API}{path}", method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {access}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise QuotaError("quota Strava atteint, réessayer dans 15 minutes") from e
        if method != "GET" and e.code in (401, 403):
            raise ScopeError("Strava refuse l'écriture : ré-autoriser avec activity:write "
                             "(python3 coach.py strava-auth)") from e
        raise


def activities(access: str, per_page: int = 10, after: int | None = None) -> list[dict]:
    q = f"?per_page={per_page}" + (f"&after={after}" if after else "")
    return call(access, f"/athlete/activities{q}")


def pace(distance_m: float, seconds: float) -> str:
    if distance_m <= 0:
        return "N/A"
    s = seconds / (distance_m / 1000)
    return f"{int(s // 60)}'{int(s % 60):02d}"
