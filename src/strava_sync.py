#!/usr/bin/env python3
"""Pousse la dernière activité Strava vers Home Assistant (capteurs sensor.strava_last_activity_*)."""
import json
import urllib.request

from . import strava
from .config import HA_URL_DEFAUT, load_config


def sync_strava_to_ha(conf=None):
    conf = load_config() if conf is None else conf
    ha_url = conf.get("HA_URL", HA_URL_DEFAUT).rstrip("/")
    if not conf.get("HA_TOKEN"):
        raise ValueError("HA_TOKEN manquant")
    acts = strava.activities(strava.token(conf), 1)
    if not acts:
        print("Aucune activité Strava")
        return
    act = acts[0]
    secs = act["moving_time"]
    sensors = [
        ("last_activity_name", act["name"], "mdi:run", "Strava dernière activité", None),
        ("last_activity_type", act.get("sport_type", act.get("type")), "mdi:shoe-sneaker", "Strava type", None),
        ("last_activity_distance", round(act["distance"] / 1000, 2), "mdi:map-marker-distance", "Strava distance", "km"),
        ("last_activity_duration", f"{secs // 3600}h{(secs % 3600) // 60:02d}m", "mdi:clock-outline", "Strava durée", None),
        ("last_activity_pace", f"{strava.pace(act['distance'], secs)}''", "mdi:speedometer", "Strava allure", "min/km"),
        ("last_activity_heart_rate", act.get("average_heartrate", 0), "mdi:heart-pulse", "Strava FC moyenne", "bpm"),
        ("last_activity_elevation", act.get("total_elevation_gain", 0), "mdi:image-filter-hdr", "Strava D+", "m"),
        ("last_activity_date", act.get("start_date_local", "").split("T")[0], "mdi:calendar", "Strava date", None),
    ]
    for sid, state, icon, fname, unit in sensors:
        body = {"state": str(state), "attributes": {"icon": icon, "friendly_name": fname}}
        if unit:
            body["attributes"]["unit_of_measurement"] = unit
        urllib.request.urlopen(urllib.request.Request(
            f"{ha_url}/api/states/sensor.strava_{sid}", data=json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {conf['HA_TOKEN']}", "Content-Type": "application/json"},
            method="POST"), timeout=5)
    print("Strava HA push completed")


if __name__ == "__main__":
    sync_strava_to_ha()
