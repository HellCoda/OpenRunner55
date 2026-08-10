# PRD — OpenRunner55

## Vision

Application desktop Linux permettant à un utilisateur de Garmin Forerunner 55 de synchroniser ses workouts et activités bidirectionnellement entre Garmin Connect et sa montre, sans dépendre de Windows ni d'un smartphone.

## Persona

**Franck (Leakorn)** — Développeur solo, Fedora/GNOME. Utilisateur réel d'un FR55. Crée des workouts sur Garmin Connect Web. Veut autonomie complète sur Linux. Publication open-source prévue mais usage avant tout personnel.

## Parcours utilisateur

### Parcours A — Envoyer un workout vers la montre
1. L'utilisateur ouvre l'application sur Fedora.
2. L'application s'authentifie à Garmin Connect (email + mot de passe, stockés localement).
3. L'utilisateur consulte la liste de ses workouts Garmin Connect, triés du plus récent au plus ancien.
4. L'utilisateur sélectionne un ou plusieurs workouts.
5. L'utilisateur branche sa montre en USB.
6. L'utilisateur clique sur « Envoyer vers la montre ».
7. Les workouts sont téléchargés (.FIT) et copiés dans le dossier approprié de la montre.
8. L'application confirme le transfert et journalise l'opération.

### Parcours B — Remonter les données de la montre vers Garmin Connect
1. L'utilisateur ouvre l'application.
2. Authentification à Garmin Connect.
3. L'utilisateur branche sa montre en USB.
4. L'utilisateur consulte les fichiers présents sur la montre (activités, métriques santé), visuellement séparés des workouts provenant de Garmin Connect.
5. L'utilisateur clique sur « Synchroniser vers Garmin Connect ».
6. L'application lit les fichiers .FIT de la montre, filtre ceux exploitables par Garmin Connect, et les téléverse via l'API.
7. L'application affiche le résultat (succès/échec par fichier) et journalise l'opération.

### Parcours C — Consulter l'historique
1. L'utilisateur ouvre l'application.
2. L'utilisateur consulte l'onglet historique.
3. L'application affiche les syncs passés (date, sens, nombre de fichiers, statut).

## Exigences fonctionnelles

### Authentification

| ID | Exigence |
|----|----------|
| EF-1 | L'application authentifie l'utilisateur auprès de Garmin Connect via email et mot de passe. |
| EF-2 | Les identifiants sont stockés localement de manière sécurisée (non en clair). |
| EF-3 | L'utilisateur peut mettre à jour ou supprimer ses identifiants stockés. |
| EF-4 | L'application notifie l'utilisateur si l'authentification échoue ou si la session expire. |

### Workouts — Garmin Connect → Montre

| ID | Exigence |
|----|----------|
| EF-5 | L'application récupère la liste des workouts disponibles sur Garmin Connect. |
| EF-6 | Les workouts sont affichés triés du plus récent au plus ancien. |
| EF-7 | L'utilisateur peut sélectionner un ou plusieurs workouts à envoyer. |
| EF-8 | L'application télécharge les workouts sélectionnés au format .FIT. |
| EF-9 | L'application copie les fichiers .FIT dans le dossier workouts de la montre connectée en USB. |
| EF-10 | L'application détecte la présence de la montre en USB avant le transfert. |

### Activités & métriques — Montre → Garmin Connect

| ID | Exigence |
|----|----------|
| EF-11 | L'application lit les fichiers .FIT présents sur la montre (activités, métriques santé : fréquence cardiaque, body battery, pas, stress). |
| EF-12 | L'application affiche la liste des fichiers présents sur la montre avec leurs métadonnées brutes (type, date, taille), en distinguant visuellement les fichiers natifs de la montre (activités, métriques) des fichiers importés depuis Garmin Connect (workouts). |
| EF-13 | L'application filtre les fichiers exploitables par Garmin Connect (exclusion des fichiers spécifiques à la montre non pris en charge). |
| EF-14 | L'application téléverse les fichiers sélectionnés via l'API Garmin Connect. |
| EF-15 | L'application affiche le résultat du téléversement par fichier (succès/échec). |
| EF-21 | L'application sépare visuellement les deux sources de fichiers : fichiers natifs de la montre (activités, métriques santé) d'un côté, workouts importés depuis Garmin Connect de l'autre. |

### Interface & historique

| ID | Exigence |
|----|----------|
| EF-16 | L'application propose une interface graphique native (GTK privilégié, fallback app web locale si coût trop élevé). |
| EF-17 | L'application affiche un historique des synchronisations (date, sens, nombre de fichiers, statut). |
| EF-18 | L'application affiche des logs d'opération consultables par l'utilisateur. |

### Robustesse

| ID | Exigence |
|----|----------|
| EF-19 | En cas d'erreur 429 (rate limiting), l'application réessaie avec un backoff exponentiel. |
| EF-20 | L'application gère les erreurs de connexion USB (montre débranchée en cours de transfert) et notifie l'utilisateur. |

## Exigences non-fonctionnelles

| ID    | Exigence                                                                                                                  |
| ----- | ------------------------------------------------------------------------------------------------------------------------- |
| ENF-1 | **Performance** — Une sync de 10 workouts s'exécute (~40-60s -> ajustement empirique. (hors rate limiting)).              |
| ENF-2 | **Fiabilité** — Aucune perte de données en cas d'échec partiel : les fichiers non transférés restent identifiables.       |
| ENF-3 | **Portabilité** — L'application fonctionne sur Fedora/GNOME. Dépendances installables via pip et gestionnaire de paquets. |
| ENF-4 | **Sécurité** — Les identifiants Garmin ne sont jamais écrits dans les logs ni exposés dans le code source.                |
| ENF-5 | **Sécurité** — Les identifiants stockés localement sont chiffrés ou stockés via un mécanisme système (ex. keyring GNOME). |
| ENF-6 | **Maintenabilité** — Code structuré en modules : auth, API Garmin, USB/montre, UI, logs.                                  |

## Contraintes

| Type | Contrainte |
|------|-----------|
| **Technique** | Python 3, API `garminconnect` (validée par ADR-001 et spike). |
| **Technique** | Montre FR55 accessible en USB mass storage (dossiers .FIT). |
| **Technique** | GTK / GNOME comme environnement cible (préférence utilisateur). |
| **Technique** | Pas de Bluetooth, pas de smartphone, pas de Windows. |
| **API** | Rate limiting 429 observé sur Garmin Connect. Sync manuelle uniquement. |
| **Auth** | L'authentification email+mot de passe via `garminconnect` doit être validée sans session navigateur préalable. **Spike S-2 à planifier.** |
| **Légale** | Projet open-source. Identifiants personnels non inclus dans le dépôt. |
| **Budget** | Coût nul. Outils libres uniquement. |

## Incertitudes documentées

| ID | Incertitude | Impact | Action |
|----|------------|--------|--------|
| INC-1 | Auth sans session navigateur préalable non confirmée | Bloquant si échec | Spike S-2 avant Phase 4 |
| INC-2 | Filtre exact des fichiers .FIT acceptés par Garmin Connect | Fonctionnalité de remontée partielle | Tests empiriques en Phase 3/4 |
| INC-3 | Choix définitif GTK vs app web locale | Architecture UI | Décision Architecte Phase 3 |