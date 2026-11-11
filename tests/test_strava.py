"""Strava : nom, description, débrief, recalage de l'agenda, club, chaussures, humour."""
import unittest

from src import planif, strava
from src.strava_enrich import GENERIC, caler_agenda, debriefing, proposer, workout_type


class Strava(unittest.TestCase):
    def test_pace(self):
        self.assertEqual(strava.pace(1000, 265), "4'25")
        self.assertEqual(strava.pace(0, 10), "N/A")

    def test_generic(self):
        self.assertTrue(GENERIC.match("Morning Run"))
        self.assertFalse(GENERIC.match("Footing avec Max"))

    def test_workout_type(self):
        self.assertEqual(workout_type("CAP: Seuil 2x15m AS21"), 3)
        self.assertEqual(workout_type("Footing EF"), 0)

    def test_proposer_respecte_nom_perso_et_description(self):
        act = {"name": "Footing avec Max", "distance": 10000, "moving_time": 3000}
        self.assertIsNone(proposer(act, "CAP: Seuil", []))
        act = {"name": "Morning Run", "distance": 10000, "moving_time": 3000, "description": "déjà"}
        self.assertNotIn("description", proposer(act, "CAP: Seuil", []))  # description de Tom jamais remplacée
        act = {"name": "Evening Run", "distance": 6000, "moving_time": 2000, "description": "Ef avec les potes", "workout_type": 0}
        self.assertEqual(proposer(act, None, []), {"name": "Course du soir"})

    def test_sans_seance_nom_selon_type(self):
        base = {"name": "Afternoon Run", "distance": 11000, "moving_time": 3600, "sport_type": "Run"}
        self.assertEqual(proposer({**base, "workout_type": 2}, None, [])["name"], "Sortie longue de l'après-midi")
        self.assertEqual(proposer({**base, "workout_type": 3}, None, [])["name"], "Séance de l'après-midi")
        self.assertIn("description", proposer(base, None, []))

    def test_velo_nom_seul(self):
        p = proposer({"name": "Lunch Ride", "distance": 9900, "moving_time": 1800, "sport_type": "Ride"}, None, [])
        self.assertEqual(p, {"name": "Sortie vélo du midi"})

    def test_proposer_seuil(self):
        act = {"name": "Morning Run", "distance": 13159.8, "moving_time": 3900, "average_heartrate": 160, "sport_type": "Run"}
        laps = [{"distance": 1000, "moving_time": 340}, {"distance": 1000, "moving_time": 268}, {"distance": 1000, "moving_time": 262},
                {"distance": 1000, "moving_time": 270}, {"distance": 1000, "moving_time": 340}, {"distance": 1000, "moving_time": 265}]
        p = proposer(act, "CAP: Seuil 2x15m AS21", laps)
        self.assertEqual(p["name"], "Seuil 2x15m AS21")
        self.assertEqual(p["workout_type"], 3)
        self.assertIn("Bloc 1", p["private_note"])
        self.assertIn("3.00 km", p["private_note"])  # 3 tours rapides consécutifs = 1 bloc
        self.assertNotIn("Bloc 2", p["private_note"])  # le dernier tour seul (1 km) est sous le seuil de 1,5 km

