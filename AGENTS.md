# Instructions pour les Agents IA — `coach-sport`

Ce guide s'adresse à tout agent (Claude Code, Gemini CLI, Antigravity) intervenant sur le dépôt.

## Principes Directeurs
1. **Zéro fuite de données personnelles** : Ne jamais écrire en dur de nom d'athlète, d'adresse personnelle, d'IP locale ni de clé API dans le code versionné. Toute donnée vit dans `profile.yaml`, `plan.yaml` ou `coach.env`.
2. **Architecture modulaire & no-op** : Si un service tiers (Garmin, Strava, CalDAV, ntfy, Home Assistant) n'est pas configuré dans l'environnement, le code ne doit jamais crasher et doit basculer en mode console/silencieux.
3. **Multiplateforme** : Toujours utiliser `pathlib`, `chemins.py` et `encoding="utf-8"`. Ne jamais supposer la présence d'outils POSIX exclusifs (`fcntl`, scripts shell).
4. **Sécurité sportive** : Se conformer impérativement aux règles de `docs/SECURITE.md` et `prompts/reprise_blessure.md`.

## Démarrage Rapide (Si l'utilisateur te demande de configurer le coach)

Si l'utilisateur te dit « installe ce projet », « configure mon coach » ou « démarre mon plan » :
1. **Initialiser l'environnement** si besoin :
   - Linux/macOS : exécuter `./start.sh` ou créer `.venv` (`python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pyyaml platformdirs`).
   - Windows : exécuter `.\start.ps1`.
2. **Dérouler l'onboarding** :
   - Lire [`prompts/onboarding.md`](prompts/onboarding.md).
   - Poser les 5 questions essentielles à l'utilisateur (prénom, objectif, blessure éventuelle, matériel/montre, créneaux disponibles).
   - Créer son fichier `profile.yaml` depuis le modèle [`templates/profile.example.yaml`](templates/profile.example.yaml).
3. **Vérification** :
   - Lancer `python coach.py doctor` pour valider la configuration.
   - Afficher sa première séance avec `python coach.py next`.
   - Proposer d'exporter son calendrier via `python coach.py export-ics`.

## Commandes Principales
- Diagnostiquer la configuration : `python coach.py doctor`
- Afficher la prochaine séance : `python coach.py next [--date AAAA-MM-JJ]`
- Lancer les tests unitaires : `python -m pytest -q`
- Linter le code : `ruff check .`
