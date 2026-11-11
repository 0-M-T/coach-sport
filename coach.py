#!/usr/bin/env python3
"""CLI Coach Sportif — Unification des commandes et protocoles d'entraînement."""

import argparse
import datetime as dt
import sys
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")

def get_next_workout(target_date: str | None = None) -> None:
    """Séances de l'agenda Sport à une date, avec le corps de séance du plan pour celles posées par le coach."""
    from src import baikal, planif
    target_date = target_date or dt.datetime.now(PARIS).strftime("%Y-%m-%d")
    try:
        events = baikal.lister(target_date)
    except FileNotFoundError:
        events = []
    if not events:
        from src.plan import SEMAINES
        d = dt.date.fromisoformat(target_date)
        lundi = (d - dt.timedelta(days=d.weekday())).isoformat()
        seances = [s for s in SEMAINES.get(lundi, []) if s.jour == d.weekday()]
        if seances:
            print(f"=== Séances du plan pour le {target_date} ===")
            for s in seances:
                print(f"* {s.titre} ({s.duree} min) : {s.corps}")
            return
        print(f"Aucune séance programmée pour le {target_date}.")
        return
    print(f"=== Séances du {target_date} ===")
    for s in planif.seances_du_jour(target_date, [baikal.parse(l) for l in events]):
        print(f"* {s}")


def _alerter_une_fois_par_semaine(msg: str) -> None:
    import time
    from src import chemins, ntfy
    from src.config import load_config
    marker = chemins.scope_alert_path()
    if marker.exists() and time.time() - marker.stat().st_mtime < 7 * 86400:
        return
    conf = load_config()
    ntfy.envoyer(conf, "Coach : Strava en lecture seule", msg)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch()


def main():
    parser = argparse.ArgumentParser(description="CLI Coach Sportif")
    sub = parser.add_subparsers(dest="command")

    # next
    p_next = sub.add_parser("next", help="Afficher la séance du jour ou à une date")
    p_next.add_argument("--date", help="Date cible (AAAA-MM-JJ)")

    # doctor
    sub.add_parser("doctor", help="Vérifier la configuration et les connexions actives")

    # init
    sub.add_parser("init", help="Initialiser ou modifier votre profil athlète (questionnaire)")

    # export-ics
    p_ics = sub.add_parser("export-ics", help="Exporter les séances au format calendrier standard (.ics)")
    p_ics.add_argument("--jours", type=int, default=28, help="Nombre de jours à exporter (défaut : 28)")
    p_ics.add_argument("--sortie", default="entrainements.ics", help="Chemin du fichier de sortie")

    # ressenti / RPE
    p_rpe = sub.add_parser("ressenti", help="Noter le ressenti d'effort de la séance (RPE 1-10)")
    p_rpe.add_argument("note", type=int, help="Note d'effort de 1 (très facile) à 10 (maximal)")
    p_rpe.add_argument("--date", help="Date de la séance (AAAA-MM-JJ)")
    p_rpe.add_argument("--commentaire", default="", help="Remarque ou sensation particulière")

    # sync
    sub.add_parser("sync", help="Synchroniser Garmin Connect vers Baïkal")

    # notify
    p_notify = sub.add_parser("notify", help="Envoyer la notification du coach via ntfy")
    p_notify.add_argument("--soir", action="store_true", help="Notification du soir")
    p_notify.add_argument("--semaine", action="store_true", help="Récap de la semaine et briefing de la suivante (dimanche)")
    p_notify.add_argument("--reveil", action="store_true", help="Attendre les données de la nuit (cron toutes les 10 min)")
    p_notify.add_argument("--force", action="store_true", help="Renvoyer même si déjà envoyé aujourd'hui")

    # strava
    sub.add_parser("strava", help="Synchroniser Strava vers Home Assistant")
    p_en = sub.add_parser("strava-enrich", help="Nommer/décrire les activités Strava (dry-run sans --apply)")
    p_en.add_argument("--apply", action="store_true")
    p_bf = sub.add_parser("strava-backfill", help="Passage unique sur l'historique (dry-run sans --apply)")
    p_bf.add_argument("--jours", type=int, default=60)
    p_bf.add_argument("--apply", action="store_true")
    p_ch = sub.add_parser("chaussures", help="Vérifier l'usure des chaussures (notification seulement si un seuil est franchi)")
    p_ch.add_argument("--dry-run", action="store_true")
    p_hu = sub.add_parser("strava-humour", help="Ajouter la phrase d'humour aux descriptions déjà posées par le coach")
    p_hu.add_argument("--apply", action="store_true")
    p_wh = sub.add_parser("strava-webhook", help="Récepteur du webhook Strava, ou gestion de l'abonnement")
    p_wh.add_argument("action", choices=["servir", "voir", "creer", "supprimer"])
    p_wh.add_argument("--url", help="URL publique de rappel (pour creer)")
    p_pl = sub.add_parser("planifier", help="Placer les séances du plan dans l'agenda (dry-run sans --apply)")
    p_pl.add_argument("--jours", type=int, default=14)
    p_pl.add_argument("--apply", action="store_true")
    p_pl.add_argument("--reagir", action="store_true", help="Passage périodique (cron) : notifie seulement les changements")
    p_pl.add_argument("--annuler", action="store_true", help="Retirer les séances futures créées par le coach")
    p_rj = sub.add_parser("rejouer", help="Appliquer les règles du coach à l'historique réel (lecture seule)")
    p_rj.add_argument("--jours", type=int, default=28)
    p_bo = sub.add_parser("boucles", help="Parcours de l'historique au départ de la maison : catalogue, suggestion, export GPX")
    p_bo.add_argument("--maj", action="store_true", help="Relire l'historique Strava")
    p_bo.add_argument("--suggere", nargs=2, metavar=("TYPE", "MINUTES"), help="ex. ef 40")
    p_bo.add_argument("--gpx", type=int, metavar="ID_ACTIVITE")
    p_bo.add_argument("--ntfy", action="store_true", help="envoyer le GPX en pièce jointe ntfy")
    sub.add_parser("sauvegarde", help="Sauvegarde quotidienne des fichiers du coach (14 jours)")
    p_au = sub.add_parser("strava-auth", help="Ré-autoriser Strava avec activity:write")
    p_au.add_argument("--code")

    args = parser.parse_args()
    if args.command not in (None, "next", "strava-webhook", "rejouer"):
        # crons, webhook et lancements à la main partagent les fichiers d'état : un seul écrivain à la fois
        from src.config import verrou
        try:
            _verrou = verrou()  # noqa: F841 (gardé ouvert jusqu'à la fin du processus)
        except TimeoutError as e:
            print(f"{args.command} : {e}, passage abandonné", file=sys.stderr)
            sys.exit(75)
    job = {"sync": "garmin_sync", "strava": "strava_ha", "strava-enrich": "strava_enrich", "chaussures": "chaussures", "planifier": "planifier", "sauvegarde": "sauvegarde",
           "notify": "semaine" if getattr(args, "semaine", False) else "soir" if getattr(args, "soir", False) else "matin"}.get(args.command)
    if job:
        import time as _t
        from src import suivi
        t0, code = _t.time(), 0
        try:
            _executer(args, parser)
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
            raise
        except Exception:
            code = 1
            raise
        finally:
            suivi.ecrire(job, code, _t.time() - t0, envoye=suivi.ENVOYE)
        return
    _executer(args, parser)