class Debrief(unittest.TestCase):
    ACT = {"name": "Morning Run", "distance": 13159.8, "moving_time": 3900, "average_heartrate": 160}

    def test_seuil_avec_chaussure_et_demain(self):
        laps = [{"distance": 1000, "moving_time": 268}] * 2 + [{"distance": 1000, "moving_time": 340}]
        titre, corps = debriefing(self.ACT, "CAP: Seuil 2x15m AS21", laps, "18:00 Renfo", {})
        self.assertEqual(titre, "Séance terminée : Seuil 2x15m AS21")
        self.assertIn("Bloc 1", corps)
        self.assertNotIn("CHAUSSURES", corps)  # l'usure a sa notification dédiée
        self.assertIn("DEMAIN\n18:00 Renfo", corps)

    def test_ef_fc_trop_haute(self):
        _, corps = debriefing(self.ACT, "Footing EF", [], None, {})
        self.assertIn("au-dessus de la limite de 145", corps)
        self.assertIn("Trop rapide pour de l'endurance", corps)
        self.assertIn("Repos ou séance libre", corps)

    def test_footing_lent_a_la_bonne_fc_est_reussi(self):
        # le 10/11 : 6,81 km à 5'53/km, FC 138 (max 149) ; la notification le faisait passer pour raté
        act = {"id": 20940000000, "name": "Afternoon Run", "sport_type": "Run", "distance": 6810, "moving_time": 2405,
               "average_heartrate": 138.5, "max_heartrate": 149}
        titre, corps = debriefing(act, "CAP: Footing EF 40 min", [], "08:30 CAP: Footing EF 35 min", {})
        self.assertIn("PRÉVU\nFooting EF 40 min\nFC sous 145, allure repère 5'15 à 5'35/km", corps)
        self.assertIn("VERDICT\nSéance réussie : endurance respectée, 40 min comme prévu", corps)
        self.assertIn("6.81 km à 5'53/km, FC moyenne 138 bpm en 40 min (FC max 149)", corps)
        self.assertIn("plus lente que le repère de 5'15 à 5'35 : normal, la FC passe avant l'allure", corps)
        self.assertIn("08:30 Footing EF 35 min", corps)
        self.assertNotIn("CAP:", corps)
        self.assertNotIn("sous la cible", corps)
        p = proposer({**act, "description": None}, "CAP: Footing EF 40 min", [])
        self.assertTrue(p["private_note"].startswith("Séance prévue : Footing EF 40 min\nSéance réussie : endurance respectée"))
        phrase = p["description"]
        self.assertNotIn("\n", phrase)   # description publique : la phrase d'humour seule
        from src import humour
        self.assertIn(humour.sans_smiley(phrase), [x.format(fc="138") for x in humour.EF_REUSSIE])

    def test_seance_raccourcie_dite(self):
        act = {"id": 3, "name": "Morning Run", "sport_type": "Run", "distance": 5000, "moving_time": 1800, "average_heartrate": 140}
        _, corps = debriefing(act, "CAP: Footing EF 45 min", [], None, {})
        self.assertIn("Séance réussie : endurance respectée, 30 min sur 45 prévues", corps)

class Agenda(unittest.TestCase):
    ACT = {"id": 1, "start_date_local": "2026-11-09T09:14:41Z", "moving_time": 3900, "elapsed_time": 4200}

    def _avec(self, lignes, apply=True):
        import src.strava_enrich as se
        appels = []
        orig = (se.baikal.lister, se.baikal.deplacer)
        self.addCleanup(lambda: (setattr(se.baikal, "lister", orig[0]), setattr(se.baikal, "deplacer", orig[1])))
        se.baikal.lister = lambda d, *a, **k: lignes
        se.baikal.deplacer = lambda i, d, f: appels.append((i, d, f))
        return caler_agenda(self.ACT, {}, apply), appels

    def test_deplace_sur_heure_reelle(self):
        (etat, note), appels = self._avec(["2026-11-09 07:30  [Sport] CAP: Seuil 2x15m AS21  — abc.ics"])
        self.assertEqual(etat, "deplace")
        self.assertEqual(appels, [("abc.ics", "2026-11-09T09:14", "2026-11-09T10:24")])
        self.assertIn("07:30 à 09:14", note)

    def test_a_l_heure_ne_touche_rien(self):
        (etat, _), appels = self._avec(["2026-11-09 09:10  [Sport] CAP: Footing  — abc.ics"])
        self.assertEqual((etat, appels), ("ok", []))

    def test_evenement_non_sportif_ignore(self):
        (etat, _), appels = self._avec(["2026-11-09 10:00  [Sport] Étude posturale  — abc.ics"])
        self.assertEqual((etat, appels), ("aucun", []))

    def test_dry_run_n_ecrit_pas(self):
        (etat, _), appels = self._avec(["2026-11-09 07:30  [Sport] CAP: Seuil  — abc.ics"], apply=False)
        self.assertEqual((etat, appels), ("deplace", []))

