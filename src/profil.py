"""Modèle et chargement du profil athlète (profile.yaml)."""
from dataclasses import dataclass, field
import os
from pathlib import Path
import yaml
from . import chemins

DEFAULT_OBJECTIFS = [
    {"nom": "Semi-Marathon Lourdes-Tarbes", "date": "2026-11-29", "priorite": "A"},
    {"nom": "24h de La Rhune", "date": "2027-01-23", "priorite": "A", "details": None},
    {"nom": "10 km sous 40 min (4'00/km)", "date": "2027-04-25", "priorite": "A", "details": "date à confirmer"},
    {"nom": "5 km sous 20 min (3'59/km)", "date": "2027-04-04", "priorite": "B", "details": "test intermédiaire, date à confirmer"},
]

DEFAULT_CHAUSSURES = {
    "seuil_bas": "Adidas Evo SL (paire 2)",
    "ef_paire": "Adidas Adizero Evo SL",
    "carbone": "ASICS Metaspeed Sky Paris",
    "scott": "Scott Kinabalu Trail",
    "nnormal": "NNormal Kjerag",
}


@dataclass
class Profil:
    prenom: str = "Athlète"
    nom: str = ""
    age: int = 28
    taille: int = 175
    poids: float = 68.0
    vma: float = 16.0
    fc_max: int = 195
    fc_repos: int = 55
    seuil_allure_s: int = 265
    seuil_fc: int = 175
    depart_nom: str = "Maison"
    depart_lat: float = 43.3515
    depart_lon: float = -0.3120
    club_actif: bool = True
    club_nom: str = "ASM"
    club_stade_lat: float = 43.315603
    club_stade_lon: float = -0.370669
    club_ligne: str = " Au club ASM (groupe de fractionné adapté à cette allure) ou seul sur la piste."
    chaussures: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_CHAUSSURES))
    objectifs: list[dict] = field(default_factory=lambda: list(DEFAULT_OBJECTIFS))
    montre: str = "garmin"
    fuseau: str = "Europe/Paris"
    version: int = 1

    @property
    def depart_coords(self) -> tuple[float, float, str]:
        return (self.depart_lat, self.depart_lon, self.depart_nom)

    @property
    def club_stade(self) -> tuple[float, float]:
        return (self.club_stade_lat, self.club_stade_lon)

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "identite": {"prenom": self.prenom, "nom": self.nom, "age": self.age, "taille": self.taille, "poids": self.poids},
            "physiologie": {"vma": self.vma, "fc_max": self.fc_max, "fc_repos": self.fc_repos, "seuil_allure_s": self.seuil_allure_s, "seuil_fc": self.seuil_fc},
            "localisation": {"nom": self.depart_nom, "lat": self.depart_lat, "lon": self.depart_lon},
            "club": {"actif": self.club_actif, "nom": self.club_nom, "stade_lat": self.club_stade_lat, "stade_lon": self.club_stade_lon, "ligne": self.club_ligne},
            "chaussures": self.chaussures,
            "objectifs": self.objectifs,
            "preferences": {"montre": self.montre, "fuseau": self.fuseau},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Profil":
        ident = data.get("identite", {})
        physio = data.get("physiologie", {})
        loc = data.get("localisation", {})
        cl = data.get("club", {})
        prefs = data.get("preferences", {})
        return cls(
            prenom=ident.get("prenom", "Athlète"),
            nom=ident.get("nom", ""),
            age=ident.get("age", 30),
            taille=ident.get("taille", 175),
            poids=float(physio.get("poids", ident.get("poids", 70.0))),
            vma=float(physio.get("vma", 15.0)),
            fc_max=int(physio.get("fc_max", 190)),
            fc_repos=int(physio.get("fc_repos", 60)),
            seuil_allure_s=int(physio.get("seuil_allure_s", 270)),
            seuil_fc=int(physio.get("seuil_fc", 170)),
            depart_nom=loc.get("nom", "Maison"),
            depart_lat=float(loc.get("lat", 43.3515)),
            depart_lon=float(loc.get("lon", -0.3120)),
            club_actif=cl.get("actif", False),
            club_nom=cl.get("nom", ""),
            club_stade_lat=float(cl.get("stade_lat", 43.315603)),
            club_stade_lon=float(cl.get("stade_lon", -0.370669)),
            club_ligne=cl.get("ligne", ""),
            chaussures=data.get("chaussures", dict(DEFAULT_CHAUSSURES)),
            objectifs=data.get("objectifs", list(DEFAULT_OBJECTIFS)),
            montre=prefs.get("montre", "garmin"),
            fuseau=prefs.get("fuseau", "Europe/Paris"),
            version=data.get("version", 1),
        )


_PROFIL_INSTANCE: Profil | None = None


def chercher_fichier_profil() -> Path | None:
    env_p = os.environ.get("COACH_PROFILE")
    if env_p and Path(env_p).is_file():
        return Path(env_p)
    ch = chemins.coach_home()
    if ch and (ch / "profile.yaml").is_file():
        return ch / "profile.yaml"
    c_dir = chemins.config_dir()
    if (c_dir / "profile.yaml").is_file():
        return c_dir / "profile.yaml"
    return None


def charger_profil(recharger: bool = False) -> Profil:
    global _PROFIL_INSTANCE
    if _PROFIL_INSTANCE is not None and not recharger:
        return _PROFIL_INSTANCE
    f = chercher_fichier_profil()
    if f:
        with open(f, encoding="utf-8") as fp:
            data = yaml.safe_load(fp) or {}
            _PROFIL_INSTANCE = Profil.from_dict(data)
    else:
        _PROFIL_INSTANCE = Profil()
    return _PROFIL_INSTANCE


def sauvegarder_profil(profil: Profil, chemin: Path | None = None) -> Path:
    target = chemin or chercher_fichier_profil() or (chemins.config_dir() / "profile.yaml")
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8") as fp:
        yaml.dump(profil.to_dict(), fp, allow_unicode=True, sort_keys=False)
    global _PROFIL_INSTANCE
    _PROFIL_INSTANCE = profil
    return target
