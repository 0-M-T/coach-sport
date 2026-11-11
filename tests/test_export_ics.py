import tempfile
from pathlib import Path
from src.export_ics import generer_ics, exporter_fichier


def test_generer_ics():
    ics = generer_ics(jours=14)
    assert "BEGIN:VCALENDAR" in ics
    assert "END:VCALENDAR" in ics
    assert "VERSION:2.0" in ics


def test_exporter_fichier():
    with tempfile.TemporaryDirectory() as tmpdir:
        p = Path(tmpdir) / "test.ics"
        res = exporter_fichier(p, jours=7)
        assert res.exists()
        assert "BEGIN:VCALENDAR" in res.read_text(encoding="utf-8")
