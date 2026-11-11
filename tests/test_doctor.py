import unittest
from src.doctor import diagnostiquer


class TestDoctor(unittest.TestCase):
    def test_doctor_execution(self):
        res = diagnostiquer()
        self.assertIn("Python", res)
        self.assertIn("Profil", res)
        self.assertIn("Garmin", res)
        self.assertIn("Strava", res)
