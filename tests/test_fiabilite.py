"""Fiabilité : verrou entre processus, écritures atomiques, webhook réel, flux strava-enrich de bout en bout, connecteurs HTTP.

Aucun test n'atteint un vrai service : Strava, Baïkal, Home Assistant et ntfy sont remplacés par des faux.
"""

import datetime as dt
import io
import json
import os
import stat
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

from src import config, planif, strava, strava_enrich, webhook


def _mode(p: Path) -> int:
    return stat.S_IMODE(p.stat().st_mode)


class Config(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.d))

    def test_load_config_guillemets_commentaires_et_surcharge(self):
        env = self.d / "coach.env"
        env.write_text(
            "# commentaire\nNTFY_TOKEN='abc'\nHA_URL=\"http://ha\"\nligne sans egal\n\nSTRAVA_ATHLETE_ID = 42\n"
        )
        with (
            mock.patch.object(config, "DEFAULT_ENV_PATHS", [env]),
            mock.patch.dict(
                os.environ, {"COACH_RACE_DATE": "2026-12-01", "AUTRE": "x"}
            ),
        ):
            c = config.load_config()
        self.assertEqual(c["NTFY_TOKEN"], "abc")
        self.assertEqual(c["HA_URL"], "http://ha")
        self.assertEqual(c["STRAVA_ATHLETE_ID"], "42")
        self.assertEqual(
            c["COACH_RACE_DATE"], "2026-12-01"
        )  # l'environnement l'emporte, préfixes connus seulement
        self.assertNotIn("AUTRE", c)
        self.assertEqual(config.race_date(c), dt.date(2026, 12, 1))

    def test_ecriture_atomique_garde_les_droits_et_cree_en_0600(self):
        f = self.d / "coach.env"
        f.write_text("A=1\n")
        f.chmod(0o640)
        config.ecrire_atomique(f, "A=2\n")
        self.assertEqual((f.read_text(), _mode(f)), ("A=2\n", 0o640))
        neuf = self.d / "sous" / "etat.json"
        config.ecrire_json(neuf, {"é": 1})
        self.assertEqual(json.loads(neuf.read_text()), {"é": 1})
        self.assertEqual(_mode(neuf), 0o600)
        self.assertEqual(list(neuf.parent.glob("*.tmp")), [])

    def test_ecriture_interrompue_laisse_l_ancien_fichier(self):
        f = self.d / "etat.json"
        config.ecrire_json(f, {"v": 1})
        with (
            mock.patch("json.dumps", side_effect=RuntimeError("panne")),
            self.assertRaises(RuntimeError),
        ):
            config.ecrire_json(f, {"v": 2})
        self.assertEqual(json.loads(f.read_text()), {"v": 1})

    def test_verrou_exclusif_puis_libere(self):
        chemin = str(self.d / "coach.lock")
        premier = config.verrou(chemin, 0)
        with self.assertRaises(TimeoutError):
            config.verrou(
                chemin, 0
            )  # un second écrivain (cron, webhook) attend puis abandonne
        premier.close()
        config.verrou(chemin, 0).close()  # libéré à la fermeture (fin du processus)


class PersistanceStrava(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.d))

    def test_refresh_token_reecrit_sans_perdre_les_autres_cles(self):
        env = self.d / "coach.env"
        env.write_text("NTFY_TOKEN=x\nSTRAVA_REFRESH_TOKEN=ancien\nHA_TOKEN=y\n")
        env.chmod(0o600)
        with mock.patch.object(strava, "env_file", return_value=env):
            strava._persist_refresh("nouveau")
        self.assertEqual(
            env.read_text(), "NTFY_TOKEN=x\nSTRAVA_REFRESH_TOKEN=nouveau\nHA_TOKEN=y\n"
        )
        self.assertEqual(_mode(env), 0o600)

    def test_jeton_mis_en_cache_en_0600_et_reutilise(self):
        cache = self.d / "tok.json"
        conf = {"STRAVA_REFRESH_TOKEN": "r"}
        appels = []

        def renouveler(c):
            appels.append(1)
            return {"access_token": "A", "expires_at": 10**10}

        with (
            mock.patch.object(strava, "CACHE", cache),
            mock.patch.object(strava, "_renouveler", renouveler),
        ):
            self.assertEqual(strava.token(conf), "A")
            self.assertEqual(strava.token(conf), "A")
            self.assertEqual(len(appels), 1)
            self.assertEqual(_mode(cache), 0o600)
            self.assertEqual(
                strava.token({"STRAVA_REFRESH_TOKEN": "autre"}), "A"
            )  # refresh changé : nouvel appel
            self.assertEqual(len(appels), 2)


