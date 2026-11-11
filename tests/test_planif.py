"""Planification autonome, plan, progression des allures."""
import datetime as dt
import unittest

from src import planif

PARIS = __import__("zoneinfo").ZoneInfo("Europe/Paris")


class Planif(unittest.TestCase):
    NOW = dt.datetime(2026, 11, 10, 7, 0, tzinfo=PARIS)

    def setUp(self):
        import tempfile
        from pathlib import Path
        self._d = tempfile.TemporaryDirectory()
        planif.STATE = Path(self._d.name) / "planif.json"
        self.addCleanup(self._d.cleanup)
        self.occ = {}
        self._orig = (planif.occupations_range, planif.baikal.lister, planif.baikal.creer, planif.baikal.modifier, planif.baikal.supprimer)
        self.addCleanup(lambda: [setattr(planif.baikal, n, f) for n, f in zip(("lister", "creer", "modifier", "supprimer"), self._orig[1:], strict=True)] +
                        [setattr(planif, "occupations_range", self._orig[0])])
        planif.occupations_range = lambda a, b: self.occ
        # Plan de test figé : ces tests vérifient le moteur, pas les séances du vrai plan (qui évolue)
        from src import plan as P
        ancienne = [P.ef(1, 40), P.renfo(1, "B1"),
                    P.Entree(2, "seuil", "Seuil 3x3000m à 4'20/km", 80, "Échauffement, 3x3000m à 4'20/km, retour au calme.", dure=True,
                             etapes=(P.W(20), P.REP(3, P.ID(3000, 260), P.R(150)), P.C(10)), famille="seuil", allure_base=260),
                    P.renfo(2, "A1"), P.ef(3, 35), P.etirements(4, "D1"),
                    P.Entree(5, "longue", "Sortie longue 1h30 vallonnée", 100, "Sortie longue.", prefs=("09:00", "16:00"), dure=True,
                             etapes=(P.E(20, 325, 345), P.IT(1200, 270, 4), P.E(50, 320, 340))),
                    P.Entree(6, "velo", "Vélo route souple 1h", 60, "Vélo.", prefs=("10:00", "15:00")), P.renfo(6, "C1", prefs=("18:00", "17:00"))]
        orig_semaines = planif.SEMAINES
        planif.SEMAINES = {**orig_semaines, "2026-11-09": ancienne}
        self.addCleanup(lambda: setattr(planif, "SEMAINES", orig_semaines))
        self.groupes = {}
        orig_groupes = self.vrai_groupes_range = planif.groupes_range
        planif.groupes_range = lambda a, b: self.groupes
        self.addCleanup(lambda: setattr(planif, "groupes_range", orig_groupes))
        # Les tests ne doivent JAMAIS atteindre le vrai compte Garmin (un test a créé 35 séances et 49 programmations réelles)
        orig_garmin = planif._garmin
        self.garmin_appels = []
        planif._garmin = lambda compte, maintenant: self.garmin_appels.append(1) or []
        self.addCleanup(lambda: setattr(planif, "_garmin", orig_garmin))
        self.agenda, self.appels = {}, []

        def lister(d, f=None, cal="Sport", fins=False):
            return [f"{r['date']} {r['heure']}  [Sport] {r['titre']}  — {i}" for i, r in self.agenda.items()]
        planif.baikal.lister = lister
        def creer(titre, debut, fin, desc, url=None, cal="Sport", categorie=None, html=None):
            i = f"id{len(self.agenda)}.ics"
            self.agenda[i] = {"date": debut[:10], "heure": debut[11:], "titre": titre}
            self.appels.append(("creer", titre, debut))
            return i
        def modifier(i, **ch):
            if "titre" in ch:
                self.agenda[i]["titre"] = ch["titre"]
            if "debut" in ch:
                self.agenda[i]["date"], self.agenda[i]["heure"] = ch["debut"][:10], ch["debut"][11:]
            self.appels.append(("modifier", i, ch.get("titre")))
        def supprimer(i):
            del self.agenda[i]
            self.appels.append(("supprimer", i))
        planif.baikal.creer, planif.baikal.modifier, planif.baikal.supprimer = creer, modifier, supprimer

    def test_creation_puis_idempotence(self):
        c, _ = planif.planifier(jours=7, apply=True, maintenant=self.NOW)
        self.assertTrue(any("Seuil 3x3000m" in l for l in c))
        n = len(self.appels)
        c2, _ = planif.planifier(jours=7, apply=True, maintenant=self.NOW)
        self.assertEqual(len(self.appels), n)  # rien de plus au second passage
        self.assertEqual(c2, [])

    def test_conflit_matin_bascule_au_soir(self):
        self.occ["2026-11-12"] = [{"debut": None, "fin": None, "bloque": True, "titre": "Forum"}]
        c, _ = planif.planifier(jours=7, apply=True, maintenant=self.NOW)
        ef = [a for a in self.appels if a[0] == "creer" and a[2].startswith("2026-11-12")]
        self.assertEqual(ef[0][2][11:], "18:30")

    def test_aucun_creneau_est_signale_pas_deplace(self):
        self.occ["2026-11-11"] = [{"debut": None, "fin": None, "bloque": True, "titre": "Entretien"}, {"debut": 17 * 60, "fin": 22 * 60, "bloque": False, "titre": "Rdv"}]
        # séances dures voisines : le seuil ne peut aller ni au 10 (collé au 9) ni au 12 (collé au 13)
        _, notes = planif.planifier(jours=7, apply=True, maintenant=self.NOW, dures_init={"2026-11-09", "2026-11-13"})
        self.assertTrue(any("Seuil 3x3000m" in n and "aucun créneau" in n for n in notes))
        self.assertFalse(any(a[0] == "creer" and "Seuil 3x3000m" in a[1] for a in self.appels))

    def test_edition_de_tom_verrouille(self):
        planif.planifier(jours=7, apply=True, maintenant=self.NOW)
        i = next(i for i, r in self.agenda.items() if "Seuil 3x3000m" in r["titre"])
        self.agenda[i]["heure"] = "07:00"  # Tom déplace la séance
        self.occ["2026-11-11"] = [{"debut": 8 * 60, "fin": 9 * 60 + 30, "bloque": False, "titre": "autre"}]  # le plan voudrait la bouger
        n = len(self.appels)
        c, _ = planif.planifier(jours=7, apply=True, maintenant=self.NOW)
        self.assertEqual(len(self.appels), n)   # séance verrouillée, et le renfo du soir ne bouge pas à cause d'elle

    def test_seance_imminente_non_deplacee_ni_supprimee(self):
        planif.planifier(jours=7, apply=True, maintenant=self.NOW)
        proche = dt.datetime(2026, 11, 11, 7, 0, tzinfo=PARIS)  # séance à 08:30 dans 1 h 30
        n = len(self.appels)
        planif.planifier(jours=7, apply=True, maintenant=proche)
        self.assertEqual([a for a in self.appels[n:] if "3x3000" in str(a)], [])

    def test_allegement_fatigue_puis_conservation(self):
        planif.planifier(jours=7, apply=True, maintenant=self.NOW)
        mer = dt.datetime(2026, 11, 11, 6, 0, tzinfo=PARIS)
        notes = planif.ajuster_jour({"sleep_hours": 5.5, "hrv_status": "BALANCED"}, mer)
        self.assertTrue(notes and "allégée" in notes[0].lower())
        self.assertIn("allégée", next(r["titre"] for r in self.agenda.values() if r["date"] == "2026-11-11" and "EF" in r["titre"]))
        c, _ = planif.planifier(jours=7, apply=True, maintenant=mer)
        self.assertTrue(any("allégée par le coach" in l for l in c))

    def test_forme_inconnue_ou_bonne_ne_change_rien(self):
        planif.planifier(jours=7, apply=True, maintenant=self.NOW)
        mer = dt.datetime(2026, 11, 11, 6, 0, tzinfo=PARIS)
        self.assertEqual(planif.ajuster_jour({"sleep_hours": None, "hrv_status": None}, mer), [])
        self.assertEqual(planif.ajuster_jour({"sleep_hours": 8, "hrv_status": "BALANCED"}, mer), [])

    def test_evenement_ajoute_au_dernier_moment_deplace_la_seance(self):
        planif.planifier(jours=7, apply=True, maintenant=self.NOW)   # seuil mercredi 11 à 08:30
        mer = dt.datetime(2026, 11, 11, 6, 30, tzinfo=PARIS)         # 2 h avant : normalement gelée
        self.occ["2026-11-11"] = [{"debut": 8 * 60, "fin": 10 * 60, "bloque": False, "titre": "Rdv ajouté ce matin"}]
        c, _ = planif.planifier(jours=7, apply=True, maintenant=mer)
        seuil = next(r for r in self.agenda.values() if "Seuil 3x3000" in r["titre"])
        self.assertEqual(seuil["date"], "2026-11-11")
        self.assertGreaterEqual(seuil["heure"], "10:15")  # après le rendez-vous, marge comprise
        self.assertTrue(any("mise à jour" in l for l in c))

    def test_description_seule_ne_declenche_aucune_notification(self):
        planif.planifier(jours=7, apply=True, maintenant=self.NOW)
        etat = planif.charger()
        for rec in etat["evenements"].values():
            rec["empreinte"] = "ancienne"   # même date, heure et titre, contenu différent
        planif.sauver(etat)
        c, _ = planif.planifier(jours=7, apply=True, maintenant=self.NOW)
        self.assertTrue(any("description actualisée" in l for l in c))
        self.assertFalse(any("mise à jour" in l for l in c))
        self.assertEqual(planif.resume_changements(c, [], []), [])

    def test_journee_pleine_deplace_une_seance_facile_au_jour_voisin(self):
        self.occ["2026-11-12"] = [{"debut": None, "fin": None, "bloque": True, "titre": "Forum"},
                                  {"debut": 17 * 60, "fin": 22 * 60, "bloque": False, "titre": "Soirée"}]
        c, notes = planif.planifier(jours=7, apply=True, maintenant=self.NOW)
        self.assertTrue(any("déplacée du 2026-11-12 au" in n for n in notes))
        self.assertEqual([r["titre"] for r in self.agenda.values() if r["date"] == "2026-11-12"], [])

    def test_seuil_deplace_au_jour_voisin_libre(self):
        self.occ["2026-11-11"] = [{"debut": None, "fin": None, "bloque": True, "titre": "Forum"},
                                  {"debut": 17 * 60, "fin": 22 * 60, "bloque": False, "titre": "Soirée"}]
        _, notes = planif.planifier(jours=7, apply=True, maintenant=self.NOW, dures_init={"2026-11-09"})
        self.assertTrue(any("Seuil 3x3000m" in n and "déplacée du 2026-11-11" in n for n in notes))
        seuil = next(r for r in self.agenda.values() if "Seuil 3x3000" in r["titre"])
        self.assertEqual(seuil["date"], "2026-11-12")  # le 10 est collé à la séance dure du 9

    def test_fin_reelle_des_evenements(self):
        self.occ["2026-11-10"] = [{"debut": 8 * 60, "fin": 13 * 60, "bloque": False, "titre": "Long rdv"}]
        planif.planifier(jours=3, apply=True, maintenant=dt.datetime(2026, 11, 9, 20, 0, tzinfo=PARIS), dures_init=set())
        ef = next(r for r in self.agenda.values() if r["date"] == "2026-11-10" and "EF" in r["titre"])
        self.assertGreaterEqual(ef["heure"], "17:00")  # matin occupé jusqu'à 13 h : séance reportée au soir

    def test_reagir_ne_previent_que_des_changements(self):
        import src.ntfy as nt
        envoyes = []
        orig = nt.envoyer
        nt.envoyer = lambda conf, titre, msg, actions=None, priority="default": envoyes.append((titre, msg, priority))
        self.addCleanup(lambda: setattr(nt, "envoyer", orig))
        planif.reagir({"NTFY_URL": "x"}, self.NOW)
        self.assertEqual(envoyes, [])                       # premières créations : silence
        planif.reagir({}, self.NOW)
        self.assertEqual(envoyes, [])                       # rien n'a changé : silence
        self.occ["2026-11-12"] = [{"debut": 18 * 60, "fin": 20 * 60, "bloque": False, "titre": "Imprévu"}]   # jeudi : footing au club à 18:30
        planif.reagir({}, self.NOW)
        self.assertEqual(len(envoyes), 1)                   # séance déplacée (repli le matin) : un message
        self.assertIn("mise à jour", envoyes[0][1])
        planif.reagir({}, self.NOW)
        self.assertEqual(len(envoyes), 1)                   # pas de répétition

    def test_dernier_jour_de_la_fenetre_pas_retire(self):
        planif.planifier(jours=14, apply=True, maintenant=self.NOW)             # crée jusqu'au 23/11 inclus
        n = len([a for a in self.appels if a[0] == "creer"])
        self.assertGreater(n, 0)
        planif.planifier(jours=10, apply=True, maintenant=self.NOW)             # fenêtre plus courte : [10/11, 20/11[
        self.assertEqual([a for a in self.appels if a[0] == "supprimer"], [])   # rien n'est retiré, hors fenêtre ou en bordure

    def test_etirements_les_jours_de_repos_en_soiree(self):
        planif.planifier(jours=14, apply=True, maintenant=dt.datetime(2026, 11, 9, 20, 0, tzinfo=PARIS), dures_init=set())
        vend = {r["date"]: r for r in self.agenda.values() if "Étirements" in r["titre"]}
        self.assertEqual(sorted(vend), ["2026-11-13", "2026-11-20"])
        self.assertTrue(all("15:00" <= r["heure"] <= "18:00" for r in vend.values()))   # l'après-midi, pas tard le soir
        self.assertNotEqual(vend["2026-11-13"]["titre"], vend["2026-11-20"]["titre"])  # routines différentes d'une semaine à l'autre

    def test_seance_de_groupe_remplace_la_seance_du_jour_et_allege_le_lendemain(self):
        # sortie de groupe mercredi 11 (jour du seuil prévu) : le seuil est remplacé, le footing du jeudi reste facile
        self.groupes["2026-11-11"] = {"titre": "Groupe : sortie avec les potes", "dure": True}
        _, notes = planif.planifier(jours=7, apply=True, maintenant=self.NOW, dures_init=set())
        self.assertTrue(any("Seuil 3x3000m" in n and "remplacée par la séance de groupe" in n for n in notes))
        self.assertFalse(any("Seuil 3x3000" in r["titre"] for r in self.agenda.values()))

    def test_seance_de_groupe_dure_degrade_la_seance_dure_voisine(self):
        # groupe le vendredi 13 (jour de repos) : la sortie longue du samedi 14 devient un footing facile
        self.groupes["2026-11-13"] = {"titre": "Groupe : trail", "dure": True}
        _, notes = planif.planifier(jours=7, apply=True, maintenant=self.NOW, dures_init=set())
        self.assertTrue(any("Sortie longue" in n and "footing facile" in n for n in notes))
        self.assertFalse(any("Sortie longue" in r["titre"] for r in self.agenda.values()))

    def test_groupe_facile_ne_degrade_pas_les_voisines(self):
        self.groupes["2026-11-13"] = {"titre": "Groupe : balade facile", "dure": False}
        planif.planifier(jours=7, apply=True, maintenant=self.NOW, dures_init=set())
        self.assertTrue(any("Sortie longue" in r["titre"] for r in self.agenda.values()))

    def test_club_asm_compte_comme_groupe_et_compatibilite(self):
        planif.groupes_range = self.vrai_groupes_range  # test direct de la détection par titre
        saved = planif.baikal.lister
        planif.baikal.lister = lambda d, f=None, cal="Sport", fins=False: [
            "2026-11-17 18:30→20:00  [Sport] Club ASM : fractionné 8x400  — a.ics",
            "2026-11-19 18:30→20:00  [Sport] Club ASM : footing EF avec le groupe  — b.ics",
            "2026-11-12 08:30→09:30  [Sport] CAP: Footing EF 35 min  — c.ics"]
        self.addCleanup(lambda: setattr(planif.baikal, "lister", saved))
        g = planif.groupes_range("2026-11-10", "2026-11-30")
        self.assertEqual(sorted(g), ["2026-11-17", "2026-11-19"])
        self.assertTrue(g["2026-11-17"]["dure"])      # fractionné : séance dure
        self.assertFalse(g["2026-11-19"]["dure"])     # footing EF : facile

    def test_compatibilite_club(self):
        self.assertIn("4'10/km", planif.compatible_club("CAP: Seuil court 5x1000m à 4'10/km"))
        self.assertIn("groupe d'allure EF", planif.compatible_club("CAP: Footing EF 35 min"))
        self.assertIsNone(planif.compatible_club("CAP: Côtes 8x45 s"))
        self.assertIsNone(planif.compatible_club("Pic du Rey : montée et descente (référence)"))

    def test_journal_lisible_pour_le_recap(self):
        from src.semaine import lisible
        self.assertIsNone(lisible({"action": "creation", "detail": "2026-11-12|ef CAP: Footing EF 35 min 08:30"}))
        self.assertIsNone(lisible({"action": "garmin", "detail": "séance Garmin A1 créée"}))
        self.assertIsNone(lisible({"action": "maj", "detail": "2026-11-12|ef CAP: Footing EF 35 min 08:30->08:30"}))   # contenu mis à jour, pas déplacé
        self.assertEqual(lisible({"action": "maj", "detail": "2026-11-12|ef CAP: Footing EF 35 min 08:30->18:30"}), "12/11 : CAP: Footing EF 35 min déplacée de 08:30 à 18:30")
        self.assertEqual(lisible({"action": "maj", "detail": "2026-11-12|ef CAP: Footing EF 35 min 18:30"}), "12/11 : CAP: Footing EF 35 min déplacée à 18:30")
        self.assertEqual(lisible({"action": "retrait", "detail": "2026-11-19|ef CAP: Footing EF 30 min"}), "19/11 : CAP: Footing EF 30 min retirée du plan")
        self.assertIn("remplacée par un footing EF", lisible({"action": "allegement", "detail": "2026-11-11|seuil CAP: Seuil -> CAP: Footing EF 40 min"}))

    def test_sortie_velo_de_groupe_ne_remplace_pas_la_course(self):
        planif.groupes_range = self.vrai_groupes_range
        saved = planif.baikal.lister
        planif.baikal.lister = lambda d, f=None, cal="Sport", fins=False: [
            "2026-11-14 09:00→11:00  [Sport] Club ASM : sortie vélo route  — a.ics",
            "2026-11-15 08:00→12:00  [Sport] Groupe : grande sortie vélo  — b.ics"]
        self.addCleanup(lambda: setattr(planif.baikal, "lister", saved))
        g = planif.groupes_range("2026-11-10", "2026-11-30")
        self.assertEqual((g["2026-11-14"]["velo"], g["2026-11-14"]["dure"]), (True, False))   # 2 h : facile
        self.assertEqual((g["2026-11-15"]["velo"], g["2026-11-15"]["dure"]), (True, True))    # 4 h : compte comme dure

    def test_deux_seances_du_coach_ne_se_recouvrent_pas(self):
        # fractionné de 65 min à 18:30 puis renfo préféré à 19:00 le même soir : le renfo doit passer après
        import datetime as d
        seances, _ = planif.construire(d.date(2027, 2, 16), 1, dt.datetime(2027, 2, 1, 12, 0, tzinfo=PARIS), occ={}, etat={"evenements": {}}, groupes={})
        jour = sorted((s for s in seances if s.date == "2027-02-16"), key=lambda s: s.heure)
        self.assertGreaterEqual(len(jour), 2)
        for a, b in zip(jour, jour[1:], strict=False):
            self.assertLessEqual(planif.minutes(a.heure) + a.duree, planif.minutes(b.heure))

    def test_resume_ne_montre_pas_les_seances_supprimees_par_tom(self):
        lignes = planif.resume_changements(["2026-11-10|ef : supprimée par Tom, non recréée", "2026-11-11|ef : créée à 08:30 (x)",
                                            "2026-11-12|ef : retirée (plus au plan)"], [], [])
        self.assertEqual(len(lignes), 2)
        self.assertFalse(any("supprimée" in l for l in lignes))

    def test_footing_du_mardi_et_du_jeudi_propose_au_club_le_soir(self):
        import datetime as d
        seances, _ = planif.construire(d.date(2026, 11, 10), 5, dt.datetime(2026, 11, 9, 18, 0, tzinfo=PARIS), occ={}, etat={"evenements": {}}, groupes={})
        ef = {s.date: s for s in seances if s.kind == "ef"}
        self.assertEqual((ef["2026-11-10"].heure, "club ASM" in ef["2026-11-10"].titre), ("18:30", True))   # mardi
        self.assertEqual(ef["2026-11-12"].heure, "18:30")                                                   # jeudi
        renfo = next(s for s in seances if s.date == "2026-11-10" and s.kind == "renfo")
        self.assertEqual(renfo.heure, "08:30")                       # jour de club : le matin, Tom rentre du club après 19 h 30
        autre = planif.construire(d.date(2026, 11, 11), 1, dt.datetime(2026, 11, 9, 18, 0, tzinfo=PARIS), occ={}, etat={"evenements": {}}, groupes={})[0]
        self.assertEqual(next(s for s in autre if s.kind == "renfo").heure, "16:00")           # mercredi : 16:00 par défaut
        # un autre jour reste le matin
        autres = planif.construire(d.date(2026, 11, 16), 1, dt.datetime(2026, 11, 9, 18, 0, tzinfo=PARIS), occ={}, etat={"evenements": {}}, groupes={})[0]
        self.assertEqual(next(s for s in autres if s.kind == "ef").heure, "08:30")                           # lundi

    def test_footing_au_club_se_replie_le_matin_si_le_soir_est_pris(self):
        import datetime as d
        occ = {"2026-11-10": [{"debut": 17 * 60, "fin": 21 * 60, "bloque": False, "titre": "Soirée"}]}
        seances, _ = planif.construire(d.date(2026, 11, 10), 1, dt.datetime(2026, 11, 9, 18, 0, tzinfo=PARIS), occ=occ, etat={"evenements": {}}, groupes={})
        self.assertEqual(next(s for s in seances if s.kind == "ef").heure, "08:30")

    def test_renfo_du_jour_de_club_se_replie_a_15h_si_le_matin_est_pris(self):
        import datetime as d
        occ = {"2026-11-10": [{"debut": 8 * 60, "fin": 12 * 60, "bloque": False, "titre": "Rendez-vous"}]}
        seances, _ = planif.construire(d.date(2026, 11, 10), 1, dt.datetime(2026, 11, 9, 18, 0, tzinfo=PARIS), occ=occ, etat={"evenements": {}}, groupes={})
        renfo = next(s for s in seances if s.kind == "renfo")
        ef = next(s for s in seances if s.kind == "ef")
        self.assertEqual(renfo.heure, "15:00")                                                        # jamais après le club
        self.assertLessEqual(planif.minutes(renfo.heure) + renfo.duree, planif.minutes(ef.heure))

    def test_jour_sans_seance_le_soir_garde_le_renfo_l_apres_midi(self):
        import datetime as d
        seances, _ = planif.construire(d.date(2026, 11, 11), 1, dt.datetime(2026, 11, 9, 18, 0, tzinfo=PARIS), occ={}, etat={"evenements": {}}, groupes={})
        self.assertEqual(next(s for s in seances if s.kind == "renfo").heure, "16:00")                # seuil le matin, renfo à 16:00

    def test_seance_de_piste_le_soir_renvoie_le_renfo_au_matin(self):
        import datetime as d
        # mardi 16/02/2027 : fractionné de piste à 18:30 (bloc 10 km) et renfo A1 le matin
        seances, _ = planif.construire(d.date(2027, 2, 16), 1, dt.datetime(2027, 2, 1, 12, 0, tzinfo=PARIS), occ={}, etat={"evenements": {}}, groupes={})
        piste = next(s for s in seances if s.kind == "seuil")
        self.assertGreaterEqual(piste.heure, "17:00")
        self.assertEqual(next(s for s in seances if s.kind == "renfo").heure, "08:30")

    def test_semaine_du_9_11_seuil_decale_au_jeudi_apres_la_grosse_seance_du_lundi(self):
        import datetime as d

        from src import plan as P
        real = {e.kind + str(e.jour): e for e in P.SEMAINES["2026-11-09"] if e.kind in ("ef", "seuil", "renfo")}
        self.assertEqual(real["seuil3"].jour, 3)                                   # jeudi
        self.assertEqual(real["seuil3"].prefs[0], "18:30")                         # au club le soir
        self.assertNotIn("seuil2", real)                                           # plus de seuil le mercredi
        self.assertIn("ef2", real)                                                 # mercredi : footing facile
        self.assertEqual(real["renfo2"].titre.split(",")[0], "Renfo A2")           # renfo allégé le mercredi
        lundi = d.date(2026, 11, 9)
        jours_durs = sorted(lundi + d.timedelta(days=e.jour) for e in P.SEMAINES["2026-11-09"] if e.dure)
        self.assertEqual([j.isoformat() for j in jours_durs], ["2026-11-12", "2026-11-14"])   # jeudi et samedi : 2 jours d'écart

    def test_seance_deja_faite_non_replanifiee(self):
        acts = [{"start_date_local": "2026-11-09T09:14:00Z", "sport_type": "Run", "name": "Seuil 2x15m AS21"}]
        self.assertEqual(planif.reels_dur_semaine(acts, dt.date(2026, 11, 9)), {"as21"})

