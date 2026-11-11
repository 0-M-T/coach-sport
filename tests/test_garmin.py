"""Garmin : forme, séances de course et de renforcement sur la montre (faux client, jamais le vrai compte)."""
import unittest

from src import decision, planif


class FormeGarmin(unittest.TestCase):
    """garmin.forme avec un faux client : une erreur d'import ou de champ ne doit plus passer inaperçue (elle a cassé le rejeu le 2026-11-10)."""

    class Faux:
        def get_user_summary(self, d): return {"bodyBatteryAtWakeTime": 63, "bodyBatteryMostRecentValue": 63, "restingHeartRate": 55, "lastSevenDaysAvgRestingHeartRate": 52}
        def get_sleep_data(self, d): return {"dailySleepDTO": {"sleepTimeSeconds": 31680, "calendarDate": "2026-11-10", "sleepScores": {"overall": {"value": 81}}}}
        def get_hrv_data(self, d): return {"hrvSummary": {"status": "BALANCED", "lastNightAvg": 50, "baseline": {"balancedLow": 52}}}
        def get_heart_rates(self, d): return {"heartRateValues": []}
        def get_activities_by_date(self, a, b): return [{"activityTrainingLoad": 254.3}]

    def test_champs_fins(self):
        from src import garmin
        f = garmin.forme(self.Faux(), "2026-11-10")
        self.assertEqual((f["bb_wake"], f["fc_repos"], f["fc_repos_7j"], f["hrv_nuit"], f["hrv_bas"]), (63, 55, 52, 50, 52))
        self.assertAlmostEqual(f["charge_veille"], 254.3)
        self.assertEqual(f["sleep_hours"], 8.8)
        self.assertTrue(decision.fatigue(f["sleep_hours"], f["hrv_status"], f))      # le cas du 10/11 de bout en bout

    def test_charges_prechargees_et_sans_charge(self):
        from src import garmin
        self.assertEqual(garmin.forme(self.Faux(), "2026-11-10", charges={"2026-11-09": 200})["charge_veille"], 200)
        self.assertIsNone(garmin.forme(self.Faux(), "2026-11-10", avec_charge=False)["charge_veille"])

class SeancesCourse(unittest.TestCase):
    def test_charge_utile_seuil(self):
        from src import garmin_course as gc
        d = gc.charge_utile([("w", 1200), ("rep", 3, [("id", 3000, 260, 3), ("r", 150)]), ("c", 600)], "Seuil")
        steps = d["workoutSegments"][0]["workoutSteps"]
        self.assertEqual([s["stepType"]["stepTypeKey"] for s in steps], ["warmup", "repeat", "cooldown"])
        interne = steps[1]["workoutSteps"]
        self.assertEqual(steps[1]["numberOfIterations"], 3)
        self.assertEqual(interne[0]["endCondition"]["conditionTypeKey"], "distance")
        self.assertAlmostEqual(interne[0]["targetValueOne"], 1000 / 263, places=3)   # vitesse lente
        self.assertAlmostEqual(interne[0]["targetValueTwo"], 1000 / 257, places=3)   # vitesse rapide
        self.assertTrue(all(s["childStepId"] == steps[1]["stepOrder"] for s in interne))
        self.assertEqual(len({s["stepOrder"] for s in steps} | {s["stepOrder"] for s in interne}), 5)  # ordres uniques
        self.assertEqual(d["estimatedDurationInSecs"], 1200 + 3 * (3 * 260 + 150) + 600)

    def test_etape_inconnue_refusee(self):
        from src import garmin_course as gc
        with self.assertRaises(ValueError):
            gc.charge_utile([("zz", 1)], "x")

    def test_toutes_les_seances_du_plan_se_construisent(self):
        from src import garmin_course as gc
        from src.plan import SEMAINES
        for es in SEMAINES.values():
            for e in es:
                if e.etapes:
                    gc.charge_utile(e.etapes, e.titre)

