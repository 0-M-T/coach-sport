"""Briefings : réveil, montre oubliée, météo, repas, semaine, jour du semi."""
import datetime as dt
import unittest

from src import decision, meteo, semaine
from src.agent_coach import echeance_passee, montre_non_portee, nuit_disponible


def _prev(is_day=1, apparent=6, prob=10, mm=0.0, gust=20, uv=1, cloud=20):
    heures = [f"2026-11-10T{h:02d}:00" for h in range(0, 24)]
    n = len(heures)
    return {"hourly": {"time": heures, "apparent_temperature": [apparent] * n, "precipitation_probability": [prob] * n,
                       "precipitation": [mm] * n, "wind_speed_10m": [12] * n, "wind_gusts_10m": [gust] * n,
                       "uv_index": [uv] * n, "cloud_cover": [cloud] * n, "is_day": [is_day] * n},
            "daily": {"time": ["2026-11-10"], "sunrise": ["2026-11-10T07:48"], "sunset": ["2026-11-10T17:55"]}}


PARIS = __import__("zoneinfo").ZoneInfo("Europe/Paris")
SEANCE = "2026-11-10 07:30  [Sport] CAP: Seuil @ Route  — x.ics"


class Reveil(unittest.TestCase):
    def test_nuit_disponible(self):
        ok = {"sleep_hours": 8, "sleep_score": 85, "sleep_date": "2026-11-10"}
        self.assertTrue(nuit_disponible(ok, "2026-11-10"))
        self.assertFalse(nuit_disponible({**ok, "sleep_date": "2026-11-09"}, "2026-11-10"))  # nuit d'hier
        self.assertFalse(nuit_disponible({"sleep_hours": 8, "sleep_score": None}, "2026-11-10"))
        self.assertFalse(nuit_disponible({}, "2026-11-10"))

    def test_echeance(self):
        def d(h, m):
            return dt.datetime(2026, 11, 10, h, m, tzinfo=PARIS)
        self.assertFalse(echeance_passee(d(7, 0), SEANCE))   # séance 07:30, limite 07:10
        self.assertTrue(echeance_passee(d(7, 10), SEANCE))
        self.assertFalse(echeance_passee(d(10, 59), None))
        self.assertTrue(echeance_passee(d(11, 0), None))

class MontreOubliee(unittest.TestCase):
    def test_detection(self):
        self.assertTrue(montre_non_portee({"sleep_hours": None, "fc_nuit": 0, "fc_matin": 120}))
        self.assertFalse(montre_non_portee({"sleep_hours": None, "fc_nuit": 150, "fc_matin": 120}))  # portée, sommeil en attente
        self.assertFalse(montre_non_portee({"sleep_hours": None, "fc_nuit": 0, "fc_matin": 0}))      # pas synchronisée du tout
        self.assertFalse(montre_non_portee({"sleep_hours": 7.5, "fc_nuit": None, "fc_matin": None}))
        self.assertFalse(montre_non_portee({"sleep_hours": None}))

    def test_conseil_sans_donnees(self):
        self.assertIn("l'échauffement décide", decision.conseil_sans_donnees("CAP: Seuil 2x15m")[0])
        self.assertEqual(decision.conseil_sans_donnees("Footing EF"), [])
        self.assertEqual(decision.conseil_sans_donnees(None), [])

class BriefingExterieur(unittest.TestCase):
    RENFO = "2026-11-10 08:30  [Sport] Renfo B1, haut du corps et gainage  — a.ics"
    EF = "2026-11-10 18:30  [Sport] CAP: Footing EF 40 min au club ASM  — b.ics"
    ETIR = "2026-11-13 16:30  [Sport] Étirements D1, chaîne postérieure  — c.ics"

    def test_pas_de_meteo_pour_renfo_activation_etirements(self):
        from src.agent_coach import en_exterieur
        self.assertFalse(en_exterieur(self.RENFO))
        self.assertFalse(en_exterieur(self.ETIR))
        self.assertFalse(en_exterieur("2026-11-15 16:00  [Sport] Activation C1  — d.ics"))
        self.assertTrue(en_exterieur(self.EF))
        self.assertTrue(en_exterieur("2026-11-14 09:00  [Sport] CAP: Sortie longue 1h30  — e.ics"))

    def test_echeance_fixee_par_la_course_pas_par_le_renfo(self):
        from src.agent_coach import echeance_passee, premiere_course
        self.assertEqual(premiere_course([self.RENFO, self.EF]), self.EF)
        self.assertIsNone(premiere_course([self.RENFO]))
        maintenant = dt.datetime(2026, 11, 10, 8, 15, tzinfo=PARIS)    # 08:10 aurait suffi avec le renfo comme référence
        self.assertFalse(echeance_passee(maintenant, premiere_course([self.RENFO, self.EF])))
        self.assertTrue(echeance_passee(dt.datetime(2026, 11, 10, 11, 0, tzinfo=PARIS), premiere_course([self.RENFO, self.EF])))