class PlanRhune(unittest.TestCase):
    COURSE = ("ef", "seuil", "as21", "longue", "cotes")

    def test_pas_deux_seances_dures_consecutives_ni_semaine_sans_repos(self):
        import datetime as d

        from src.plan import SEMAINES
        dures = set()
        for lundi, es in SEMAINES.items():
            base = d.date.fromisoformat(lundi)
            jours_course = {e.jour for e in es if e.kind in self.COURSE}
            for e in es:
                if e.dure:
                    dures.add(base + d.timedelta(days=e.jour))
            self.assertLess(len(jours_course), 7, f"semaine {lundi} sans jour sans course")
        for j in dures:
            self.assertNotIn(j + d.timedelta(days=1), dures, f"séances dures consécutives le {j}")

    def test_le_bloc_se_place_sans_blocage_sur_un_agenda_vide(self):
        import datetime as d
        seances, notes = planif.construire(d.date(2026, 12, 7), 47, dt.datetime(2026, 11, 9, 12, 0, tzinfo=PARIS), occ={}, etat={"evenements": {}}, groupes={})
        self.assertEqual(notes, [])
        self.assertTrue(any("Simulation 24 h" in s.titre for s in seances))
        self.assertEqual(max(s.date for s in seances) <= "2027-01-22", True)

    def test_rando_du_3_janvier_et_circuit_b3(self):
        import datetime as d

        from src import garmin_renfo as gr
        from src.plan import SEMAINES
        e = next(x for x in SEMAINES["2026-12-28"] if x.kind == "rando")
        self.assertEqual((d.date(2026, 12, 28) + d.timedelta(days=e.jour)).isoformat(), "2027-01-03")
        self.assertFalse(e.dure)
        self.assertEqual(gr.code_de("Renfo B3, haut du corps pour les bâtons"), "B3")
        gr.charge_utile("B3", "x")

    def test_circuit_a3_pour_la_montre(self):
        from src import garmin_renfo as gr
        self.assertEqual(gr.code_de("Renfo A3, bas du corps et descente"), "A3")
        gr.charge_utile("A3", "x")

