"""Accès partagés : Baïkal, texte, ntfy, métriques, webhook, sauvegarde, parcours, Home Assistant."""
import datetime as dt
import unittest

from src import baikal, meteo, texte


def _prev(is_day=1, apparent=6, prob=10, mm=0.0, gust=20, uv=1, cloud=20):
    heures = [f"2026-11-10T{h:02d}:00" for h in range(0, 24)]
    n = len(heures)
    return {"hourly": {"time": heures, "apparent_temperature": [apparent] * n, "precipitation_probability": [prob] * n,
                       "precipitation": [mm] * n, "wind_speed_10m": [12] * n, "wind_gusts_10m": [gust] * n,
                       "uv_index": [uv] * n, "cloud_cover": [cloud] * n, "is_day": [is_day] * n},
            "daily": {"time": ["2026-11-10"], "sunrise": ["2026-11-10T07:48"], "sunset": ["2026-11-10T17:55"]}}


PARIS = __import__("zoneinfo").ZoneInfo("Europe/Paris")


class Baikal(unittest.TestCase):
    def test_court_sans_uid(self):
        l = "2026-11-09 07:30  [Sport] CAP: Seuil 2x15m AS21 @ Route / Bitume plat  — e50e6aa9-4292.ics"
        self.assertEqual(baikal.court(l), "07:30 CAP: Seuil 2x15m AS21 (Route / Bitume plat)")
        self.assertEqual(baikal.lieu(l), "Route / Bitume plat")

    def test_court_sans_lieu(self):
        self.assertEqual(baikal.court("2026-11-10 18:00  [Sport] Renfo  — x.ics"), "18:00 Renfo")

class Texte(unittest.TestCase):
    def test_noms_en_francais(self):
        self.assertEqual(texte.nom_fr("Afternoon Mountain Bike Ride"), "Sortie VTT de l'après-midi")
        self.assertEqual(texte.nom_fr("Morning Run"), "Course du matin")
        self.assertEqual(texte.nom_fr("Footing avec Max"), "Footing avec Max")

    def test_bloc(self):
        self.assertEqual(texte.bloc("Météo", ["a", "b"], puces=True), "🌤️ MÉTÉO\n- a\n- b")
        self.assertEqual(texte.bloc("Inconnu", "x"), "INCONNU\nx")
        self.assertEqual(texte.bloc("Vide", [None, ""]), "")
        self.assertEqual(texte.bloc("Rien", None), "")
        self.assertEqual(texte.duree_h(8.41), "8 h 25")

    def test_resume_sans_plage_inutile(self):
        w = meteo.fenetre(_prev(apparent=10), "2026-11-10", "10:00")
        self.assertIn("Ressenti 10°C", meteo.resume(w))

class Ntfy(unittest.TestCase):
    def test_virgule_decimale(self):
        import re
        self.assertEqual(re.sub(r"(?<=\d)\.(?=\d)", ",", "13.16 km, 07:30, 4'25"), "13,16 km, 07:30, 4'25")

class Suivi(unittest.TestCase):
    def test_metriques_atomiques_et_dernier_succes_conserve(self):
        import tempfile
        from pathlib import Path

        from src import suivi
        with tempfile.TemporaryDirectory() as d:
            suivi.DIR = Path(d)
            suivi.ecrire("x", 0, 1.2, envoye=True)
            f = Path(d) / "coach_x.prom"
            premier = f.read_text()
            suivi.ecrire("x", 1, 0.5)  # échec : le dernier succès et le dernier envoi restent
            apres = f.read_text()
            def val(txt, k):
                return [l for l in txt.splitlines() if l.startswith(k)][0].rsplit(" ", 1)[1]
            self.assertEqual(val(premier, "coach_job_last_success"), val(apres, "coach_job_last_success"))
            self.assertEqual(val(premier, "coach_job_last_sent"), val(apres, "coach_job_last_sent"))
            self.assertEqual(val(apres, "coach_job_last_exit_code"), "1")
            self.assertFalse(list(Path(d).glob("*.tmp")))
            self.assertIn('{tache="x"}', premier)        # pas « job » : Prometheus le renommerait en exported_job
            self.assertNotIn('job="x"', premier)