class WebhookReel(unittest.TestCase):
    """Le vrai serveur HTTP sur un port local : chemin secret, corps invalides, déclenchement."""

    def setUp(self):
        webhook.Handler.conf = {
            "STRAVA_WEBHOOK_SECRET": "s3cret",
            "STRAVA_WEBHOOK_VERIFY": "v",
            "STRAVA_ATHLETE_ID": "7",
        }
        self.srv = webhook.ThreadingHTTPServer(("127.0.0.1", 0), webhook.Handler)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        p = mock.patch.object(webhook, "declencher")
        self.declencher = p.start()
        self.addCleanup(p.stop)

    def _req(self, chemin, corps=None, entetes=None, methode=None):
        import http.client

        c = http.client.HTTPConnection(
            "127.0.0.1", self.srv.server_address[1], timeout=5
        )
        c.putrequest(
            methode or ("POST" if corps is not None else "GET"),
            chemin,
            skip_accept_encoding=True,
        )
        for k, v in (entetes or {}).items():
            c.putheader(k, v)
        c.endheaders(corps)
        r = c.getresponse()
        return r.status, r.read()

    def test_evenement_valide_declenche(self):
        ev = b'{"object_type":"activity","aspect_type":"create","owner_id":7}'
        self.assertEqual(
            self._req("/strava/s3cret", ev, {"Content-Length": str(len(ev))})[0], 200
        )
        import time
        fin = time.monotonic() + 3
        while not self.declencher.called and time.monotonic() < fin:   # appelé après l'envoi de la réponse
            time.sleep(0.01)
        self.declencher.assert_called_once()

    def test_content_length_negatif_ou_invalide_ne_bloque_pas(self):
        self.assertEqual(
            self._req("/strava/s3cret", b"", {"Content-Length": "-1"})[0], 200
        )
        self.assertEqual(
            self._req("/strava/s3cret", b"", {"Content-Length": "abc"})[0], 200
        )
        self.declencher.assert_not_called()

    def test_chemin_non_ascii_404_sans_exception(self):
        self.assertEqual(
            webhook.traiter("POST", "/strava/sécret", b"{}", webhook.Handler.conf)[0],
            404,
        )
        self.assertEqual(
            webhook.traiter(
                "GET",
                "/strava/s3cret?hub.mode=subscribe&hub.verify_token=%C3%A9",
                b"",
                webhook.Handler.conf,
            )[0],
            403,
        )
        self.assertEqual(self._req("/strava/autre")[0], 404)

    def test_journal_ne_contient_jamais_le_secret(self):
        sortie = io.StringIO()
        with mock.patch("sys.stdout", sortie):
            self._req(
                "/strava/s3cret?hub.mode=subscribe&hub.verify_token=v&hub.challenge=c"
            )
        self.assertNotIn("s3cret", sortie.getvalue())


class SeanceDuJour(unittest.TestCase):
    JOUR = [
        "2026-11-10 08:30→08:55  [Sport] Renfo B1, haut du corps et gainage  — a.ics",
        "2026-11-10 18:30→19:15  [Sport] CAP: Footing EF 40 min au club ASM @ Stade  — b.ics",
    ]

    def test_course_du_soir_jamais_le_renfo_du_matin(self):
        with mock.patch.object(strava_enrich.baikal, "lister", return_value=self.JOUR):
            self.assertEqual(
                strava_enrich.seance_du_jour("2026-11-10", "18:34"),
                "CAP: Footing EF 40 min au club ASM",
            )
            self.assertEqual(
                strava_enrich.seance_du_jour("2026-11-10"),
                "CAP: Footing EF 40 min au club ASM",
            )

    def test_la_plus_proche_de_l_heure_de_depart(self):
        deux = [
            "2026-11-12 08:30  [Sport] CAP: Footing EF 30 min  — a.ics",
            "2026-11-12 18:30  [Sport] CAP: Seuil 3x3000m  — b.ics",
        ]
        with mock.patch.object(strava_enrich.baikal, "lister", return_value=deux):
            self.assertEqual(
                strava_enrich.seance_du_jour("2026-11-12", "08:41"),
                "CAP: Footing EF 30 min",
            )
            self.assertEqual(
                strava_enrich.seance_du_jour("2026-11-12", "18:20"),
                "CAP: Seuil 3x3000m",
            )

    def test_sortie_de_groupe_et_journee_sans_course(self):
        with mock.patch.object(
            strava_enrich.baikal,
            "lister",
            return_value=[
                "2026-12-12 09:00  [Sport] Groupe : sortie Pic du Rey  — g.ics"
            ],
        ):
            self.assertEqual(
                strava_enrich.seance_du_jour("2026-12-12", "09:05"),
                "Groupe : sortie Pic du Rey",
            )
        with mock.patch.object(
            strava_enrich.baikal, "lister", return_value=[self.JOUR[0]]
        ):
            self.assertIsNone(strava_enrich.seance_du_jour("2026-11-10", "18:30"))


class SynchroniserPanneBaikal(unittest.TestCase):
    def test_evenements_crees_avant_la_panne_restent_dans_l_etat(self):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(d))
        jour = dt.date(2026, 11, 20)
        seances = [
            planif.Seance(
                "2026-11-20", "08:30", 40, "CAP: Footing EF 40 min", "x", "ef", False
            ),
            planif.Seance(
                "2026-11-21", "16:00", 30, "Renfo A1, bas du corps", "y", "renfo", False
            ),
        ]
        crees = iter(["un.ics"])

        def creer(*a, **k):
            try:
                return next(crees)
            except StopIteration:
                raise RuntimeError("Baïkal indisponible") from None

        with (
            mock.patch.object(planif, "STATE", d / "p.json"),
            mock.patch.object(planif.baikal, "lister", return_value=[]),
            mock.patch.object(planif.baikal, "creer", creer),
        ):
            with self.assertRaises(RuntimeError):
                planif.synchroniser(
                    seances, jour, jour + dt.timedelta(days=5), apply=True
                )
            etat = planif.charger()
        self.assertEqual(
            list(etat["evenements"]), ["un.ics"]
        )  # au passage suivant : pas de doublon
        self.assertEqual(etat["evenements"]["un.ics"]["cle"], "2026-11-20|ef")


