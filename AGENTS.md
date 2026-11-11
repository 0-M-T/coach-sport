# Instructions pour les Agents IA — `coach-sport`

Ce guide s'adresse à tout agent (Claude Code, Gemini CLI, Antigravity) intervenant sur le dépôt.

## Principes Directeurs
1. **Zéro fuite de données personnelles** : Ne jamais écrire en dur de nom d'athlète, d'adresse personnelle, d'IP locale ni de clé API dans le code versionné. Toute donnée vit dans `profile.yaml`, `plan.yaml` ou `coach.env`.
2. **Architecture modulaire & no-op** : Si un service tiers (Garmin, Strava, CalDAV, ntfy, Home Assistant) n'est pas configuré dans l'environnement, le code ne doit jamais crasher et doit basculer en mode console/silencieux.
3. **Multiplateforme** : Toujours utiliser `pathlib`, `chemins.py` et `encoding="utf-8"`. Ne jamais supposer la présence d'outils POSIX exclusifs (`fcntl`, scripts shell).
4. **Sécurité sportive** : Se conformer impérativement aux règles de `docs/SECURITE.md` et `prompts/reprise_blessure.md`.

## Commandes Principales
- Diagnostiquer la configuration : `python coach.py doctor`
- Afficher la prochaine séance : `python coach.py next [--date AAAA-MM-JJ]`
- Lancer les tests unitaires : `python -m pytest -q`
- Linter le code : `ruff check .`
