"""Ré-autorisation Strava avec activity:write. Usage : coach.py strava-auth [--code CODE]."""
import json
import re
import urllib.parse
import urllib.request

from .config import ecrire_atomique, env_file, load_config

REDIRECT = "http://localhost/exchange_token"


def run(code: str | None = None) -> None:
    conf = load_config()
    if code and "code=" in code:  # l'utilisateur peut coller l'URL entière de la page d'erreur
        q = urllib.parse.parse_qs(urllib.parse.urlparse(code).query)
        assert "activity:write" in q.get("scope", [""])[0], \
            "activity:write non accordé : la case était décochée sur Strava, recommencer"
        code = q["code"][0]
    if not code:
        q = urllib.parse.urlencode({"client_id": conf["STRAVA_CLIENT_ID"], "response_type": "code",
                                    "redirect_uri": REDIRECT, "approval_prompt": "force",
                                    "scope": "read,activity:read_all,activity:write"})
        print(f"1. Ouvre : https://www.strava.com/oauth/authorize?{q}\n"
              "2. Accepte, puis copie le paramètre code= de l'URL où tu atterris (page d'erreur normale).\n"
              "3. Relance : coach.py strava-auth --code <code>")
        return
    data = urllib.parse.urlencode({"client_id": conf["STRAVA_CLIENT_ID"], "client_secret": conf["STRAVA_CLIENT_SECRET"],
                                   "code": code, "grant_type": "authorization_code"}).encode()
    with urllib.request.urlopen(urllib.request.Request("https://www.strava.com/oauth/token", data=data), timeout=10) as r:
        tok = json.loads(r.read())
    path = env_file()
    txt = path.read_text(encoding="utf-8")
    out = re.sub(r"(?m)^STRAVA_REFRESH_TOKEN=.*$", f"STRAVA_REFRESH_TOKEN={tok['refresh_token']}", txt)
    assert out != txt, "STRAVA_REFRESH_TOKEN inchangé : fichier env inattendu"
    ecrire_atomique(path, out)
    from .strava import CACHE
    CACHE.unlink(missing_ok=True)  # l'ancien jeton n'a pas le nouveau scope
    print("Refresh token mis à jour (scope activity:write).")