class StravaEnrichBoutEnBout(unittest.TestCase):
    """Un passage de strava-enrich sur le footing du club du 10/11 : nom, description, débrief unique, état écrit."""

    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.d))
        depart = dt.datetime.now(dt.UTC) - dt.timedelta(hours=1)
        self.act = {
            "id": 99,
            "name": "Evening Run",
            "sport_type": "Run",
            "distance": 8000.0,
            "moving_time": 2600,
            "elapsed_time": 2700,
            "start_date": depart.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "start_date_local": "2026-11-10T18:34:00",
            "average_heartrate": 140,
            "description": None,
        }
        self.ecrits, self.ntfy = [], []

        def call(tok, chemin, methode="GET", corps=None):
            if methode == "PUT":
                self.ecrits.append(corps)
                return {}
            return [] if chemin.endswith("/laps") else {}

        lister = mock.Mock(
            side_effect=lambda date, *a, **k: (
                SeanceDuJour.JOUR if date == "2026-11-10" else []
            )
        )
        patches = [
            mock.patch.object(strava_enrich, "STATE", self.d / "s.json"),
            mock.patch.object(planif, "STATE", self.d / "p.json"),
            mock.patch.object(strava, "token", return_value="t"),
            mock.patch.object(strava, "activities", return_value=[self.act]),
            mock.patch.object(strava, "call", call),
            mock.patch.object(strava_enrich.baikal, "lister", lister),
            mock.patch.object(strava_enrich.baikal, "deplacer"),
            mock.patch(
                "src.ntfy.envoyer", lambda *a, **k: self.ntfy.append(a[1])
            ),
            mock.patch("src.strava_sync.sync_strava_to_ha"),
            mock.patch("src.materiel.verifier"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_nom_du_club_debrief_unique_et_idempotent(self):
        conf = {"COACH_RACE_DATE": "2026-11-29"}
        with mock.patch("sys.stdout", io.StringIO()):
            self.assertEqual(strava_enrich.run(apply=True, conf=conf), 1)
            self.assertEqual(
                strava_enrich.run(apply=True, conf=conf), 0
            )  # second passage (webhook puis cron) : rien de plus
        self.assertEqual(self.ecrits[0]["name"], "Footing EF 40 min au club ASM")
        self.assertIn(
            "Séance prévue : Footing EF 40 min au club ASM",
            self.ecrits[0]["private_note"],
        )
        self.assertEqual(len(self.ecrits), 1)
        self.assertEqual(self.ntfy, ["Séance terminée : Footing EF 40 min au club ASM"])
        etat = json.loads((self.d / "s.json").read_text())
        self.assertIn("99", etat["done"])
        self.assertTrue(etat["debrief"]["99"])

    def test_debrief_et_description_meme_phrase_memorisee(self):
        with mock.patch("sys.stdout", io.StringIO()):
            strava_enrich.run(apply=True, conf={"COACH_RACE_DATE": "2026-11-29"})
        tete = __import__("src.humour", fromlist=["sans_smiley"]).sans_smiley(self.ecrits[0]["description"].split("\n")[0])
        etat = json.loads((self.d / "s.json").read_text())
        self.assertEqual(etat["humour_vu"], {tete: "99"})

    def test_dry_run_n_ecrit_rien(self):
        with mock.patch("sys.stdout", io.StringIO()):
            strava_enrich.run(apply=False, conf={"COACH_RACE_DATE": "2026-11-29"})
        self.assertEqual((self.ecrits, self.ntfy), ([], []))


class _FauxHTTP:
    """Capture les requêtes urllib (Home Assistant, ntfy) au lieu de les envoyer."""

    def __init__(self):
        self.req = []

    def __call__(self, req, timeout=None):
        self.req.append(req)
        return io.BytesIO(b"{}")


class Connecteurs(unittest.TestCase):
    # jamais de conf vide dans ces tests : `conf or load_config()` lirait le vrai coach.env
    def test_strava_vers_home_assistant(self):
        from src import strava_sync

        faux = _FauxHTTP()
        act = {
            "name": "Course du soir",
            "sport_type": "Run",
            "distance": 8000,
            "moving_time": 2600,
            "average_heartrate": 140,
            "total_elevation_gain": 50,
            "start_date_local": "2026-11-10T18:34:00",
        }
        with (
            mock.patch.object(strava, "token", return_value="t"),
            mock.patch.object(strava, "activities", return_value=[act]),
            mock.patch.object(urllib.request, "urlopen", faux),
            mock.patch("sys.stdout", io.StringIO()),
        ):
            strava_sync.sync_strava_to_ha({"HA_TOKEN": "h", "HA_URL": "http://ha/"})
        urls = [r.full_url for r in faux.req]
        self.assertIn("http://ha/api/states/sensor.strava_last_activity_pace", urls)
        self.assertEqual(faux.req[0].get_header("Authorization"), "Bearer h")
        corps = {
            r.full_url.rsplit(".", 1)[1]: json.loads(r.data)["state"] for r in faux.req
        }
        self.assertEqual(
            (
                corps["strava_last_activity_distance"],
                corps["strava_last_activity_duration"],
            ),
            ("8.0", "0h43m"),
        )

    def test_home_assistant_sans_jeton(self):
        from src import ha, strava_sync

        self.assertEqual(ha.pousser({"HA_URL": "http://ha"}), 0)
        with self.assertRaises(ValueError):
            strava_sync.sync_strava_to_ha({"HA_URL": "http://ha"})

    def test_capteurs_coach(self):
        from src import ha

        faux = _FauxHTTP()
        lignes = ["2026-11-10 18:30  [Sport] CAP: Footing EF 40 min  — b.ics"]
        with (
            mock.patch.object(ha.baikal, "lister", return_value=lignes),
            mock.patch.object(planif, "charger", return_value={"journal": []}),
            mock.patch.object(urllib.request, "urlopen", faux),
        ):
            n = ha.pousser(
                {"HA_TOKEN": "h"}, dt.datetime(2026, 11, 10, 9, 0, tzinfo=planif.PARIS)
            )
        self.assertEqual(n, 5)
        etats = {
            r.full_url.rsplit(".", 1)[1]: json.loads(r.data)["state"] for r in faux.req
        }
        self.assertEqual(
            etats["coach_prochaine_seance"], "mar 10/11 18:30 CAP: Footing EF 40 min"
        )
        self.assertEqual(etats["coach_jours_objectif"], "19")

    def test_ntfy_entetes_et_decimales(self):
        from src import ntfy, suivi

        faux = _FauxHTTP()
        with mock.patch.object(urllib.request, "urlopen", faux), mock.patch.object(suivi, "ENVOYE", False):
            ntfy.envoyer({"NTFY_URL": "https://ntfy/x", "NTFY_TOKEN": "tk"}, "Coach : séance", "8.5 km", priority="high")
            self.assertTrue(suivi.ENVOYE)   # l'alerte « aucun briefing » compte sur ce drapeau
        self.assertEqual(faux.req[0].full_url, "https://ntfy/x")
        r = faux.req[0]
        self.assertEqual(
            (r.data, r.get_header("Priority"), r.get_header("Authorization")),
            (b"8,5 km", "high", "Bearer tk"),
        )
        self.assertEqual(r.get_header("Title"), "Coach : séance".encode())

    def test_chaussures_une_alerte_par_seuil(self):
        from src import materiel

        d = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(d))
        envoyes = []

        def call(tok, chemin):
            return {"name": "Evo SL", "distance": 720000}

        with (
            mock.patch.object(materiel, "STATE", d / "s.json"),
            mock.patch.object(strava, "activities", return_value=[{"gear_id": "g1"}]),
            mock.patch.object(strava, "call", call),
            mock.patch(
                "src.ntfy.envoyer", lambda *a, **k: envoyes.append(a[1])
            ),
        ):
            self.assertEqual(len(materiel.verifier({"NTFY_URL": "x"}, "t")), 1)
            self.assertEqual(
                materiel.verifier({"NTFY_URL": "x"}, "t"), []
            )  # même seuil : pas de deuxième alerte
        self.assertEqual(envoyes, ["Chaussures bientôt usées : Evo SL"])
        self.assertEqual(
            json.loads((d / "s.json").read_text())["materiel"], {"g1": 700}
        )


if __name__ == "__main__":
    unittest.main()


class Charge(unittest.TestCase):
    J = dt.date(2026, 11, 10)

    def test_charge_constante_rapport_proche_de_1(self):
        from src import charge
        jours = {(self.J - dt.timedelta(days=i)).isoformat(): 60 for i in range(200)}
        c = charge.calculer(jours, self.J)
        self.assertAlmostEqual(c["atl"], 60, delta=0.5)
        self.assertGreater(c["ctl"], 55)   # 150 jours : 97 % de la valeur stable
        self.assertEqual(charge.avis(c["ratio"]), "charge maîtrisée")

    def test_semaine_chargee_apres_repos_alerte(self):
        from src import charge
        jours = {(self.J - dt.timedelta(days=i)).isoformat(): 40 for i in range(7, 200)}
        jours.update({(self.J - dt.timedelta(days=i)).isoformat(): 150 for i in range(4)})
        c = charge.calculer(jours, self.J)
        self.assertGreater(c["ratio"], 1.5)
        self.assertIn("risque de blessure", charge.phrase(c))

    def test_sans_historique(self):
        from src import charge
        self.assertIsNone(charge.calculer({}, self.J)["ratio"])
        self.assertIn("pas assez", charge.avis(None))

    def test_par_jour_additionne_et_s_arrete_a_la_veille(self):
        from src import charge
        faux = mock.Mock()
        faux.get_activities_by_date.return_value = [{"startTimeLocal": "2026-11-09 09:14:00", "activityTrainingLoad": 254},
                                                   {"startTimeLocal": "2026-11-09 18:00:00", "activityTrainingLoad": 20},
                                                   {"startTimeLocal": "2026-11-08 10:00:00", "activityTrainingLoad": None}]
        self.assertEqual(charge.par_jour(faux, self.J), {"2026-11-09": 274, "2026-11-08": 0})
        self.assertEqual(charge.du_jour(faux, self.J)["date"], "2026-11-09")
        self.assertEqual(faux.get_activities_by_date.call_args[0][1], "2026-11-09")


class FauxGarmin:
    def __init__(self, jour: str):
        self.jour = jour

    def get_user_summary(self, d):
        return {"bodyBatteryMostRecentValue": 70, "bodyBatteryAtWakeTime": 80, "restingHeartRate": 48, "lastSevenDaysAvgRestingHeartRate": 48}

    def get_sleep_data(self, d):
        return {"dailySleepDTO": {"sleepTimeSeconds": 28800, "calendarDate": d, "sleepScores": {"overall": {"value": 85}}}}

    def get_hrv_data(self, d):
        return {"hrvSummary": {"status": "BALANCED"}}

    def get_lactate_threshold(self, latest=True):
        return {"speed_and_heart_rate": {"heartRate": 182, "speed": 0.38333, "calendarDate": "2026-11-09T10:30:19"}}

    def get_activities_by_date(self, debut, fin):
        j0 = dt.date.fromisoformat(fin)
        return [{"startTimeLocal": f"{(j0 - dt.timedelta(days=i)).isoformat()} 08:30:00", "activityTrainingLoad": 80} for i in range(0, 120, 2)]


def _meteo(*a, **k):
    debut = dt.date.today()
    heures = [f"{debut + dt.timedelta(days=j)}T{h:02d}:00" for j in range(8) for h in range(24)]
    n = len(heures)
    jours = [(debut + dt.timedelta(days=j)).isoformat() for j in range(8)]
    return {"hourly": {"time": heures, "apparent_temperature": [8] * n, "precipitation_probability": [10] * n, "precipitation": [0] * n,
                       "wind_speed_10m": [10] * n, "wind_gusts_10m": [20] * n, "uv_index": [1] * n, "cloud_cover": [80] * n, "is_day": [1] * n},
            "daily": {"time": jours, "sunrise": [f"{j}T07:50" for j in jours], "sunset": [f"{j}T17:50" for j in jours]}}


class _BaseBriefings(unittest.TestCase):
    """Briefings complets avec de faux Garmin, Baïkal, météo, Strava et ntfy : ce qui part vraiment sur le téléphone."""

    def setUp(self):
        from src import agent_coach, semaine
        self.d = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.d))
        self.today = dt.datetime.now(planif.PARIS).date()
        self.envois, self.charges = [], []
        lignes = {self.today.isoformat(): [f"{self.today} 18:30→19:15  [Sport] CAP: Footing EF 40 min @ Route / Bitume plat  — b.ics"]}
        patches = [mock.patch.object(agent_coach, "MARQUEURS", self.d), mock.patch.object(semaine, "MARQUEURS", self.d),
                   mock.patch.object(agent_coach.garmin, "client", lambda *a: FauxGarmin(self.today.isoformat())),
                   mock.patch.object(agent_coach.baikal, "lister", lambda d, *a, **k: lignes.get(d, []) if not a and not k else []),
                   mock.patch.object(agent_coach.meteo, "fetch", _meteo),
                   mock.patch.object(agent_coach.boucles, "suggere_pour_titre", lambda *a: None),
                   mock.patch.object(planif, "planifier", lambda *a, **k: ([], [])), mock.patch.object(planif, "ajuster_jour", lambda *a, **k: []),
                   mock.patch.object(planif, "enregistrer_charge", self.charges.append),
                   mock.patch.object(planif, "charger", lambda: {"journal": [], "evenements": {}}),
                   mock.patch("src.ntfy.envoyer", lambda conf, titre, corps, *a, **k: self.envois.append((titre, corps))),
                   mock.patch.object(strava, "token", return_value="t"), mock.patch.object(strava, "activities", return_value=[]),
                   mock.patch.object(strava, "call", return_value=[]),
                   mock.patch("sys.stdout", io.StringIO())]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def conf(self, jours_avant_course: int) -> dict:
        return {"COACH_RACE_DATE": (self.today + dt.timedelta(days=jours_avant_course)).isoformat(), "NTFY_URL": "x"}


