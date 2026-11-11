import pytest
from src.ressenti import enregistrer_rpe, dernier_rpe


def test_ressenti_nominal():
    entree = enregistrer_rpe(7, "Bonnes sensations", "2026-11-12")
    assert entree["note"] == 7
    assert entree["commentaire"] == "Bonnes sensations"

    recup = dernier_rpe("2026-11-12")
    assert recup is not None
    assert recup["note"] == 7


def test_ressenti_invalide():
    with pytest.raises(ValueError):
        enregistrer_rpe(11)
    with pytest.raises(ValueError):
        enregistrer_rpe(0)