class Progression(unittest.TestCase):
    def b(self, ecart, fc=160, cible=260, famille="seuil"):
        return {"date": "2026-11-11", "famille": famille, "cible": cible, "ecart": ecart, "fc": fc}

    def test_regles(self):
        from src import progression as pg
        self.assertEqual(pg.correction([], "seuil", 260)[0], 0)
        self.assertEqual(pg.correction([self.b(-5)], "seuil", 260)[0], -2)           # trop facile : plus rapide
        self.assertEqual(pg.correction([self.b(+6)], "seuil", 260)[0], +3)           # trop dur : plus lent
        self.assertEqual(pg.correction([self.b(1)], "seuil", 260)[0], 0)             # dans la cible : on garde
        self.assertEqual(pg.correction([self.b(-5, fc=150), self.b(-5, fc=160)], "seuil", 260)[0], 0 - 0)  # FC montée de 10 : on ne monte pas
        self.assertEqual(pg.correction([self.b(-5, cible=254)], "seuil", 260)[0], -6)  # borne basse atteinte (-6)
        self.assertEqual(pg.correction([self.b(+9, famille="as21", cible=267)], "as21", 265)[0], 2)  # jamais plus lent que 4'27

    def test_appliquer_modifie_titre_etapes_et_texte(self):
        from src import progression as pg
        from src.plan import SEMAINES
        e = next(x for es in SEMAINES.values() for x in es if x.famille == "seuil" and "3x3000" in x.titre)
        n = pg.appliquer(e, [self.b(-5)])
        self.assertIn("4'18", n.titre)
        self.assertIn("ajustée par le coach", n.corps)
        self.assertEqual(n.etapes[1][2][0][2], 258)
        self.assertIs(pg.appliquer(e, []), e)   # sans bilan : inchangé

    def test_bilan_enregistre_une_fois_et_cible_du_jour(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            planif.STATE = Path(d) / "p.json"
            planif.enregistrer_bilan("2026-11-11", "seuil", 260, -4.2, 160)
            planif.enregistrer_bilan("2026-11-11", "seuil", 260, -4.2, 160)
            self.assertEqual(len(planif.charger()["bilans"]), 1)
            etat = {"evenements": {"x": {"cle": "2026-11-11|seuil", "date": "2026-11-11", "etapes": [["w", 1200], ["rep", 3, [["id", 3000, 258, 3], ["r", 150]]]]}}}
            self.assertEqual(planif.cible_du_jour(etat, "2026-11-11", "seuil"), 258)
            self.assertIsNone(planif.cible_du_jour(etat, "2026-11-12", "seuil"))

    def test_garmin_synchro_course_cree_met_a_jour_et_nettoie(self):
        from src import garmin_renfo as gr

        class Faux:
            def __init__(self): self.up, self.sched, self.unsched, self.dele = [], [], [], []
            def get_workouts(self, a, b): return []
            def upload_workout(self, d):
                self.up.append(d)
                return {"workoutId": 200 + len(self.up)}

            def schedule_workout(self, w, date):
                self.sched.append((w, date))
                return {"workoutScheduleId": 700 + len(self.sched)}

            def unschedule_workout(self, s): self.unsched.append(s)
            def delete_workout(self, w): self.dele.append(w)
        c = Faux()
        rec = {"cle": "2026-11-11|seuil", "date": "2026-11-11", "heure": "08:30", "titre": "CAP: Seuil 3x3000m à 4'20/km",
               "etapes": [["w", 1200], ["rep", 3, [["id", 3000, 260, 3], ["r", 150]]], ["c", 600]]}
        etat = {"evenements": {"e1": dict(rec)}}
        gr.synchroniser(c, etat, "2026-11-10")
        self.assertEqual((len(c.up), c.sched), (1, [(201, "2026-11-11")]))
        gr.synchroniser(c, etat, "2026-11-10")
        self.assertEqual(len(c.up), 1)                                    # idempotent
        etat["evenements"]["e1"]["etapes"] = [["w", 1200], ["rep", 3, [["id", 3000, 258, 3], ["r", 150]]], ["c", 600]]   # allure ajustée
        gr.synchroniser(c, etat, "2026-11-10")
        self.assertEqual((len(c.up), c.sched[-1], c.dele), (2, (202, "2026-11-11"), [201]))
        del etat["evenements"]["e1"]
        gr.synchroniser(c, etat, "2026-11-10")
        self.assertEqual((etat["garmin"]["programmes"], etat["garmin"]["courses"], c.dele[-1]), ({}, {}, 202))


if __name__ == "__main__":
    unittest.main()


class Enchainement(unittest.TestCase):
    """Activation collée avant la course, renfo B juste après un footing du matin ; jamais le renfo A, jamais autour du club."""

    def setUp(self):
        from src import plan as P
        semaine = [P.ef(0, 45), P.renfo(0, "B1"),
                   P.Entree(2, "seuil", "Seuil 3x3000m à 4'20/km", 80, "Seuil.", prefs=("08:30", "18:30"), dure=True), P.renfo(2, "C2"),
                   P.ef(3, 40), P.renfo(3, "B2"),
                   P.ef(4, 40), P.renfo(4, "A1"),
                   P.ef(5, 40), P.renfo(5, "B1")]
        orig = planif.SEMAINES
        planif.SEMAINES = {"2026-11-16": semaine}
        self.addCleanup(lambda: setattr(planif, "SEMAINES", orig))

    def _places(self, occ=None):
        seances, _ = planif.construire(dt.date(2026, 11, 16), 7, dt.datetime(2026, 11, 15, 20, 0, tzinfo=PARIS), occ=occ or {},
                                       etat={"evenements": {}}, groupes={}, verrouilles={}, dures_init=set())
        return {(s.date, s.titre.split(",")[0]): s for s in seances}

    def test_renfo_b_juste_apres_le_footing_du_matin(self):
        s = self._places()
        self.assertEqual((s[("2026-11-16", "CAP: Footing EF 45 min")].heure, s[("2026-11-16", "Renfo B1")].heure), ("08:30", "09:20"))
        self.assertIn("Enchaîné juste après le footing", s[("2026-11-16", "Renfo B1")].description)

    def test_activation_collee_avant_la_seance(self):
        s = self._places()
        self.assertEqual((s[("2026-11-18", "Activation C2")].heure, s[("2026-11-18", "CAP: Seuil 3x3000m à 4'20/km")].heure), ("08:15", "08:30"))

    def test_jamais_autour_du_club_ni_pour_le_renfo_a(self):
        s = self._places()
        self.assertEqual(s[("2026-11-19", "CAP: Footing EF 40 min au club ASM")].heure, "18:30")
        self.assertEqual(s[("2026-11-19", "Renfo B2")].heure, "08:30")     # jour de club : le matin, comme avant
        self.assertEqual(s[("2026-11-20", "Renfo A1")].heure, "16:00")     # bas du corps lourd : au moins 6 h après la course

    def test_creneau_pris_apres_le_footing_repli_l_apres_midi(self):
        s = self._places({"2026-11-21": [{"debut": 9 * 60 + 30, "fin": 11 * 60, "bloque": False, "titre": "Marché"}]})
        self.assertEqual(s[("2026-11-21", "Renfo B1")].heure, "16:00")


class VeloMaison(unittest.TestCase):
    def setUp(self):
        from src import plan as P
        semaine = [P.Entree(0, "seuil", "Seuil 3x3000m à 4'20/km", 80, "Seuil.", prefs=("08:30", "18:30"), dure=True),
                   P.etirements(1, "D1", prefs=("16:30", "17:00")),   # lendemain de séance dure : vélo de récupération collé avant
                   P.ef(2, 40), P.renfo(2, "A2"),                      # renfo : 15 min de vélo en échauffement, pas de séance vélo à part
                   # jeudi 19 : rien du tout -> vélo facultatif
                   P.Entree(4, "velo", "Vélo route souple 1h", 60, "Vélo.", prefs=("10:00", "15:00"))]
        orig = planif.SEMAINES
        planif.SEMAINES = {"2026-11-16": semaine}
        self.addCleanup(lambda: setattr(planif, "SEMAINES", orig))

    def _places(self, occ=None):
        seances, _ = planif.construire(dt.date(2026, 11, 16), 7, dt.datetime(2026, 11, 15, 20, 0, tzinfo=PARIS), occ=occ or {},
                                       etat={"evenements": {}}, groupes={}, verrouilles={}, dures_init=set())
        return seances

    def test_recuperation_collee_avant_les_etirements(self):
        s = {(x.date, x.kind): x for x in self._places()}
        v, e = s[("2026-11-17", "velo_maison")], s[("2026-11-17", "etirements")]
        self.assertEqual((v.heure, v.duree, e.heure), ("16:10", 20, "16:30"))
        self.assertEqual(v.titre, "Vélo d'appartement 20 min (récupération)")
        self.assertEqual(v.etapes, (("fc", 1200, 100, 128),))
        self.assertIn("FC sous 128", v.description)

    def test_jours_avec_course_renfo_ou_velo_sans_seance_velo(self):
        par_jour = {}
        for x in self._places():
            par_jour.setdefault(x.date, []).append(x.kind)
        self.assertNotIn("velo_maison", par_jour["2026-11-16"] + par_jour["2026-11-18"] + par_jour["2026-11-20"])
        self.assertIn("velo_maison", par_jour["2026-11-19"])   # jour vide : facultatif

    def test_renfo_avec_echauffement_velo(self):
        r = next(x for x in self._places() if x.kind == "renfo")
        self.assertEqual(r.duree, 30 + 15)
        self.assertIn("15 min de vélo d'appartement souple", r.description)

    def test_journee_chargee_rien_en_plus(self):
        occ = {"2026-11-19": [{"debut": None, "fin": None, "bloque": True, "titre": "Forum"}]}
        self.assertFalse(any(x.date == "2026-11-19" and x.kind == "velo_maison" for x in self._places(occ)))

    def test_avant_un_objectif(self):
        self.assertEqual([planif.velo_minutes(dt.date(2026, 11, d)) for d in (22, 23, 26, 27, 28, 29, 30)], [20, 15, 15, None, None, None, 20])


class VeloSurLaMontre(unittest.TestCase):
    def test_seance_de_velo_avec_cible_fc(self):
        from src import garmin_course as gc
        c = gc.charge_utile((("fc", 1200, 100, 128),), "Vélo d'appartement 20 min", gc.VELO)
        s = c["workoutSegments"][0]["workoutSteps"][0]
        self.assertEqual((c["sportType"]["sportTypeKey"], c["estimatedDurationInSecs"]), ("cycling", 1200))
        self.assertEqual((s["targetType"]["workoutTargetTypeKey"], s["targetValueOne"], s["targetValueTwo"]), ("heart.rate.zone", 100.0, 128.0))

    def test_synchronisation_choisit_le_sport_velo(self):
        from src import garmin_renfo as gr
        envoyes = []

        class Faux:
            def upload_workout(self, d):
                envoyes.append(d["sportType"]["sportTypeKey"])
                return {"workoutId": 1 + len(envoyes)}

            def schedule_workout(self, w, date):
                return {"workoutScheduleId": 10 + len(envoyes)}
        etat = {"evenements": {"v.ics": {"cle": "2026-11-17|velo_maison", "date": "2026-11-17", "titre": "Vélo d'appartement 20 min (récupération)",
                                         "etapes": [["fc", 1200, 100, 128]]},
                               "c.ics": {"cle": "2026-11-18|ef", "date": "2026-11-18", "titre": "CAP: Footing EF 40 min", "etapes": [["e", 2400, 315, 335]]}}}
        gr.synchroniser(Faux(), etat, "2026-11-16")
        self.assertEqual(sorted(envoyes), ["cycling", "running"])
