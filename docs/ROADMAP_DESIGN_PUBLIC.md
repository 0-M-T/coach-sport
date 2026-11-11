# Roadmap Design & Améliorations Publiques

Points à reprendre en priorité avec un agent de niveau supérieur (Claude Opus / modèle lourd) :

## 1. Identité visuelle & Logo (`docs/marque/`)
- [ ] **Refondre l'icône / logo** : Le SVG actuel (`docs/marque/logo.svg`) est trop simpliste.
  - Appliquer le protocole complet du skill `logo-design`.
  - Co-conception de 3 concepts vectoriels géométriques distincts (isotype pur, testé à 16 px, monochrome, zéro artifice).
  - Générer le kit complet : 4 types (isotype seul, wordmark seul, lockups horizontal & vertical) x 4 variantes (dark, light, mono blanc, mono noir) + exports multi-résolutions.

## 2. Refonte visuelle du `README.md`
- [ ] **Mise en page et direction artistique** :
  - Remplacer l'en-tête actuel par un `<picture>` adaptatif (thème sombre / thème clair).
  - Intégrer de vraies captures visuelles soignées (mockups de notification ntfy sur mobile, affichage terminal riche, aperçu calendrier).
  - Restructurer la hiérarchie visuelle pour une lecture fluide en 30 secondes.

## 3. Schémas d'architecture vectoriels
- [ ] **Schémas D2 / Kroki** (`docs/schemas/`) :
  - Remplacer les diagrammes SVG basiques par des schémas D2 générés via Kroki (ELK routing, coins 16-20px, tokens de marque, conformité WCAG AA).
