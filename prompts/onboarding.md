# Guide d'Onboarding Athlète (Session Agent IA)

Ce guide s'exécute lors du premier lancement de `coach-sport` par un nouvel utilisateur.

## Protocole en 4 étapes

### Étape 1 : Diagnostic & Cadrage (5 questions essentielles)
Poser ces questions de façon synthétique et structurée :
1. **Identité & prénom** : Comment t'appelles-tu ? (âge, taille, poids si connus)
2. **Objectif prioritaire** : Reprise progressive (post-blessure) ? 5 km ? 10 km ? Semi ? Marathon ? Trail ? Avec quelle date cible ?
3. **Historique & Blessures** : As-tu eu une blessure récente (entorse, tendinite, déchirure) ? Depuis combien de temps es-tu arrêté ?
4. **Matériel & Écosystème** : As-tu une montre connectée (Garmin, Coros, Suunto, Apple) ou cours-tu avec ton smartphone ? As-tu un compte Strava ?
5. **Disponibilités** : Combien de jours par semaine peux-tu t'entraîner et quels jours préfères-tu (ex : mardi, jeudi, samedi) ?

### Étape 2 : Import ou saisie physiologique
- Si montre ou Strava disponible : proposer de connecter le compte (`coach connecter strava` ou `garmin`).
- Si pas de capteur / reprise : démarrer sur des séances guidées au temps (marche/course) sans imposer d'allure cible au km.

### Étape 3 : Génération du profil et du plan
1. Écrire le fichier `profile.yaml` (dans `~/.config/coach-sport/profile.yaml` ou le dossier `COACH_HOME`).
2. Sélectionner ou instancier le plan adapté depuis `templates/` (ex : `templates/plan.reprise.yaml`).
3. Présenter le résumé de la semaine 1 à l'utilisateur et demander sa validation.

### Étape 4 : Première séance
Afficher la séance du jour via :
```bash
coach next
```
Indiquer comment installer l'application de notifications `ntfy` si souhaité.