class Humour(unittest.TestCase):
    def test_phrase_selon_ecart(self):
        from src import humour
        act = {"id": 2, "distance": 13000}
        s = humour.sans_smiley
        self.assertIn(s(humour.phrase(act, 1, 3)), humour.PILE)
        self.assertIn(s(humour.phrase(act, -6, 3)), [x.format(e="6") for x in humour.TROP_VITE])
        self.assertIn(s(humour.phrase(act, 5, 3)), [x.format(e="5") for x in humour.TROP_LENT])

    def test_jamais_deux_fois_la_meme_phrase(self):
        from src import humour
        deja = {}
        phrases = [humour.sans_smiley(humour.phrase({"id": i, "distance": 10000}, None, 0, deja)) for i in range(len(humour.DEFAUT))]
        self.assertEqual(len(set(phrases)), len(humour.DEFAUT))           # 10 sorties : 10 phrases différentes
        self.assertEqual(humour.sans_smiley(humour.phrase({"id": 3, "distance": 10000}, None, 0, deja)), phrases[3])   # même activité : même phrase
        onzieme = humour.sans_smiley(humour.phrase({"id": 99, "distance": 10000}, None, 0, deja))
        self.assertEqual(onzieme, phrases[0])                             # liste épuisée : la plus anciennement utilisée revient

    def test_noms_de_balade_uniques(self):
        from src import humour
        deja = {}
        noms = [humour.nom_balade({"id": i * 7}, deja) for i in range(len(humour.BALADE))]
        self.assertEqual(len(set(noms)), len(humour.BALADE))
        self.assertIn("Promenade du tigre", humour.BALADE)

    def test_ef_coeur_et_stable(self):
        from src import humour
        act = {"id": 7, "distance": 10000, "average_heartrate": 158}
        self.assertIn("158 bpm", humour.phrase(act, None, 0))
        self.assertEqual(humour.phrase(act, None, 0), humour.phrase(act, None, 0))  # déterministe

    def test_longue_et_courte(self):
        from src import humour
        self.assertIn("20 km", humour.phrase({"id": 0, "distance": 20000}, None, 2))
        self.assertTrue(humour.phrase({"id": 1, "distance": 3000}, None, 0))