class BriefingsBoutEnBout(_BaseBriefings):
    def test_matin_complet_avec_charge_puis_anti_doublon(self):
        from src import agent_coach
        self.assertEqual(agent_coach.run_agent_coach(conf=self.conf(19)), 0)
        titre, corps = self.envois[0]
        self.assertEqual(titre, "Coach du matin : J-19 avant Lourdes-Tarbes")
        for attendu in ("SÉANCE", "18:30 CAP: Footing EF 40 min", "MÉTÉO", "FORME", "CHARGE", "Condition", "REPAS"):
            self.assertIn(attendu, corps)
        self.assertNotIn("SOURCES EN PANNE", corps)
        self.assertEqual(len(self.charges), 1)
        agent_coach.run_agent_coach(conf=self.conf(19))
        self.assertEqual(len(self.envois), 1)   # déjà envoyé aujourd'hui

    def test_veille_du_semi_n_empeche_pas_le_briefing_du_jour_de_course(self):
        from src import agent_coach
        agent_coach.run_agent_coach(conf=self.conf(1))
        self.assertEqual((self.d / "coach-brief-matin").read_text(), self.today.isoformat())   # écrivait la date de la course
        agent_coach.run_agent_coach(soir=True, conf=self.conf(1), force=True)
        self.assertEqual(self.envois[-1][0], "Veille du semi de Lourdes-Tarbes")
        self.assertEqual((self.d / "coach-brief-soir").read_text(), self.today.isoformat())

    def test_jour_de_course(self):
        from src import agent_coach
        agent_coach.run_agent_coach(conf=self.conf(0))
        titre, corps = self.envois[0]
        self.assertEqual(titre, "Jour de course : semi de Lourdes-Tarbes")
        self.assertIn("Sommeil 85/100", corps)

    def test_recap_de_la_semaine(self):
        from src import semaine
        semaine.run(conf=self.conf(19))
        titre, corps = self.envois[0]
        self.assertEqual(titre, "Coach de la semaine : J-19 avant Lourdes-Tarbes")
        self.assertIn("Condition", corps)
        self.assertIn("SOMMEIL", corps)
        self.assertEqual((self.d / "coach-brief-semaine").read_text()[:4], str(dt.date.today().isocalendar().year))


