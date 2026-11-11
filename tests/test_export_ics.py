import unittest
import tempfile
from pathlib import Path
from src.export_ics import generer_ics, exporter_fichier


class TestExportIcs(unittest.TestCase):
    def test_generer_ics(self):
        ics = generer_ics(jours=14)
        self.assertIn("BEGIN:VCALENDAR", ics)
        self.assertIn("END:VCALENDAR", ics)
        self.assertIn("VERSION:2.0", ics)

    def test_exporter_fichier(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "test.ics"
            res = exporter_fichier(p, jours=7)
            self.assertTrue(res.exists())
            self.assertIn("BEGIN:VCALENDAR", res.read_text(encoding="utf-8"))