class GarminRenfo(unittest.TestCase):
    def test_tous_les_exercices_existent_et_les_titres_correspondent(self):
        from src import garmin_renfo as gr
        from src.plan import CIRCUITS
        for code in gr.CIRCUITS_GARMIN:
            p = gr.charge_utile(code, "x")
            self.assertGreater(len(p["workoutSegments"][0]["workoutSteps"]), 3)
            self.assertEqual(gr.code_de(CIRCUITS[code][0]), code)  # le titre de l'agenda retrouve le circuit

    def test_synchro_cree_programme_et_deplace(self):
        from src import garmin_renfo as gr

        class Faux:
            def __init__(self): self.up, self.sched, self.unsched, self.dele, self.biblio = [], [], [], [], []
            def get_workouts(self, a, b): return self.biblio
            def upload_workout(self, d):
                self.up.append(d)
                return {"workoutId": 100 + len(self.up)}

            def schedule_workout(self, w, date):
                self.sched.append((w, date))
                return {"workoutScheduleId": 900 + len(self.sched)}

            def unschedule_workout(self, s): self.unsched.append(s)
            def delete_workout(self, w): self.dele.append(w)
        c = Faux()
        etat = {"evenements": {"e1": {"cle": "2026-11-11|renfo", "date": "2026-11-11", "heure": "19:00", "titre": "Renfo A1, bas du corps"}}}
        gr.synchroniser(c, etat, "2026-11-10")
        self.assertEqual(c.sched, [(101, "2026-11-11")])
        gr.synchroniser(c, etat, "2026-11-10")                       # second passage : rien de plus
        self.assertEqual((len(c.up), len(c.sched)), (1, 1))
        etat["evenements"]["e1"]["date"] = "2026-11-12"              # l'agenda a déplacé la séance
        gr.synchroniser(c, etat, "2026-11-10")
        self.assertEqual((c.unsched, c.sched[-1]), ([901], (101, "2026-11-12")))
        del etat["evenements"]["e1"]                                  # séance retirée du plan
        gr.synchroniser(c, etat, "2026-11-10")
        self.assertEqual(c.unsched[-1], 902)
        self.assertEqual(etat["garmin"]["programmes"], {})

    def test_bibliotheque_filtre_hiit_sauts_et_durees(self):
        from src import garmin_renfo as gr
        def A(nom, sport, duree, sur=True):
            return {"nom": nom, "sport": sport, "duree": duree, "sur": sur}
        self.assertEqual(gr.classer(A("Flex Your Torso", "pilates", 5)), "etirements")
        self.assertEqual(gr.classer(A("After-Work Yoga", "yoga", 70)), None)                      # trop long pour un créneau de 20 min
        self.assertEqual(gr.classer(A("15-Minute Ab Burner", "pilates", 15)), "activation")      # gainage : activation, pas étirements
        self.assertEqual(gr.classer(A("Get Slope Strong", "strength_training", 20, sur=False)), None)   # sauts trop près d'un objectif
        self.assertEqual(gr.classer(A("Get Slope Strong", "strength_training", 20, sur=False), impact_ok=True), "activation")   # loin d'un objectif
        self.assertEqual(gr.classer(A("5-minute All Out", "hiit", 5)), None)                      # HIIT exclu
        self.assertEqual(gr.classer(A("Mobility Flow", "mobility", 12)), "etirements")

    def test_impact_autorise_seulement_loin_d_un_objectif(self):
        import datetime as d

        from src import garmin_renfo as gr
        self.assertFalse(gr.impact_autorise(d.date(2026, 11, 9)))      # semi dans 20 jours
        self.assertTrue(gr.impact_autorise(d.date(2026, 12, 7)))       # La Rhune dans 47 jours
        self.assertFalse(gr.impact_autorise(d.date(2027, 1, 5)))       # La Rhune dans 18 jours
        self.assertTrue(gr.impact_autorise(d.date(2027, 2, 1)))        # 10 km dans 83 jours
        self.assertEqual(gr.classer({"nom": "x", "sport": "hiit", "duree": 10, "sur": True}, impact_ok=True), None)   # HIIT toujours exclu

    def test_circuits_de_mollets_lestes_et_assis(self):
        from src import garmin_renfo as gr
        from src.plan import CIRCUITS
        for code in ("A1", "A2", "A3"):
            noms = [x[0] for x in gr.CIRCUITS_GARMIN[code]]
            self.assertIn("Single-leg Standing Dumbbell Calf Raise", noms)
            self.assertIn("Seated Calf Raise", noms)
            self.assertIn("mollets", CIRCUITS[code][2].lower())
            gr.charge_utile(code, "x")
        self.assertIn("Mollets : ils se renforcent", planif.description(__import__("src.plan", fromlist=["renfo"]).renfo(1, "A1")))

    def test_animees_utilise_les_analyses_et_exclut_les_seances_du_coach(self):
        from src import garmin_renfo as gr
        biblio = [{"workoutId": 7, "workoutName": "Copy of Flex Your Torso"}, {"workoutId": 8, "workoutName": "Copy of 5-minute All Out"},
                  {"workoutId": 9, "workoutName": "Renfo A1"}]
        analyses = {"7": {"nom": "Copy of Flex Your Torso", "sport": "pilates", "duree": 5, "sur": True},
                    "8": {"nom": "Copy of 5-minute All Out", "sport": "hiit", "duree": 5, "sur": False},
                    "9": {"nom": "Renfo A1", "sport": "strength_training", "duree": 35, "sur": True}}
        r = gr.animees(biblio, {9}, analyses)
        self.assertEqual([w["workoutId"] for w in r["etirements"]], [7])
        self.assertEqual(r["activation"], [])
        self.assertEqual(gr.animees(biblio, set(), None), {"etirements": [], "activation": []})   # sans analyse, rien n'est programmé
        self.assertEqual(gr.choisir(r["etirements"], "2026-11-13")["workoutId"], 7)
        self.assertIsNone(gr.choisir([], "2026-11-13"))


if __name__ == "__main__":
    unittest.main()


class SeancesDEssai(unittest.TestCase):
    def test_seance_test_jamais_programmee(self):
        from src import garmin_renfo as gr
        a = {"nom": "x", "sport": "yoga", "duree": 15, "sur": True}
        ws = [{"workoutId": 1, "workoutName": "TEST animation : Renfo A1 (ne pas programmer)"}, {"workoutId": 2, "workoutName": "Copy of Extend Your Body"},
              {"workoutId": 3, "workoutName": "Mobilité (ne pas programmer)"}]
        out = gr.animees(ws, set(), {"1": a, "2": a, "3": a})
        self.assertEqual([w["workoutId"] for w in out["etirements"]], [2])


class Animation(unittest.TestCase):
    def test_circuits_portent_les_champs_d_animation(self):
        from src import garmin_renfo as gr
        for code in gr.CIRCUITS_GARMIN:
            c = gr.charge_utile(code, f"Renfo {code}")
            self.assertEqual((c["workoutProvider"], c["workoutSourceId"]), ("Garmin", "GGe2df9"), code)