class Meteo(unittest.TestCase):
    def test_fenetre_agrege_les_heures_recouvertes(self):
        w = meteo.fenetre(_prev(), "2026-11-10", "07:30", 90)
        self.assertEqual((w["debut"], w["fin"]), ("07:30", "09:00"))

    def test_seance_du_soir_dit_coucher_du_soleil(self):
        w = meteo.fenetre(_prev(is_day=0, apparent=10), "2026-11-10", "18:30")
        c = " ".join(meteo.conseils(w))
        self.assertIn("Séance de nuit (coucher du soleil 17:55)", c)
        self.assertNotIn("lever", c)

    def test_nuit_et_froid(self):
        c = " ".join(meteo.conseils(meteo.fenetre(_prev(is_day=0, apparent=-3), "2026-11-10", "07:30")))
        self.assertIn("frontale", c)
        self.assertIn("Grand froid", c)

    def test_soleil_pluie(self):
        c = " ".join(meteo.conseils(meteo.fenetre(_prev(uv=7, cloud=10, apparent=12), "2026-11-10", "10:00")))
        self.assertIn("lunettes et crème", c)
        c = " ".join(meteo.conseils(meteo.fenetre(_prev(prob=80, mm=1.5, cloud=90), "2026-11-10", "10:00")))
        self.assertIn("K-way", c)
        self.assertNotIn("lunettes", c)

class Nutrition(unittest.TestCase):
    EF = "2026-11-11 08:30  [Sport] CAP: Footing EF 35 min  — a.ics"
    EF_SOIR = "2026-11-10 18:30  [Sport] CAP: Footing EF 40 min au club ASM  — b.ics"
    SEUIL = "2026-11-12 18:30  [Sport] CAP: Seuil 3x3000m à 4'20/km  — c.ics"
    LONGUE = "2026-11-14 09:00  [Sport] CAP: Sortie longue 1h30 vallonnée  — d.ics"
    RENFO = "2026-11-10 08:30  [Sport] Renfo B1, haut du corps et gainage  — e.ics"

    def test_a_jeun_seulement_footing_court_du_matin_sans_fatigue(self):
        from src import nutrition as n
        self.assertTrue(n.a_jeun(self.EF))
        self.assertFalse(n.a_jeun(self.EF, fatigue=True))
        for l in (self.EF_SOIR, self.SEUIL, self.LONGUE, self.RENFO):
            self.assertFalse(n.a_jeun(l))

    def test_repas_jour(self):
        from src import nutrition as n
        self.assertTrue(any("à jeun" in x for x in n.repas_jour([self.EF])))
        self.assertFalse(any("à jeun" in x for x in n.repas_jour([self.EF], fatigue=True)))
        self.assertTrue(any("mange avant" in x for x in n.repas_jour([self.EF], fatigue=True)))
        self.assertTrue(any("06:30" in x for x in n.repas_jour([self.LONGUE])))
        self.assertTrue(any("glucides par heure" in x for x in n.repas_jour([self.LONGUE])))
        self.assertEqual(n.repas_jour([self.RENFO]), [])
        self.assertFalse(any("café" in x.lower() for x in n.repas_jour([self.EF, self.SEUIL, self.LONGUE])))

    def test_repas_veille(self):
        from src import nutrition as n
        self.assertTrue(any("Dîner riche" in x for x in n.repas_veille([self.SEUIL])))
        self.assertTrue(any("à jeun" in x for x in n.repas_veille([self.EF])))
        self.assertEqual(n.repas_veille([self.RENFO]), [])

class DescriptionRepas(unittest.TestCase):
    def test_repas_dans_la_description_des_seances_de_course(self):
        from src import planif
        from src.plan import Entree
        ef = Entree(2, "ef", "Footing EF 35 min", 40, "Facile.")
        self.assertIn("REPAS\n• Séance à jeun", planif.description(ef, "2026-11-11", "08:30"))
        seuil = Entree(3, "seuil", "Seuil 3x3000m", 80, "Seuil.")
        self.assertIn("\nREPAS\n•", planif.description(seuil, "2026-11-12", "18:30"))
        renfo = Entree(2, "renfo", "Renfo A2", 40, "Bas du corps.")
        self.assertNotIn("REPAS", planif.description(renfo, "2026-11-11", "16:00"))
        self.assertNotIn("REPAS", planif.description(ef))