class NtfyPieceJointe(unittest.TestCase):
    def test_gpx_en_put_avec_nom_de_fichier(self):
        from src import boucles
        d = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(d))
        f = d / "123.gpx"
        f.write_text("<gpx/>")
        faux = _FauxHTTP()
        with mock.patch.object(urllib.request, "urlopen", faux):
            boucles.envoyer_gpx({"NTFY_URL": "https://ntfy/x", "NTFY_TOKEN": "tk"}, f, "Parcours GPX 123")
        r = faux.req[0]
        self.assertEqual((r.get_method(), r.data, r.get_header("Filename"), r.get_header("Authorization")), ("PUT", b"<gpx/>", "123.gpx", "Bearer tk"))


class SeancesDuJourNext(unittest.TestCase):
    def test_corps_du_plan_pour_le_coach_et_allegement(self):
        from src import plan as P
        d = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(d))
        semaines = {"2026-11-09": [P.Entree(3, "seuil", "Seuil test", 60, "3x3000m à 4'20", chaussures="Evo SL")]}
        etat = {"evenements": {"a.ics": {"cle": "2026-11-12|seuil"}, "b.ics": {"cle": "2026-11-12|seuil", "empreinte": "allege"}}}
        evs = [{"heure": "18:30", "titre": "CAP: Seuil test", "lieu": "Stade", "id": "a.ics"},
               {"heure": "08:30", "titre": "CAP: Footing EF 40 min (séance allégée)", "lieu": None, "id": "b.ics"},
               {"heure": "10:00", "titre": "Dentiste", "lieu": None, "id": None}, None]
        with mock.patch.object(planif, "SEMAINES", semaines), mock.patch.object(planif, "charger", return_value=etat):
            out = planif.seances_du_jour("2026-11-12", evs)
        self.assertEqual(out[0], "18:30 CAP: Seuil test (Stade)\n    3x3000m à 4'20\n    Chaussures : Evo SL")
        self.assertIn("allégée", out[1].splitlines()[1])
        self.assertEqual(out[2], "10:00 Dentiste")
        self.assertEqual(len(out), 3)


