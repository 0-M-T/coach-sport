from unittest import mock
from src.intervals import _headers, verifier_connexion


def test_intervals_headers():
    h = _headers("testkey123")
    assert "Authorization" in h
    assert h["Authorization"].startswith("Basic ")


@mock.patch("urllib.request.urlopen")
def test_intervals_tester_connexion(mock_urlopen):
    cm = mock.MagicMock()
    cm.read.return_value = b'{"name": "Athlete Test"}'
    cm.__enter__.return_value = cm
    mock_urlopen.return_value = cm

    ok, msg = verifier_connexion("i12345", "keysecret")
    assert ok is True
    assert "Athlete Test" in msg
