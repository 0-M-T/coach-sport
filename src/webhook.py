"""Récepteur du webhook Strava (push_subscriptions).

Strava ne signe pas ses appels : le chemin contient un secret, seul l'athlète de Tom est accepté, et un appel ne fait
que déclencher un passage de strava-enrich (qui relit tout via l'API). Un faux appel ne peut donc rien écrire.
"""
import hmac
import json
import os
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .config import load_config

VERROU = threading.Lock()
DELAI_S = 30  # laisser Strava finir de recevoir tours et capteurs avant de lire l'activité


def traiter(methode: str, url: str, corps: bytes, conf: dict) -> tuple[int, dict, bool]:
    """Renvoie (code HTTP, JSON de réponse, déclencher ?). Pur : testable sans réseau."""
    u = urlparse(url)
    secret = conf.get("STRAVA_WEBHOOK_SECRET", "")
    if not secret or not hmac.compare_digest(u.path.encode(), f"/strava/{secret}".encode()):  # bytes : un chemin non ASCII ne lève pas
        return 404, {}, False
    if methode == "GET":
        q = parse_qs(u.query)
        verify = conf.get("STRAVA_WEBHOOK_VERIFY", "")
        if q.get("hub.mode") == ["subscribe"] and verify and hmac.compare_digest(q.get("hub.verify_token", [""])[0].encode(), verify.encode()):
            return 200, {"hub.challenge": q.get("hub.challenge", [""])[0]}, False
        return 403, {}, False
    if methode == "POST":
        try:
            ev = json.loads(corps or b"{}")
        except ValueError:
            return 400, {}, False
        ok = (ev.get("object_type") == "activity" and str(ev.get("owner_id")) == conf.get("STRAVA_ATHLETE_ID", "141445394")
              and ev.get("aspect_type") in ("create", "update"))
        return 200, {}, ok  # toujours 200 : Strava réessaie sinon
    return 405, {}, False


def declencher() -> None:
    """Un passage de strava-enrich, après un délai, jamais deux en parallèle."""
    if not VERROU.acquire(blocking=False):
        return  # un passage est déjà en cours ou en attente : il verra aussi cet événement
    def _run():
        try:
            time.sleep(DELAI_S)
            subprocess.run(["/usr/local/bin/strava-enrich"], timeout=300)
        finally:
            VERROU.release()
    threading.Thread(target=_run, daemon=True).start()


class Handler(BaseHTTPRequestHandler):
    conf: dict = {}

    def _repondre(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        corps = self.rfile.read(max(0, min(n, 65536)))  # négatif : read(-1) attendrait la fin de la connexion
        code, rep, go = traiter(self.command, self.path, corps, self.conf)
        data = json.dumps(rep).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        if go:
            declencher()

    do_GET = do_POST = do_PUT = do_DELETE = _repondre

    def log_message(self, fmt, *args):  # jamais le chemin : il contient le secret
        print(f"webhook {self.command} -> {args[1] if len(args) > 1 else ''}", flush=True)


def servir() -> None:
    Handler.conf = load_config()
    port = int(os.environ.get("COACH_WEBHOOK_PORT", "8787"))
    ThreadingHTTPServer((os.environ.get("COACH_WEBHOOK_BIND", "0.0.0.0"), port), Handler).serve_forever()


def abonnement(action: str, url: str | None = None) -> None:
    """Gère l'abonnement Strava (un seul par application) : --voir, --creer URL, --supprimer."""
    import urllib.parse
    import urllib.request
    conf = load_config()
    base = "https://www.strava.com/api/v3/push_subscriptions"
    ident = {"client_id": conf["STRAVA_CLIENT_ID"], "client_secret": conf["STRAVA_CLIENT_SECRET"]}
    if action == "voir":
        with urllib.request.urlopen(f"{base}?{urllib.parse.urlencode(ident)}", timeout=15) as r:
            print(r.read().decode())
    elif action == "creer":
        data = urllib.parse.urlencode({**ident, "callback_url": url, "verify_token": conf["STRAVA_WEBHOOK_VERIFY"]}).encode()
        with urllib.request.urlopen(urllib.request.Request(base, data=data), timeout=20) as r:
            print(r.read().decode())
    elif action == "supprimer":
        subs = json.loads(urllib.request.urlopen(f"{base}?{urllib.parse.urlencode(ident)}", timeout=15).read())
        for s in subs:
            req = urllib.request.Request(f"{base}/{s['id']}?{urllib.parse.urlencode(ident)}", method="DELETE")
            urllib.request.urlopen(req, timeout=15)
            print(f"abonnement {s['id']} supprimé")


if __name__ == "__main__":
    servir()