class ClubGeoloc(unittest.TestCase):
    ACT = {"start_latlng": [43.3157, -0.3708], "athlete_count": 6, "start_date_local": "2026-09-15T18:27:00Z"}   # mardi

    def test_reconnu_par_la_localisation(self):
        from src import club
        self.assertTrue(club.au_club(self.ACT))
        self.assertFalse(club.au_club({**self.ACT, "athlete_count": 1}))                          # seul : pas le club
        self.assertFalse(club.au_club({**self.ACT, "start_latlng": [43.33, -0.35]}))              # ailleurs à Pau
        self.assertFalse(club.au_club({**self.ACT, "start_date_local": "2026-09-16T18:27:00Z"}))  # mercredi : pas de séance
        self.assertTrue(club.au_club({**self.ACT, "start_date_local": "2026-09-12T09:50:00Z"}))   # samedi matin

    def test_fractionne_ou_footing(self):
        from src import club
        footing = [{"distance": 1000, "moving_time": 330}] * 8
        frac = [{"distance": 1000, "moving_time": 340}, {"distance": 400, "moving_time": 85}, {"distance": 400, "moving_time": 85},
                {"distance": 400, "moving_time": 84}, {"distance": 400, "moving_time": 86}, {"distance": 1000, "moving_time": 345},
                {"distance": 400, "moving_time": 130}]
        self.assertFalse(club.est_fractionne(footing))
        self.assertTrue(club.est_fractionne(frac))

    def test_club_detecte_allege_le_lendemain(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            planif.STATE = Path(d) / "p.json"
            planif.enregistrer_club("2026-11-10", True)
            planif.baikal.lister = lambda *a, **k: []
            g = planif.groupes_range("2026-11-11", "2026-11-20")      # la veille (10/11) est incluse
            self.assertTrue(g["2026-11-10"]["dure"])

class Materiel(unittest.TestCase):
    def test_niveaux(self):
        from src.materiel import niveau
        self.assertEqual([niveau(k, 700, 750) for k in (300, 700, 726, 750, 900)], [0, 700, 700, 750, 750])

    def test_heure_matin(self):
        from src.garmin_sync import heure_seance
        self.assertEqual(heure_seance("07:30", {}), "08:30")
        self.assertEqual(heure_seance("18:00", {}), "18:00")
        self.assertEqual(heure_seance("07:30", {"COACH_HEURE_MATIN": "09:00"}), "09:00")


if __name__ == "__main__":
    unittest.main()


class BaladeDuChien(unittest.TestCase):
    def setUp(self):
        import json
        import tempfile
        from pathlib import Path
        from unittest import mock

        from src import boucles
        d = Path(tempfile.mkdtemp())
        f = d / "boucles.json"
        f.write_text(json.dumps({"maison": [43.36, -0.315], "routes": []}))
        p = mock.patch.object(boucles, "CATALOGUE", f)
        p.start()
        self.addCleanup(p.stop)

    def test_marche_partie_de_la_maison(self):
        act = {"name": "Afternoon Walk", "sport_type": "Walk", "start_latlng": [43.3612, -0.3141], "distance": 3200, "moving_time": 2400}
        self.assertIn(proposer(act, None, [])["name"], __import__("src.humour", fromlist=["BALADE"]).BALADE)

    def test_autres_marches_et_courses_inchangees(self):
        loin = {"name": "Afternoon Walk", "sport_type": "Walk", "start_latlng": [43.30, -0.37], "distance": 3200, "moving_time": 2400}
        self.assertEqual(proposer(loin, None, []), {"name": "Marche de l'après-midi"})
        sans_gps = {"name": "Afternoon Walk", "sport_type": "Walk", "start_latlng": [], "distance": 1180, "moving_time": 1725}
        self.assertIn(proposer(sans_gps, None, [])["name"], __import__("src.humour", fromlist=["BALADE"]).BALADE)
        rando = {"name": "Afternoon Hike", "sport_type": "Hike", "start_latlng": [], "distance": 9000, "moving_time": 9000}
        self.assertEqual(proposer(rando, None, [])["name"], "Randonnée de l'après-midi")
        nommee = {"name": "Tour du lac", "sport_type": "Walk", "start_latlng": [43.3612, -0.3141], "distance": 3200, "moving_time": 2400}
        self.assertIsNone(proposer(nommee, None, []))      # nom écrit par Tom : jamais remplacé
        course = {"name": "Afternoon Run", "sport_type": "Run", "start_latlng": [43.3612, -0.3141], "distance": 5000, "moving_time": 1500}
        self.assertNotIn(proposer(course, None, [])["name"], __import__("src.humour", fromlist=["BALADE"]).BALADE)


class NotePrivee(unittest.TestCase):
    ACT = {"id": 5, "name": "Morning Run", "sport_type": "Run", "distance": 8000, "moving_time": 2600, "average_heartrate": 139}

    def test_humour_en_public_recap_en_prive(self):
        p = proposer(self.ACT, "CAP: Footing EF 40 min", [])
        self.assertNotIn("Bilan", p["description"])
        self.assertIn("Bilan : 8.00 km", p["private_note"])

    def test_textes_de_tom_jamais_remplaces(self):
        p = proposer({**self.ACT, "description": "Avec les copains", "private_note": "Genou un peu raide"}, "CAP: Footing EF 40 min", [])
        self.assertNotIn("description", p)
        self.assertNotIn("private_note", p)
        p = proposer({**self.ACT, "description": "Avec les copains"}, "CAP: Footing EF 40 min", [])
        self.assertNotIn("description", p)
        self.assertIn("Séance réussie", p["private_note"])     # la note privée vide reçoit quand même le récap


class HumourModele(unittest.TestCase):
    def test_meme_blague_avec_un_autre_chiffre_comptee_comme_utilisee(self):
        from src import humour
        deja = {humour.FC_HAUTE[0].format(fc="152"): "1"}
        p = humour.phrase({"id": 0, "distance": 8000, "average_heartrate": 147}, None, 0, deja)
        self.assertNotRegex(p, r"^Endurance fondamentale à \\d+ bpm : mon coeur n'a pas lu le plan")
        self.assertIn("147", p)


class ChampsAuto(unittest.TestCase):
    def test_balade_renfo_et_velo_masques_du_fil(self):
        from src.strava_enrich import champs_auto
        self.assertEqual(champs_auto({"sport_type": "Walk", "start_latlng": [1, 2]}), {"hide_from_home": True})
        self.assertEqual(champs_auto({"sport_type": "WeightTraining"}), {})      # renfo : reste dans le fil (exercices détaillés)
        self.assertEqual(champs_auto({"sport_type": "Yoga"}), {"hide_from_home": True})
        self.assertEqual(champs_auto({"sport_type": "Ride", "start_latlng": []}), {"hide_from_home": True, "trainer": True})
        self.assertEqual(champs_auto({"sport_type": "Ride", "start_latlng": [1, 2]}), {})      # vraie sortie vélo : visible
        self.assertEqual(champs_auto({"sport_type": "Run", "start_latlng": [1, 2]}), {})
        self.assertEqual(champs_auto({"sport_type": "Walk", "hide_from_home": True}), {})      # déjà fait (ou choix de Tom)

    def test_paire_du_plan(self):
        from src.strava_enrich import champs_auto, paire_strava
        paires = {"g1": "Adidas Adizero Evo SL", "g2": "Adidas Adizero Evo SL 2", "g3": "ASICS Metaspeed Sky Paris", "g4": "Scott Kinabalu 3"}
        self.assertEqual(paire_strava("Adidas Evo SL (paire 2)", paires), "g2")
        self.assertEqual(paire_strava("ASICS Metaspeed Sky Paris", paires), "g3")
        self.assertIsNone(paire_strava("Adidas Evo SL", paires))          # deux paires possibles : on ne choisit pas
        self.assertIsNone(paire_strava("NNormal Kjerag", paires))         # inconnue sur Strava
        self.assertIsNone(paire_strava(None, paires))
        self.assertEqual(champs_auto({"sport_type": "Run", "gear_id": "g1"}, "g2"), {"gear_id": "g2"})
        self.assertEqual(champs_auto({"sport_type": "Run", "gear_id": "g2"}, "g2"), {})

    def test_tag_avec_un_animal_reconnu(self):
        from src.strava_enrich import balade_du_chien
        self.assertTrue(balade_du_chien({"sport_type": "Walk", "start_latlng": [43.0, -0.5], "tags": ["WithPet"]}))

    def test_velo_nomme_sans_type_de_seance_de_course(self):
        p = proposer({"name": "Afternoon Ride", "sport_type": "Ride", "distance": 0, "moving_time": 1200, "start_latlng": []},
                     "Vélo d'appartement 20 min (récupération)", [])
        self.assertEqual(p, {"name": "Vélo d'appartement 20 min (récupération)"})


class EntreeDuPlan(unittest.TestCase):
    def test_retrouve_la_seance_et_ses_chaussures(self):
        from src import planif
        e = planif.entree_du_plan("2026-11-12", "CAP: Seuil 3x3000m à 4'20/km")
        self.assertEqual((e.kind, e.chaussures), ("seuil", "Adidas Evo SL (paire 2)"))
        self.assertEqual(planif.entree_du_plan("2026-11-10", "CAP: Footing EF 40 min au club ASM").kind, "ef")
        self.assertIsNone(planif.entree_du_plan("2026-11-12", "Dentiste"))


class PairePrevue(unittest.TestCase):
    PAIRES = {"g28765917": "Adidas Evo Sl Adidas 2", "g24872534": "Adidas Adizero Evo SL Adidas", "g24426686": "ASICS MetaSpeed Sky Paris Asics",
              "g32394468": "Scott Kinabalu Trail Scott", "g30191207": "NNormal KJerag NNormal"}

    def _paire(self, date, titre, km_ancienne=600):
        from unittest import mock

        from src import strava, strava_enrich
        with mock.patch.object(strava, "call", lambda t, chemin: {"distance": km_ancienne * 1000}):
            return strava_enrich.paire_prevue({"sport_type": "Run"}, date, titre, {}, self.PAIRES, "t")

    def test_paire_selon_la_seance(self):
        self.assertEqual(self._paire("2026-11-12", "CAP: Seuil 3x3000m à 4'20/km"), "g28765917")     # qualité : paire 2
        self.assertEqual(self._paire("2026-11-11", "CAP: Footing EF 35 min"), "g24872534")             # footing : l'ancienne
        self.assertEqual(self._paire("2026-11-29", None), "g24426686")                                 # semi : Metaspeed
        self.assertEqual(self._paire("2026-11-21", "CAP: Sortie 1h05 avec 2x8' à allure semi"), "g24426686")   # essai à allure de course : Metaspeed

    def test_ancienne_usee_passe_a_la_paire_2(self):
        self.assertEqual(self._paire("2026-11-11", "CAP: Footing EF 35 min", km_ancienne=752), "g28765917")

    def test_trail(self):
        from src import plan, strava_enrich
        self.assertEqual(strava_enrich.paire_strava(plan.NNORMAL, self.PAIRES), "g30191207")
        self.assertEqual(strava_enrich.paire_strava(plan.SCOTT, self.PAIRES), "g32394468")


class RenfoNomme(unittest.TestCase):
    def test_nom_de_l_agenda(self):
        from unittest import mock

        from src import strava_enrich
        lignes = ["2026-11-10 17:45  [Sport] Renfo B1, haut du corps et gainage  — a.ics", "2026-11-10 16:50  [Sport] CAP: Footing EF 40 min  — b.ics"]
        with mock.patch.object(strava_enrich.baikal, "lister", return_value=lignes):
            titre = strava_enrich.renfo_du_jour("2026-11-10", "17:52")
        self.assertEqual(titre, "Renfo B1, haut du corps et gainage")
        p = proposer({"name": "Afternoon Weight Training", "sport_type": "WeightTraining", "distance": 0, "moving_time": 2100}, titre, [])
        self.assertEqual(p, {"name": "Renfo B1, haut du corps et gainage"})


class Smileys(unittest.TestCase):
    def test_phrase_avec_smiley_adapte(self):
        from src import humour
        p = humour.phrase({"id": 9, "distance": 8000, "average_heartrate": 152}, None, 0, {})
        self.assertIn(p.rsplit(" ", 1)[1], humour.SMILEYS["fc_haute"])
        self.assertIn(humour.sans_smiley(p), [x.format(fc="152") for x in humour.FC_HAUTE])

    def test_la_memoire_ignore_le_smiley(self):
        from src import humour
        deja = {}
        humour.phrase({"id": 1, "distance": 10000}, None, None, deja)
        self.assertTrue(all(k == humour.sans_smiley(k) for k in deja))      # la mémoire garde la blague, sans smiley
        self.assertEqual(humour.sans_smiley("Bouclé. 😮‍💨"), "Bouclé.")
        self.assertEqual(humour.sans_smiley("Pile sur le 4'25."), "Pile sur le 4'25.")

    def test_smileys_varies(self):
        from src import humour
        self.assertGreater(len({humour.smiley("defaut", i) for i in range(0, 30)}), 3)
