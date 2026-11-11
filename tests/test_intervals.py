import unittest
from unittest import mock
from src.intervals import _headers, verifier_connexion


class TestIntervals(unittest.TestCase):
    def test_intervals_headers(self):
        h = _headers("testkey123")
        self.assertIn("Authorization", h)
        self.assertTrue(h["Authorization"].startswith("Basic "))

    @mock.patch("urllib.request.urlopen")
    def test_intervals_verifier_connexion(self, mock_urlopen):
        cm = mock.MagicMock()
        cm.read.return_value = b'{"name": "Athlete Test"}'
        cm.__enter__.return_value = cm
        mock_urlopen.return_value = cm

        ok, msg = verifier_connexion("i12345", "keysecret")
        self.assertTrue(ok)
        self.assertIn("Athlete Test", msg)
