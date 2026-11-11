"""Météo sur la fenêtre de la séance (Open-Meteo, par heure) et conseils pratiques."""
import datetime as dt
import json
import urllib.request

HOURLY = "apparent_temperature,precipitation_probability,precipitation,wind_speed_10m,wind_gusts_10m,uv_index,cloud_cover,is_day"


def fetch(lat: float, lon: float, jours: int = 3) -> dict:
    url = (f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly={HOURLY}"
           f"&daily=sunrise,sunset&forecast_days={jours}&timezone=Europe%2FParis")
    with urllib.request.urlopen(url, timeout=8) as r:
        return json.loads(r.read())


def fenetre(data: dict, date: str, debut: str, duree_min: int = 90) -> dict:
    """Agrège les heures qui recouvrent [debut, debut + durée]. Lève ValueError si la prévision est absente."""
    start = dt.datetime.fromisoformat(f"{date}T{debut}")
    end = start + dt.timedelta(minutes=duree_min)
    h = data["hourly"]
    idx = [i for i, t in enumerate(h["time"])
           if (d := dt.datetime.fromisoformat(t)) < end and d + dt.timedelta(hours=1) > start]
    if not idx:
        raise ValueError(f"pas de prévision pour {date} {debut}")
    def col(k):
        return [h[k][i] for i in idx if h[k][i] is not None]

    jour = data["daily"]["time"].index(date) if date in data["daily"]["time"] else None
    return {
        "debut": start.strftime("%H:%M"), "fin": end.strftime("%H:%M"),
        "ressenti_min": min(col("apparent_temperature")), "ressenti_max": max(col("apparent_temperature")),
        "pluie_prob": max(col("precipitation_probability") or [0]), "pluie_mm": round(sum(col("precipitation")), 1),
        "vent": max(col("wind_speed_10m")), "rafales": max(col("wind_gusts_10m")),
        "uv": max(col("uv_index")), "nuages": round(sum(col("cloud_cover")) / len(col("cloud_cover"))),
        "nuit": any(v == 0 for v in col("is_day")), "jour": any(v == 1 for v in col("is_day")),
        "lever": data["daily"]["sunrise"][jour][11:16] if jour is not None else None,
        "coucher": data["daily"]["sunset"][jour][11:16] if jour is not None else None,
    }


def resume(w: dict) -> str:
    r0, r1 = round(w["ressenti_min"]), round(w["ressenti_max"])
    ressenti = f"{r0}°C" if r0 == r1 else f"{r0} à {r1}°C"
    return (f"{w['debut']} à {w['fin']}\nRessenti {ressenti}, pluie {w['pluie_prob']:.0f} % ({w['pluie_mm']} mm)\n"
            f"Vent {w['vent']:.0f} km/h (rafales {w['rafales']:.0f}), UV {w['uv']:.0f}, nuages {w['nuages']} %")


def tenue(effectif: float) -> str:
    # À l'effort on se sent ~5°C plus chaud que le ressenti à l'arrêt.
    if effectif < 4:
        return "Grand froid : collant long, 2 couches, gants, bonnet"
    if effectif < 9:
        return "Frais : collant ou 3/4, manches longues, gants fins"
    if effectif < 15:
        return "Doux : manches longues, short ou 3/4"
    if effectif < 21:
        return "T-shirt et short"
    if effectif < 27:
        return "Chaud : tenue légère, casquette, eau sur soi"
    return "Très chaud : reporter ou raccourcir, casquette, eau et sel"


def conseils(w: dict) -> list[str]:
    out = [tenue((w["ressenti_min"] + w["ressenti_max"]) / 2 + 5)]
    if w["pluie_prob"] >= 50 or w["pluie_mm"] >= 0.5:
        out.append(f"Pluie probable ({w['pluie_prob']:.0f} %) : K-way, casquette")
    elif w["pluie_prob"] >= 30:
        out.append("Averse possible : K-way dans la poche")
    if w["rafales"] >= 40:
        out.append(f"Rafales {w['rafales']:.0f} km/h : K-way coupe-vent, aller face au vent, retour dos au vent")
    if w["nuit"]:
        if w["debut"] >= "12:00":   # séance du soir : la nuit tombe avant ou pendant
            out.append(f"Séance de nuit (coucher du soleil {w['coucher'] or '?'}) : frontale et gilet réfléchissant")
        else:
            out.append(f"Départ de nuit (lever {w['lever'] or '?'}) : frontale et gilet réfléchissant")
    if w["jour"] and w["nuages"] < 50:
        out.append("Soleil : lunettes" + (f" et crème (UV {w['uv']:.0f})" if w["uv"] >= 6 else ""))
    return out