from src import garmin as _garmin_module  # noqa: E402

CLIENT_REEL = _garmin_module.client   # gardé avant les remplacements des tests de briefing


class UneConnexionGarmin(_BaseBriefings):
    """Un briefing complet (passage du réveil, forme, charge) ne se connecte qu'une fois à Garmin."""

    def _connexions(self, echec: bool = False) -> list:
        connexions = []
        today = self.today.isoformat()

        class Faux(FauxGarmin):
            def __init__(self, email, mdp):
                super().__init__(today)

            def login(self, tokens):
                connexions.append(tokens)
                if echec:
                    raise RuntimeError("429 Too Many Requests")
        for p in (mock.patch.object(_garmin_module, "client", CLIENT_REEL), mock.patch.object(_garmin_module, "Garmin", Faux),
                  mock.patch.dict(_garmin_module._SESSIONS, clear=True)):
            p.start()
            self.addCleanup(p.stop)
        return connexions

    def test_reveil_forme_et_charge_une_seule_connexion(self):
        from src import agent_coach
        connexions = self._connexions()
        conf = {**self.conf(19), "COACH_REVEIL_DEBUT": "00:00", "GARMIN_TOKENS": "/faux/jetons.json"}
        self.assertEqual(agent_coach.run_agent_coach(conf=conf, reveil=True), 0)
        self.assertIn("Condition", self.envois[0][1])
        self.assertEqual(connexions, ["/faux/jetons.json"])

    def test_echec_de_connexion_pas_retente_et_dit(self):
        from src import agent_coach
        connexions = self._connexions(echec=True)
        conf = {**self.conf(19), "GARMIN_TOKENS": "/faux/jetons.json"}
        self.assertEqual(agent_coach.run_agent_coach(conf=conf), 1)   # source en panne : code 1, priorité urgente
        corps = self.envois[0][1]
        self.assertIn("SOURCES EN PANNE", corps)
        self.assertIn("Garmin : RuntimeError 429", corps)
        self.assertEqual(len(connexions), 1)   # forme puis charge : la seconde ne retente pas