class Webhook(unittest.TestCase):
    CONF = {"STRAVA_WEBHOOK_SECRET": "s3cret", "STRAVA_WEBHOOK_VERIFY": "verif", "STRAVA_ATHLETE_ID": "141445394"}

    def _t(self, m, url, corps=b""):
        from src.webhook import traiter
        return traiter(m, url, corps, self.CONF)

    def test_validation_abonnement(self):
        code, rep, go = self._t("GET", "/strava/s3cret?hub.mode=subscribe&hub.verify_token=verif&hub.challenge=abc")
        self.assertEqual((code, rep, go), (200, {"hub.challenge": "abc"}, False))
        self.assertEqual(self._t("GET", "/strava/s3cret?hub.mode=subscribe&hub.verify_token=faux&hub.challenge=abc")[0], 403)

    def test_mauvais_chemin_404(self):
        self.assertEqual(self._t("POST", "/strava/autre", b"{}")[0], 404)
        self.assertEqual(self._t("POST", "/", b"{}")[0], 404)

    def test_evenement_de_tom_declenche(self):
        ev = b'{"object_type":"activity","aspect_type":"create","owner_id":141445394,"object_id":1}'
        self.assertEqual(self._t("POST", "/strava/s3cret", ev), (200, {}, True))

    def test_evenements_ignores(self):
        for ev in (b'{"object_type":"activity","aspect_type":"create","owner_id":999}',
                   b'{"object_type":"athlete","aspect_type":"update","owner_id":141445394}',
                   b'{"object_type":"activity","aspect_type":"delete","owner_id":141445394}', b"pas du json"):
            code, _, go = self._t("POST", "/strava/s3cret", ev)
            self.assertFalse(go)
            self.assertIn(code, (200, 400))

    def test_sans_secret_configure_tout_refuse(self):
        from src.webhook import traiter
        self.assertEqual(traiter("GET", "/strava/", b"", {})[0], 404)

class Sauvegarde(unittest.TestCase):
    def test_archive_contenu_permissions_et_rotation(self):
        import datetime as d
        import tarfile
        import tempfile
        from pathlib import Path

        from src import sauvegarde
        with tempfile.TemporaryDirectory() as tmp:
            etat = Path(tmp) / "state"
            etat.mkdir()
            (etat / "coach-planif.json").write_text("{}")
            (etat / "autre.json").write_text("{}")
            sauvegarde.DEST = Path(tmp) / "dest"
            sauvegarde.FICHIERS = []
            for i in range(sauvegarde.GARDER + 3):
                cible = sauvegarde.sauvegarder(d.datetime(2026, 11, 1) + d.timedelta(days=i), etat)
            with tarfile.open(cible) as t:
                noms = t.getnames()
            self.assertIn("crontab.txt", noms)
            self.assertTrue(any(n.endswith("coach-planif.json") for n in noms))
            self.assertFalse(any(n.endswith("autre.json") for n in noms))     # seulement les fichiers du coach
            self.assertEqual(oct(cible.stat().st_mode & 0o777), "0o600")
            self.assertEqual(len(list(sauvegarde.DEST.glob("coach-*.tar.gz"))), sauvegarde.GARDER)

class Boucles(unittest.TestCase):
    ROUTES = [{"id": 1, "date": "2026-10-26", "km": 7.4, "dplus": 103, "nom": "a"}, {"id": 2, "date": "2025-02-19", "km": 8.5, "dplus": 242, "nom": "b"},
              {"id": 3, "date": "2024-08-19", "km": 16.4, "dplus": 134, "nom": "c"}]

    def test_suggestion_selon_la_seance(self):
        from src import boucles
        self.assertEqual(boucles.suggere("ef", 40, self.ROUTES)["id"], 1)         # 7,4 km pour 40 min, profil peu vallonné
        self.assertEqual(boucles.suggere("cotes", 55, self.ROUTES)["id"], 2)      # le plus vallonné à la bonne distance
        self.assertEqual(boucles.suggere("longue", 90, self.ROUTES)["id"], 3)     # 16,4 km pour 1 h 30
        self.assertIsNone(boucles.suggere("ef", 40, []))
        self.assertIsNone(boucles.suggere("seuil", 60, self.ROUTES))

    def test_pas_de_parcours_pour_trail_club_ou_fractionne(self):
        from src import boucles
        for ti in ("CAP: Pic du Rey : montée et descente", "CAP: Seuil 3x3000m à 4'20/km", "Club ASM : fractionné", "Rando avec bâtons 3 h 30"):
            self.assertIsNone(boucles.suggere_pour_titre(ti, self.ROUTES))
        self.assertIsNotNone(boucles.suggere_pour_titre("CAP: Footing EF 40 min", self.ROUTES))
        self.assertEqual(boucles.suggere_pour_titre("CAP: Sortie longue 1h30 vallonnée", self.ROUTES)["id"], 3)

    def test_le_briefing_du_matin_affiche_les_blocs_plan_et_parcours(self):
        from src import agent_coach
        sport = ["2026-11-14 09:00  [Sport] CAP: Sortie longue 1h30 vallonnée  — e.ics"]
        parcours = {"km": 16.4, "dplus": 210, "date": "2026-10-26", "id": 42}
        corps = agent_coach.message_matin(sport, None, {"sleep_hours": 8, "hrv_status": "BALANCED"}, False, None, None, parcours,
                                          ["2026-11-16|ef : mise à jour (08:30 -> 18:30)"])
        # un remplacement silencieux avait fait disparaître ces deux blocs
        self.assertIn("PLAN\n- 2026-11-16|ef : mise à jour", corps)
        self.assertIn("PARCOURS CONSEILLÉ\n16.4 km, +210 m, ta sortie du 26/10 (https://www.strava.com/activities/42)", corps)
        self.assertIn("variabilité cardiaque équilibrée", corps)