def _executer(args, parser):

    if args.command == "next":
        get_next_workout(args.date)
    elif args.command == "doctor":
        from src.doctor import afficher_rapport
        sys.exit(afficher_rapport())
    elif args.command == "init":
        from src.init_cli import run_init
        sys.exit(run_init())
    elif args.command == "export-ics":
        from src.export_ics import exporter_fichier
        dest = exporter_fichier(args.sortie, jours=args.jours)
        print(f"[OK] Fichier calendrier généré : {dest}")
    elif args.command == "ressenti":
        from src.ressenti import enregistrer_rpe
        res = enregistrer_rpe(args.note, args.commentaire, args.date)
        print(f"[OK] Ressenti RPE {res['note']}/10 enregistré.")
    elif args.command == "sync":
        from src.garmin_sync import sync_garmin_to_baikal
        sync_garmin_to_baikal()
    elif args.command == "notify" and args.semaine:
        from src.semaine import run as run_semaine
        sys.exit(run_semaine(force=args.force))
    elif args.command == "notify":
        from src.agent_coach import run_agent_coach
        sys.exit(run_agent_coach(soir=args.soir, force=args.force, reveil=args.reveil))
    elif args.command == "strava":
        from src.strava_sync import sync_strava_to_ha
        sync_strava_to_ha()
    elif args.command == "strava-enrich":
        from src.strava import QuotaError, ScopeError
        from src.strava_enrich import run
        try:
            run(apply=args.apply)
        except ScopeError as e:
            print(e, file=sys.stderr)
            _alerter_une_fois_par_semaine(str(e))
            sys.exit(2)
        except QuotaError as e:  # transitoire : le passage suivant (10 min) reprend, ce n'est pas une panne
            print(f"Quota Strava atteint, reprise au prochain passage ({e})")
    elif args.command == "strava-backfill":
        from src.strava_enrich import backfill
        from src.strava import QuotaError
        try:
            backfill(args.jours, args.apply)
        except QuotaError as e:
            print(f"Arrêt propre : {e}. Relancer la même commande, elle reprend où elle s'est arrêtée.")
            sys.exit(3)
    elif args.command == "chaussures":
        from src.materiel import verifier
        for t, corps in verifier(envoyer=not args.dry_run):
            print(t, "\n", corps)
    elif args.command == "strava-humour":
        from src.strava_enrich import humour_retroactif
        humour_retroactif(args.apply)
    elif args.command == "strava-webhook":
        from src import webhook
        webhook.servir() if args.action == "servir" else webhook.abonnement(args.action, args.url)
    elif args.command == "planifier":
        from src import planif
        if args.reagir:
            sys.exit(planif.reagir())
        elif args.annuler:
            print("\n".join(planif.annuler(args.apply)) or "Rien à annuler")
        else:
            try:
                comp, notes = planif.planifier(jours=args.jours, apply=args.apply)
                print("\n".join(comp) or "Agenda déjà à jour")
                print("\n".join(f"A VOIR : {n}" for n in notes))
            except FileNotFoundError as e:
                print(f"Agenda non disponible ({e}).", file=sys.stderr)
    elif args.command == "rejouer":
        from src import rejeu
        print(rejeu.formater(rejeu.rejouer(args.jours)))
    elif args.command == "boucles":
        from src import boucles
        from src.config import load_config
        if args.maj:
            r = boucles.maj(load_config())
            print(f"{len(r)} parcours au départ de la maison")
        if args.suggere:
            r = boucles.suggere(args.suggere[0], int(args.suggere[1]))
            print(r or "Aucun parcours adapté")
        if args.gpx:
            f = boucles.gpx(load_config(), args.gpx)
            print(f)
            if args.ntfy:
                boucles.envoyer_gpx(load_config(), f, f"Parcours GPX {args.gpx}")
    elif args.command == "sauvegarde":
        from src.sauvegarde import sauvegarder
        print(sauvegarder())
    elif args.command == "strava-auth":
        from src.strava_auth import run
        run(args.code)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
