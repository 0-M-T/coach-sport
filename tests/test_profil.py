import unittest
from pathlib import Path
import tempfile
import yaml
from src.profil import Profil, sauvegarder_profil
from src import chemins


class TestProfil(unittest.TestCase):
    def test_profil_defaut(self):
        p = Profil()
        self.assertEqual(p.prenom, "Athlète")
        self.assertEqual(p.depart_coords, (43.3515, -0.3120, "Maison"))
        self.assertIn("seuil_bas", p.chaussures)

    def test_profil_sauvegarder_charger(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "profile.yaml"
            p = Profil(prenom="Alex", nom="Dupont", vma=16.0, fc_max=195)
            sauvegarder_profil(p, chemin=f)
            self.assertTrue(f.exists())

            with open(f, encoding="utf-8") as fp:
                data = yaml.safe_load(fp)
                self.assertEqual(data["identite"]["prenom"], "Alex")
                self.assertEqual(data["physiologie"]["vma"], 16.0)

            p2 = Profil.from_dict(data)
            self.assertEqual(p2.prenom, "Alex")
            self.assertEqual(p2.vma, 16.0)

    def test_chemins_portable(self):
        self.assertTrue(chemins.state_dir().is_dir())
        self.assertTrue(chemins.planif_path().name.endswith(".json"))