class MessagesPurs(unittest.TestCase):
    def test_message_soir_sans_seance(self):
        from src import agent_coach
        corps = agent_coach.message_soir([], None)
        self.assertIn("DEMAIN\nRepos ou séance libre", corps)
        self.assertIn("Montre au poignet", corps)

    def test_pannes_tardives_visibles(self):
        from src import agent_coach
        src = agent_coach.Sources()
        self.assertEqual(src.tenter("Planification", lambda: 1 / 0, "défaut"), "défaut")
        self.assertEqual(src.problemes, ["Planification : ZeroDivisionError division by zero"])


class IsolationDesTests(unittest.TestCase):
    """Garde-fou : le 2026-11-10, un test a écrasé le vrai état du planificateur. Rien de réel n'est joignable depuis les tests."""

    def test_fichiers_d_etat_dans_le_bac_temporaire(self):
        from src import boucles, materiel, strava, strava_enrich
        from tests import BAC
        for p in (planif.STATE, strava_enrich.STATE, materiel.STATE, boucles.CATALOGUE, strava.CACHE, boucles.GPX_DIR):
            self.assertTrue(str(p).startswith(str(BAC)), p)
        self.assertEqual(config.load_config(), {k: v for k, v in os.environ.items() if k.startswith(config.PREFIXES)})

    def test_services_reels_refuses(self):
        from src import baikal, garmin
        for appel in (lambda: baikal.lister("2026-11-10"), lambda: garmin.client({"GARMIN_TOKENS": "/x"}),
                      lambda: urllib.request.urlopen("https://ntfy.sh/coach-sport-test")):
            with mock.patch.dict(garmin._SESSIONS, clear=True), self.assertRaises(RuntimeError) as e:
                appel()
            self.assertIn("interdit dans les tests", str(e.exception))


class SeuilEtFcRepos(unittest.TestCase):
    # séance du 09/11 : bloc 1 à 4'17 (FC jusqu'à 188), bloc 2 à 4'28 (FC qui dérive de 175 à 188)
    LAPS = [{"distance": 1000, "moving_time": 339, "average_heartrate": 151}, {"distance": 594, "moving_time": 286, "average_heartrate": 148},
            {"distance": 1000, "moving_time": 261, "average_heartrate": 168}, {"distance": 1000, "moving_time": 256, "average_heartrate": 187.5},
            {"distance": 1000, "moving_time": 257, "average_heartrate": 188.7}, {"distance": 487, "moving_time": 125, "average_heartrate": 188},
            {"distance": 160, "moving_time": 119, "average_heartrate": 160},
            {"distance": 1000, "moving_time": 268, "average_heartrate": 175}, {"distance": 1000, "moving_time": 268, "average_heartrate": 183},
            {"distance": 1000, "moving_time": 270, "average_heartrate": 186.6}, {"distance": 361, "moving_time": 94, "average_heartrate": 187.7}]

    def test_verdict_par_bloc_sans_le_premier_tour(self):
        act = {"distance": 13160, "moving_time": 4427, "average_heartrate": 161}
        lignes = strava_enrich.bilan(act, "CAP: Seuil 2x15m AS21", self.LAPS, 265, fcsl=182)
        self.assertIn("FC 188 : au-dessus du seuil (182)", lignes[1])
        self.assertIn("FC 185 : au-dessus du seuil (182)", lignes[2])
        self.assertIn("au seuil (186)", strava_enrich.bilan(act, "CAP: Seuil 2x15m AS21", self.LAPS, 265, fcsl=186)[2])
        self.assertNotIn("seuil (", strava_enrich.bilan(act, "CAP: Seuil 2x15m AS21", self.LAPS, 265)[1])   # sans FCSL : pas de verdict

    def test_bornes_du_verdict(self):
        v = strava_enrich.verdict_seuil
        self.assertEqual([v(f, 183) for f in (177, 178, 185, 186)], ["sous le seuil", "au seuil", "au seuil", "au-dessus du seuil"])

    def test_seuil_garmin_converti(self):
        from src import garmin
        self.assertEqual(garmin.seuil(FauxGarmin("2026-11-10")), {"fc": 182, "allure": 261, "date": "2026-11-09"})
        vide = mock.Mock(get_lactate_threshold=mock.Mock(return_value={}))
        self.assertIsNone(garmin.seuil(vide))

    def test_fc_repos_haute_trois_jours(self):
        from src import decision
        h = {(dt.date(2026, 11, 10) - dt.timedelta(days=i)).isoformat(): 51 for i in range(3, 33)}
        h.update({"2026-11-08": 55, "2026-11-09": 56, "2026-11-10": 55})
        self.assertIn("FC au repos haute 3 jours de suite (55, 56, 55 bpm contre 51 en moyenne)", decision.fc_repos_elevee(h, "2026-11-10"))
        self.assertIsNone(decision.fc_repos_elevee({**h, "2026-11-09": 53}, "2026-11-10"))    # un jour sous le seuil : pas d'alerte
        self.assertIsNone(decision.fc_repos_elevee({k: v for k, v in h.items() if k >= "2026-10-30"}, "2026-11-10"))  # historique trop court
        self.assertIsNone(decision.fc_repos_elevee({k: v for k, v in h.items() if k != "2026-11-08"}, "2026-11-10"))  # jour manquant

    def test_historique_fc_repos_borne_a_60_jours(self):
        etat = {"evenements": {}, "journal": []}
        with mock.patch.object(planif, "charger", return_value=etat), mock.patch.object(planif, "sauver") as sauver:
            for i in range(70):
                planif.enregistrer_fc_repos((dt.date(2026, 9, 1) + dt.timedelta(days=i)).isoformat(), 50)
            planif.enregistrer_fc_repos("2026-11-10", None)   # montre non portée : rien n'est écrit
        self.assertEqual(len(etat["fc_repos"]), 60)
        self.assertEqual(sauver.call_count, 70)


