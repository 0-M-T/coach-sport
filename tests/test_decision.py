"""Règles de fatigue et signaux fins (decision.py)."""
import unittest

from src import decision


class Decision(unittest.TestCase):
    def test_fatigue_degrade_seance_dure(self):
        self.assertTrue(decision.conseil("CAP: Seuil 2x15m AS21", 5.5, "BALANCED", 5, 0))

    def test_ok_ne_change_rien(self):
        self.assertEqual(decision.conseil("CAP: Seuil 2x15m AS21", 7.5, "BALANCED", 5, 0), [])

    def test_vfc_mauvaise(self):
        self.assertTrue(decision.conseil("VMA 400m", 8, "LOW", 5, 0))
        self.assertTrue(decision.conseil("VMA 400m", 6.8, "UNBALANCED", 5, 0))   # déséquilibrée + sommeil court
        self.assertEqual(decision.conseil("VMA 400m", 8.5, "UNBALANCED", 5, 0), [])  # déséquilibrée seule : pas d'allègement

    def test_donnees_absentes_pas_de_faux_conseil(self):
        self.assertEqual(decision.conseil("Seuil", None, None, None, None), [])

    def test_vent_fort(self):
        self.assertTrue(decision.conseil("Vélo route", 8, "BALANCED", 40, 0))

class SignauxFatigue(unittest.TestCase):
    AUJOURDHUI = {"sleep_hours": 8.8, "hrv_status": "BALANCED", "bb_wake": 63, "fc_repos": 55, "fc_repos_7j": 52, "hrv_nuit": 50, "hrv_bas": 52, "charge_veille": 254}

    def test_le_cas_du_10_11_est_detecte(self):
        self.assertFalse(decision.fatigue(8.8, "BALANCED"))                       # l'ancienne règle ne voyait rien
        self.assertTrue(decision.fatigue(8.8, "BALANCED", self.AUJOURDHUI))
        self.assertEqual(len(decision.signaux(self.AUJOURDHUI)), 4)

    def test_un_seul_signal_ne_suffit_pas(self):
        for cle, val in (("bb_wake", 60), ("fc_repos", 56), ("hrv_nuit", 48), ("charge_veille", 300)):
            f = {"sleep_hours": 8, "hrv_status": "BALANCED", "bb_wake": 90, "fc_repos": 52, "fc_repos_7j": 52, "hrv_nuit": 60, "hrv_bas": 52, "charge_veille": 0, cle: val}
            self.assertEqual(len(decision.signaux(f)), 1, cle)
            self.assertFalse(decision.fatigue(8, "BALANCED", f), cle)

    def test_deux_signaux_suffisent_et_donnent_les_raisons(self):
        f = {"sleep_hours": 8, "hrv_status": "BALANCED", "bb_wake": 60, "hrv_nuit": 48, "hrv_bas": 52}
        self.assertTrue(decision.fatigue(8, "BALANCED", f))
        msg = decision.conseil("CAP: Seuil 3x3000m", 8, "BALANCED", 0, 0, f)[0]
        self.assertIn("Body Battery 60", msg)
        self.assertIn("VFC de la nuit 48 ms", msg)

    def test_body_battery_bas_apres_une_courte_nuit_n_est_pas_un_signal(self):
        # BB bas parce que la nuit était courte : déjà couvert par la règle du sommeil, pas compté deux fois
        self.assertEqual(decision.signaux({"sleep_hours": 6.0, "bb_wake": 50}), [])

    def test_donnees_absentes_pas_de_signal(self):
        self.assertEqual(decision.signaux(None), [])
        self.assertEqual(decision.signaux({}), [])
        self.assertFalse(decision.fatigue(None, None, {}))


if __name__ == "__main__":
    unittest.main()
