from pathlib import Path
import tempfile
import yaml
from src.profil import Profil, sauvegarder_profil
from src import chemins


def test_profil_defaut():
    p = Profil()
    assert p.prenom == "Athlète"
    assert p.depart_coords == (43.3515, -0.3120, "Maison")
    assert "seuil_bas" in p.chaussures


def test_profil_sauvegarder_charger():
    with tempfile.TemporaryDirectory() as tmpdir:
        f = Path(tmpdir) / "profile.yaml"
        p = Profil(prenom="Alex", nom="Dupont", vma=16.0, fc_max=195)
        sauvegarder_profil(p, chemin=f)
        assert f.exists()

        with open(f, encoding="utf-8") as fp:
            data = yaml.safe_load(fp)
            assert data["identite"]["prenom"] == "Alex"
            assert data["physiologie"]["vma"] == 16.0

        p2 = Profil.from_dict(data)
        assert p2.prenom == "Alex"
        assert p2.vma == 16.0


def test_chemins_portable():
    assert chemins.state_dir().is_dir()
    assert chemins.planif_path().name.endswith(".json")
