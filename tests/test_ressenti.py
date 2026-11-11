import unittest
from src.ressenti import enregistrer_rpe, dernier_rpe


class TestRessenti(unittest.TestCase):
    def test_ressenti_nominal(self):
        entree = enregistrer_rpe(7, "Bonnes sensations", "2026-11-12")
        self.assertEqual(entree["note"], 7)
        self.assertEqual(entree["commentaire"], "Bonnes sensations")

        recup = dernier_rpe("2026-11-12")
        self.assertIsNotNone(recup)
        self.assertEqual(recup["note"], 7)

    def test_ressenti_invalide(self):
        with self.assertRaises(ValueError):
            enregistrer_rpe(11)
        with self.assertRaises(ValueError):
            enregistrer_rpe(0)
