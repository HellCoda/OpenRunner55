# MVP — OpenRunner55

## Définition

Le MVP regroupe tous les **Must** du MoSCoW. C'est la plus petite version du produit qui teste l'hypothèse : une application desktop Linux qui synchronise bidirectionnellement Garmin Connect et la montre FR55, sans Windows ni smartphone.

## Périmètre

### Stories du MVP (10)

| ID | Story | Epic |
|----|-------|------|
| US-1.1 | Authentifier l'utilisateur avec email et mot de passe Garmin Connect | 1 — Auth |
| US-1.2 | Stocker les identifiants localement de manière sécurisée | 1 — Auth |
| US-1.3 | Mettre à jour ou supprimer les identifiants stockés | 1 — Auth |
| US-1.4 | Notifier si la session expire ou l'authentification échoue | 1 — Auth |
| US-2.1 | Lister les workouts disponibles sur Garmin Connect, triés du plus récent au plus ancien | 2 — Cloud → Montre |
| US-2.3 | Sélectionner un ou plusieurs workouts et les pousser sur le FR55 via USB | 2 — Cloud → Montre |
| US-3.1 | Lire les fichiers .FIT présents sur la montre (activités et métriques) | 3 — Montre → Cloud |
| US-3.2 | Remonter les fichiers sélectionnés vers Garmin Connect | 3 — Montre → Cloud |
| US-4.1 | Afficher une interface GTK avec les sections : workouts Cloud, fichiers montre, historique | 4 — UI |
| US-4.2 | Séparer visuellement les fichiers natifs de la montre et les fichiers importés depuis Garmin Connect | 4 — UI |

### Ce qui est dans le MVP

- Authentification Garmin Connect (email + mot de passe, stockage local)
- Liste des workouts Garmin Connect avec tri récent → ancien
- Sélection manuelle et envoi de workouts vers le FR55
- Lecture des fichiers .FIT sur la montre via USB
- Remontée des activités et métriques vers Garmin Connect
- Interface GTK avec séparation visuelle des sources

### Ce qui n'est PAS dans le MVP

- Détection des doublons (workouts déjà présents sur la montre) → Should (US-2.2)
- Suppression de workouts de la montre → Should (US-2.4)
- Filtre intelligent des fichiers .FIT acceptés par Garmin Connect → Should (US-3.3)
- Historique des synchronisations et logs → Should (US-4.3)
- Retry avec backoff sur rate limiting 429 → Should (US-5.1)
- Reconnexion automatique en cas d'expiration de session → Could (US-5.2)
- Notifications desktop → Could (US-5.3)
- Synchronisation automatique → Won't
- Interprétation graphique des données → Won't
- Firmware OTA → Won't
- Multi-utilisateurs → Won't

## Estimation

| Epic | Stories MVP | Estimation |
|------|------------|------------|
| 1 — Auth | 4 | 1,5 jour |
| 2 — Cloud → Montre | 2 | 1,5 jour |
| 3 — Montre → Cloud | 2 | 2 jours |
| 4 — UI | 2 | 2 jours |
| **Total** | **10** | **~7 jours/homme** |

> Estimation macro, hors spikes et imprévus. L'incertitude INC-1 (auth sans navigateur) peut impacter l'Epic 1.

## Condition de validation

> **Le MVP est validé quand un workout créé sur Garmin Connect est sélectionné dans l'application, poussé sur le FR55 via USB, et qu'une activité enregistrée sur la montre est remontée avec succès sur Garmin Connect — le tout depuis l'interface GTK.**

## Risques MVP

| Risque | Impact | Mitigation |
|--------|--------|------------|
| INC-1 : auth sans navigateur préalable | **Bloquant** — si échec, US-1.1 à 1.4 invalides | Spike avant démarrage Epic 1 |
| INC-3 : GTK vs app web | Moyen — si GTK trop coûteux, fallback app web locale | Décision Architecte Phase 3 |
| Rate limiting 429 | Faible — sync manuelle ponctuelle | Retry basique en Should (US-5.1) |
| Filtre .FIT non maîtrisé | Faible — remontée brute, ajustement empirique | US-3.3 en Should pour affiner |

## Dépendances externes

| Dépendance | Statut | Impact si blocage |
|-----------|--------|-----------------|
| API `garminconnect` (Python) | ✅ Validé (spike + ADR-001) | — |
| USB mass storage FR55 | ✅ Validé (spike) | — |
| GTK / GNOME | ⚠️ À confirmer (INC-3) | Fallback app web locale |
| Auth sans navigateur | ⚠️ À tester (INC-1) | Bloquant — spike requis |

## Ordre de construction suggéré

1. **Spike INC-1** — tester auth sans navigateur (0,5 jour)
2. **Epic 1** — authentification (1,5 jour)
3. **Epic 2** — workouts Cloud → Montre (1,5 jour)
4. **Epic 3** — activités Montre → Cloud (2 jours)
5. **Epic 4** — interface GTK (2 jours)

> L'UI (Epic 4) arrive en dernier car elle dépend des Epics 1-3 pour avoir du contenu à afficher. Cependant, un squelette d'interface peut démarrer en parallèle dès que l'Epic 1 est validé.

---

*Product Manager — MVP défini. Phase 2 prête pour la gate de sortie.*