class BriefingFcReposEtSeuil(_BaseBriefings):
    def test_alerte_et_seuil_memorise(self):
        from src import agent_coach
        j = self.today
        h = {(j - dt.timedelta(days=i)).isoformat(): 51 for i in range(3, 33)}
        h.update({(j - dt.timedelta(days=i)).isoformat(): 56 for i in (1, 2)})
        memo = {}
        with mock.patch.object(planif, "enregistrer_fc_repos", lambda d, v: {**h, d: v}), \
                mock.patch.object(planif, "memoriser", lambda k, v: memo.__setitem__(k, v)), \
                mock.patch.object(FauxGarmin, "get_user_summary", lambda self, d: {"restingHeartRate": 57, "bodyBatteryAtWakeTime": 80}):
            agent_coach.run_agent_coach(conf=self.conf(19))
        corps = self.envois[0][1]
        self.assertIn("FC au repos haute 3 jours de suite (56, 56, 57 bpm contre 51 en moyenne)", corps)
        self.assertNotIn("SOURCES EN PANNE", corps)
        self.assertEqual(memo["seuil"]["fc"], 182)



class ChargeAvecVelo(unittest.TestCase):
    """Les sorties du compteur iGPSPORT (sur Strava, absentes de Garmin) comptent dans la charge, sans doublon."""

    GARMIN = [{"startTimeGMT": "2026-10-04 08:00:00", "startTimeLocal": "2026-10-04 10:00:00", "activityTrainingLoad": 80}]
    STRAVA = [{"start_date": "2026-10-04T08:01:10Z", "start_date_local": "2026-10-04T10:01:10Z", "suffer_score": 40, "sport_type": "Run"},
              {"start_date": "2026-09-30T07:00:00Z", "start_date_local": "2026-09-30T09:00:00Z", "suffer_score": 177, "sport_type": "Ride"},
              {"start_date": "2026-10-05T07:00:00Z", "start_date_local": "2026-10-05T09:00:00Z", "suffer_score": None, "sport_type": "Walk"}]

    def test_velo_ajoute_course_garmin_pas_comptee_deux_fois(self):
        from src import charge
        c = charge.ajouter_strava({"2026-10-04": 80}, self.GARMIN, self.STRAVA)
        self.assertEqual(c["2026-10-04"], 80)                       # même départ à 70 s près : déjà comptée par Garmin
        self.assertAlmostEqual(c["2026-09-30"], 177 * 2.3)          # 4 h de vélo : charge d'environ 400
        self.assertNotIn("2026-10-05", c)                           # sans effort relatif : rien

    def test_charge_de_la_veille_renvoyee(self):
        from src import charge
        faux = mock.Mock()
        faux.get_activities_by_date.return_value = []
        ch = charge.du_jour(faux, dt.date(2026, 10, 1), self.STRAVA)
        self.assertEqual(ch["veille"], round(177 * 2.3))
        self.assertGreater(ch["atl"], 0)


class BriefingVeloDeLaVeille(_BaseBriefings):
    def test_grosse_sortie_velo_compte_dans_la_fatigue(self):
        from src import agent_coach
        hier = (self.today - dt.timedelta(days=1)).isoformat()
        sortie = [{"start_date": f"{hier}T07:00:00Z", "start_date_local": f"{hier}T09:00:00Z", "suffer_score": 177, "sport_type": "Ride"}]
        vu = {}
        with mock.patch("src.charge.strava_recentes", return_value=sortie), \
                mock.patch.object(planif, "ajuster_jour", lambda forme, now: vu.setdefault("charge_veille", forme.get("charge_veille")) and []):
            agent_coach.run_agent_coach(conf=self.conf(19))
        self.assertGreaterEqual(vu["charge_veille"], 400)          # l'allègement voit la sortie vélo de la veille


class ChargeBorneeALaPeriode(unittest.TestCase):
    def test_activite_apres_la_periode_ignoree(self):
        from src import charge
        s = [{"start_date": "2026-11-10T16:00:00Z", "start_date_local": "2026-11-10T17:00:00Z", "suffer_score": 15, "sport_type": "Run"}]
        self.assertEqual(charge.ajouter_strava({}, [], s, dt.date(2026, 11, 9)), {})