class Semaine(unittest.TestCase):
    def test_charge(self):
        self.assertIn("+50 %", semaine.volume(30, 20))
        self.assertIn("prudence", semaine.volume(30, 20))
        self.assertNotIn("prudence", semaine.volume(21, 20))
        self.assertIn("pas de semaine précédente", semaine.volume(10, 0))

    def test_totaux(self):
        acts = [{"sport_type": "Run", "distance": 10000, "moving_time": 3000, "workout_type": 3, "total_elevation_gain": 50},
                {"sport_type": "Ride", "distance": 20000, "moving_time": 3000}]
        t = semaine.totaux(acts)
        self.assertEqual((t["n"], t["km"], t["seances"], len(t["autres"])), (1, 10.0, 1, 1))
        self.assertEqual(t["allure"], "5'00")

    def test_plan_suivi(self):
        prevues = ["2026-11-09 07:30  [Sport] Seuil  — a.ics", "2026-11-11 18:00  [Sport] Renfo  — b.ics"]
        lignes, faites = semaine.plan_suivi(prevues, [{"start_date_local": "2026-11-09T07:40:00Z"}])
        self.assertEqual(faites, 1)
        self.assertTrue(lignes[0].startswith("fait") and lignes[1].startswith("manqué"))

class CourseSemi(unittest.TestCase):
    def test_reperes_a_4_25(self):
        from src import course
        r = course.repere_5km()
        self.assertTrue(r[0].startswith("5 km : 0 h 22 min 05 s"))
        self.assertTrue(r[3].startswith("20 km : 1 h 28 min 20 s"))
        self.assertIn("1 h 33 min 11 s", r[4])
        self.assertEqual(course.heure_moins("09:00", 195), "05:45")

    def test_bilan_objectif_atteint_et_manque(self):
        from src import course
        laps = [{"distance": 5000, "elapsed_time": 1320}, {"distance": 5000, "elapsed_time": 1310}, {"distance": 5000, "elapsed_time": 1325},
                {"distance": 5000, "elapsed_time": 1330}, {"distance": 1100, "elapsed_time": 290}]
        act = {"distance": 21100, "elapsed_time": 5575, "moving_time": 5570, "average_heartrate": 172, "max_heartrate": 185}
        titre, corps = course.bilan(act, laps)
        self.assertIn("Objectif atteint : 1 min 05 s sous 1 h 34", corps)
        self.assertIn("5 km : 0 h 22 min 00 s", corps)
        self.assertIn("FC moyenne 172", corps)
        _, lent = course.bilan({**act, "elapsed_time": 5760}, laps)
        self.assertIn("Objectif manqué de 2 min 00 s", lent)
        _, juste = course.bilan({**act, "elapsed_time": 5610}, laps)
        self.assertIn("Objectif atteint : 30 s sous 1 h 34", juste)

    def test_messages_de_course(self):
        from src import course
        jour = course.message_jour_j(None, "09:00")
        self.assertIn("05:45 : réveil", jour)
        self.assertIn("Km 7 : 1 gel", jour)
        self.assertIn("relance", jour)
        self.assertIn("Dossard", course.message_veille(None, "09:00"))
        self.assertIn("Sommeil n/d/100, batterie corporelle 80/100", course.message_jour_j(None, forme={"sleep_score": None, "body_battery": 80}))

    def test_est_course(self):
        import datetime as d

        from src import course
        act = {"start_date_local": "2026-11-29T09:00:00Z", "distance": 21150, "sport_type": "Run"}
        self.assertTrue(course.est_course(act, d.date(2026, 11, 29)))
        self.assertFalse(course.est_course({**act, "distance": 12000}, d.date(2026, 11, 29)))
        self.assertFalse(course.est_course(act, d.date(2026, 11, 28)))


if __name__ == "__main__":
    unittest.main()


class ExercicesFrancais(unittest.TestCase):
    def test_tous_les_exercices_des_circuits_ont_un_nom_francais(self):
        from src import exercices_fr, garmin_renfo
        for circuit in garmin_renfo.CIRCUITS_GARMIN.values():
            for nom, _, _ in circuit:
                self.assertIn(nom, exercices_fr.FR)

    def test_fiche_du_renfo_a2(self):
        from src import planif
        from src.plan import renfo
        d = planif.description(renfo(0, "A2"), "2026-11-11", "16:00")
        self.assertIn("Single-leg Romanian Deadlift with Dumbbell = Soulevé de terre roumain à une jambe", d)
        self.assertIn("youtube.com", d)


class ChargesRenfo(unittest.TestCase):
    def test_charges_dans_la_seance_garmin_et_la_fiche(self):
        from src import garmin_renfo, planif
        from src.plan import renfo
        steps = [g["workoutSteps"][0] for g in garmin_renfo.charge_utile("A2", "x")["workoutSegments"][0]["workoutSteps"]]
        poids = {s["exerciseName"]: s.get("weightValue") for s in steps}
        self.assertEqual(poids["SINGLE_LEG_ROMANIAN_DEADLIFT_WITH_DUMBBELL"], 4.0)
        self.assertEqual(poids["DUMBBELL_REVERSE_LUNGE"], 4.0)
        self.assertIsNone(poids["HIP_RAISE"])
        d = planif.description(renfo(0, "A2"), "2026-11-11", "16:00")
        self.assertIn("1 seul haltère de 4 kg", d)
        self.assertIn("2 haltères de 2 kg chacun (un dans chaque main)", d)
        self.assertIn("sans poids", d)