class CapteursHA(unittest.TestCase):
    def test_prochaine_seance_et_objectif(self):
        import datetime as d

        from src import ha
        lignes = ["2026-11-10 08:30  [Sport] CAP: Footing EF 40 min  — a.ics", "2026-11-09 07:30  [Sport] CAP: passée  — b.ics",
                  "2026-11-23 journée  [Sport] Journée  — c.ics"]
        self.assertEqual(ha.prochaine_seance(lignes, dt.datetime(2026, 11, 9, 20, 0, tzinfo=PARIS)), "mar 10/11 08:30 CAP: Footing EF 40 min")
        self.assertEqual(ha.prochaine_seance([], dt.datetime(2026, 11, 9, tzinfo=PARIS)), "Aucune séance planifiée")
        jours, nom = ha.objectif(d.date(2026, 11, 9))
        self.assertEqual((jours, "Semi" in nom), (20, True))
        self.assertEqual(ha.objectif(d.date(2030, 1, 1))[0], -1)


if __name__ == "__main__":
    unittest.main()


class FicheAgenda(unittest.TestCase):
    """Descriptions d'agenda : texte brut lisible partout, HTML pour Thunderbird."""

    def test_un_exercice_par_ligne(self):
        from src import fiche
        from src.plan import CIRCUITS
        a1 = fiche.lignes_renfo(CIRCUITS["A1"][2])
        self.assertEqual(a1[0], "Squat gobelet ou barre 3x8")
        self.assertTrue(a1[4].startswith("mollets : unilatéraux") and a1[4].endswith("3 s en descente)"))
        self.assertEqual(a1[5], "gainage latéral 2x30 s par côté")
        self.assertEqual(fiche.lignes_renfo(CIRCUITS["A2"][2])[:2], ["Charge réduite d'un tiers, 2 séries :", "soulevé de terre unilatéral 2x8"])

    def test_texte_et_html(self):
        from src import fiche
        sections = [("Séance", ["Intro :", "a 3x8", "b <2>"]), ("Vide", []), ("Repas", ["banane"])]
        txt = fiche.texte("Titre", sections, "pied")
        self.assertEqual(txt, "Titre\n\nSÉANCE\nIntro :\n• a 3x8\n• b <2>\n\nREPAS\n• banane\n\npied")
        h = fiche.en_html("Titre", sections, "pied")
        self.assertIn("<p><b>Séance</b></p><p>Intro :</p><ul><li>a 3x8</li><li>b &lt;2&gt;</li></ul>", h)
        self.assertNotIn("Vide", h)

    def test_description_de_seance(self):
        import datetime as d

        from src import planif
        from src.plan import ef
        e = planif.club_ef(ef(1, 40))
        txt = planif.description(e, "2026-11-10", "18:30")
        self.assertTrue(txt.startswith("Footing EF 40 min au club ASM\n\nSÉANCE\n• 40 min en aisance respiratoire"))
        self.assertNotIn("-- ", txt)
        self.assertIn("<li>40 min en aisance respiratoire</li>", planif.description_html(e, "2026-11-10", "18:30"))
        s, _ = planif.placer(ef(2, 35), d.date(2026, 11, 18), [], d.datetime(2026, 11, 15, 20, tzinfo=PARIS))
        self.assertTrue(s.html.startswith("<html><body>"))
        self.assertNotIn(s.html, s.empreinte)   # l'empreinte repose sur le texte, le HTML en découle

    def test_miroir_garmin_meme_format(self):
        from src import garmin_sync
        t = garmin_sync.generate_workout_description("Test Allure Semi (AS21 - 4:25/km)", "https://connect.garmin.com/modern/workout/1")
        self.assertIn("ÉCHAUFFEMENT · 20 MIN\n• 5 min de mobilité articulaire", t)
        self.assertNotIn("Mobilite", t)
