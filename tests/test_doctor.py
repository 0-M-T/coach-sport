from src.doctor import diagnostiquer


def test_doctor_execution():
    res = diagnostiquer()
    assert "Python" in res
    assert "Profil" in res
    assert "Garmin" in res
    assert "Strava" in res
