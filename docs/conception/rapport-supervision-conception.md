# Rapport de Supervision — Phase de Conception

- **Date** : 2026-08-08
- **Auteur** : Directeur de Projet
- **Périmètre** : Revue d'alignement des ADR-002 à ADR-007 (architecte backend) vs documents amont (project-brief, PRD, MVP, epics, ADR-001, spike S-2, tree-FR55)
- **Objectif** : Détecter manquements, incohérences et décalages avant l'entrée en phase de développement

---

## Verdict global

**🟡 Alignement satisfaisant, 3 points majeurs à corriger avant le dev.**

Les 6 ADRs couvrent l'ensemble des exigences du PRD et des user stories du MVP. Les décisions techniques sont cohérentes avec les résultats du spike S-2. L'architecture est pragmatique et adaptée à un projet solo.

Cependant, **3 incohérences majeures** doivent être résolues avant d'entrer en phase 4 (Développement), sous peine de refactoring coûteux ou de violation de spécifications. Six points moyens et huit points mineurs complètent le tableau.

---

## Tableau de synthèse

| #     | Gravité    | ADR concerné     | Résumé                                                                                            |
| ----- | ---------- | ---------------- | ------------------------------------------------------------------------------------------------- |
| M1    | **Majeur** | ADR-002, ADR-007 | Dépendance circulaire `auth` ↔ `garmin` — violation de la règle cardinale                         |
| M2    | **Majeur** | ADR-007 vs PRD   | ENF-1 (10 workouts < 30s) potentiellement violée par le délai inter-requêtes de 3s                |
| M3    | **Majeur** | ADR-002          | Comptage de modules incohérent (« 8 modules » ne correspond à aucun décompte)                     |
| C1    | Moyen      | ADR-002          | Accès UI aux logs/historique — pas de service défini, violation potentielle de la règle cardinale |
| C2    | Moyen      | —                | Pas de stratégie de tests définie (framework, mocks, couverture)                                  |
| C3    | Moyen      | —                | Pas d'ADR packaging/distribution (installation, dépendances système)                              |
| C4    | Moyen      | ADR-007          | Calcul du timeout max incohérent (tableau vs prose)                                               |
| C5    | Moyen      | ADR-002, ADR-005 | Déduplication des activités — pas de persistance locale de l'état des transferts                  |
| C6    | Moyen      | ADR-004          | MFA non couvert — parcours UI non défini (risque résiduel)                                        |
| D1–D8 | Mineur     | Divers           | Voir section dédiée                                                                               |

---

## Points MAJEURS (à corriger avant le dev)

### M1 — Dépendance circulaire `auth` ↔ `garmin`

**ADR concernés :** ADR-002 (architecture en couches), ADR-007 (cascade auth sur 401)

**Problème :**

ADR-002 place `auth/` en couche **Service** et `garmin/` en couche **Core**. La règle cardinale stipule : « La couche N appelle uniquement la couche N-1. » Or :

1. **Core → Service (interdit) :** ADR-007 § « Gestion du 401 » indique que `garmin/client.py` (Core) appelle `auth.authenticator.refresh_session()` puis `resume_session()` puis `login()` sur erreur 401. Core appelle Service = **dépendance remontante**.

2. **Service → Core (autorisé mais problématique ici) :** ADR-002 définit `Authenticator.get_client() -> GarminClient` — le Service instancie et retourne un objet Core.

3. **Dépendance circulaire confirmée :** `auth` dépend de `garmin` (via `get_client()`) ET `garmin` dépend de `auth` (via refresh 401).

**Cause racine :** La bibliothèque `garminconnect` fusionne auth et client dans un seul objet `Garmin()` (confirmé par les scripts du spike — `bloc1_auth_headless.py` et `bloc3_upload_activity.py` utilisent le même objet pour login et appels API). La séparation artificielle en deux modules de couches différentes recrée une circularité que la lib n'a pas.

**Alternatives :**

| Option | Description | Avantage | Inconvénient |
|--------|-------------|----------|--------------|
| **A. Descendre `auth/` en Core** | `auth/` et `garmin/` sont tous deux Core. Ils encapsulent ensemble l'objet `Garmin()`. | Respecte la réalité de la lib. Supprime la circularité. | `auth` n'est plus un Service — l'orchestration login/tokenstore/refresh devient Core. |
| **B. Callback / injection** | `garmin/client.py` reçoit une callback `on_401` injectée par `auth/`. Core ne connaît pas `auth`, il appelle la callback. | Préserve le découpage en couches. | Complexifie l'interface pour un projet de 7 j/h. |
| **C. Fusionner `auth/` et `garmin/`** | Un seul module Core `garmin/` qui gère auth + client + retry. | Simple, fidèle à la lib. | ADR-002 perd la séparation auth/client. Module plus gros. |

**Recommandation :** Option A. C'est la plus fidèle à la réalité de `garminconnect` et la plus simple. `auth/` devient un module Core qui encapsule le login/tokenstore/keyring, et `garmin/client.py` peut légitimement l'appeler pour le re-login 401.

---

### M2 — ENF-1 (perf < 30s) vs ADR-007 (délai inter-requêtes 3s)

**ADR concernés :** ADR-007 § « Délai inter-requêtes » vs PRD ENF-1

**Problème :**

- **ENF-1 :** « Une sync de 10 workouts s'exécute en moins de 30 secondes (hors rate limiting). »
- **ADR-007 :** délai minimum de **3 secondes** entre deux requêtes API consécutives.

Calcul pour 10 workouts (parcours A : GC → Montre) :
- 1 requête `get_workouts()` + 10 requêtes `download_workout()` = 11 requêtes
- 11 × 3s de délai inter-requêtes = **33s minimum**, sans compter le temps de téléchargement et de copie USB
- Total réel estimé : **~40-45s**

Le délai de 3s est **préventif** (pour ne pas déclencher le 429), pas **réactif** (en réponse à un 429). La mention « hors rate limiting » dans ENF-1 est ambiguë : s'agit-il du rate limiting réactif (429 reçu) ou aussi du préventif (délai artificiel) ?

**Alternatives :**

| Option | Description |
|--------|-------------|
| **A. Revoir ENF-1 à la hausse** | Passer le seuil à 60s. Réaliste compte tenu du délai préventif. |
| **B. Réduire le délai pour les downloads** | Différencier : 3s pour les uploads (plus risqués), 1s pour les downloads de workouts (moins sensibles). |
| **C. Documenter l'interprétation** | Considérer le délai de 3s comme du « rate limiting préventif » → exclu du compteur ENF-1. Le 30s s'applique au temps de traitement pur (download + copie USB). |

**Recommandation :** Option C, avec mise à jour d'ENF-1 pour clarifier : « moins de 30 secondes de temps de traitement (hors délais anti-rate-limiting et hors rate limiting réactif). » Si Franck veut un seuil utilisateur perçu, ajouter : « temps total perçu < 60s pour 10 workouts. »

---

### M3 — Comptage de modules incohérent

**ADR concerné :** ADR-002

**Problème :**

ADR-002 annonce « 8 modules Python » mais :

- **Packages de premier niveau** dans `src/openrunner55/` : `auth`, `garmin`, `watch`, `sync`, `fit`, `store`, `ui` = **7 packages**
- **Modules si on compte les sous-modules de `sync/`** : auth, garmin, watch, fit, store, sync/workouts, sync/activities, sync/wellness, ui = **9 modules**
- **Le tableau de l'ADR liste 9 lignes** (une par module/sous-module)

Le chiffre « 8 » ne correspond à aucun décompte logique.

**Recommandation :** Corriger en « 7 packages, 9 modules » ou clarifier le décompte retenu.

---

## Points MOYENS (à clarifier avant le dev)

### C1 — Accès UI aux logs et historique : service manquant

**Problème :** ADR-002 stipule « L'UI appelle uniquement les Services. » Mais :

- US-4.2 (Must) : l'UI affiche l'historique des syncs → doit appeler `store/history.py` (Core) pour `get_history()`.
- US-4.3 (Should) : l'UI affiche les logs → doit appeler `store/logger.py` (Core) pour `get_logs()`.

Aucun service de consultation n'est défini dans la couche Service. Soit l'UI viole la règle cardinale (appelle Core directement), soit il manque un service.

**Recommandation :** Soit ajouter un service `sync/history.py` (ou `view/`) qui expose `get_sync_history()` et `get_logs()`, soit expliciter une exception : « L'UI peut appeler `store/` en lecture seule pour la consultation de l'historique et des logs. »

---

### C2 — Pas de stratégie de tests définie

**Problème :** ADR-002 mentionne « testable unitairement » mais aucun ADR ne définit :

- Framework de test (pytest ? unittest ?)
- Stratégie de mock pour Garmin Connect (réponses API enregistrées ? fixtures ?)
- Stratégie de mock pour USB (faux système de fichiers ? `tmp_path` ?)
- Couverture cible
- Tests d'intégration (avec montre branchée ? avec GC réel ?)

**Recommandation :** Produire un ADR-008 (stratégie de tests) avant le démarrage de l'Epic 1. Minimum : pytest + mocks pour `Garmin()` et `WatchFilesystem`.

---

### C3 — Pas d'ADR packaging/distribution

**Problème :** `pyproject.toml` est mentionné dans ADR-002 mais aucun ADR ne couvre :

- Mode d'installation (pip install . ? flatpak ? script shell ? `uv` ?)
- Gestion des dépendances système : PyGObject (`python3-gobject` via dnf), libudev (présent), gnome-keyring (présent)
- Point d'entrée (commande `openrunner55` → `src/main.py` ?)
- Fichier `.desktop` pour intégration GNOME (lancement depuis le menu)

**Recommandation :** ADR-009 (packaging) avant la fin du dev. Non bloquant pour démarrer l'Epic 1, mais nécessaire avant l'Epic 4 (UI).

---

### C4 — Calcul du timeout max incohérent dans ADR-007

**Problème :**

- **Tableau de backoff :** « Échec — Abandon — ~10 s max » (1+2+4 = 7s de délais de retry)
- **Prose :** « ~18 secondes (3 retries × jusqu'à 4s d'attente + 3 × 3s inter-requêtes + temps réseau) » = 12 + 9 + réseau ≈ **21s+**

Les deux valeurs ne sont pas cohérentes. Le tableau ne compte que les délais de backoff ; la prose ajoute les délais inter-requêtes.

**Recommandation :** Clarifier dans ADR-007 : distinguer « délai de backoff cumulé » (7s) et « temps total max par requête incluant inter-requêtes » (~21s). Mettre à jour le tableau.

---

### C5 — Déduplication des activités : pas de persistance locale

**Problème :**

- ADR-002 : `sync/activities.py` filtre les déjà présents « par comparaison timestamps » avec `get_activities()` de GC.
- Le schéma SQLite (ADR-005) n'a pas de table pour suivre les fichiers déjà transférés.
- Risque : `get_activities(start=0, limit=20)` ne retourne que 20 activités. Si la montre contient plus de 20 activités non remontées, ou si GC ne retourne pas l'historique complet, la déduplication est incomplète → re-upload de doublons.

**Recommandation :** Ajouter une table `transferred_files` au schéma SQLite :

```sql
CREATE TABLE transferred_files (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name   TEXT NOT NULL,
    file_hash   TEXT,              -- SHA256 du contenu (optionnel)
    direction   TEXT NOT NULL,     -- 'up' | 'down'
    source      TEXT NOT NULL,     -- 'activity' | 'monitor' | 'sleep' | 'metrics' | 'workout'
    transferred_at TEXT NOT NULL DEFAULT (datetime('now')),
    gc_activity_id BIGINT          -- ID côté GC si applicable
);
```

Cela permet une déduplication locale fiable, indépendante des limites de l'API GC.

---

### C6 — MFA non couvert

**Problème :**

- Spike S-2 : MFA non testée (compte sans MFA). Support API existant (`prompt_mfa` callback).
- ADR-004 mentionne « MFA callback » dans `authenticator.py` mais aucun ADR ne détaille le parcours MFA dans l'UI (saisie du code, retry, timeout).
- Si Franck active la MFA sur son compte Garmin, le parcours UI n'est pas défini.

**Recommandation :** Soit produire un mini-ADR ou une section dans ADR-004 décrivant le parcours MFA (champ de saisie de code dans `auth_view.py`, callback vers `Authenticator.login()`), soit documenter formellement comme risque résiduel accepté (« MFA non supportée dans le MVP ; si activée, l'auth échouera avec un message clair »).

---

## Points MINEURS (à noter pour la phase dev)

### D1 — HRV non peuplé : limitation non documentée

Le spike S-2 a découvert que `get_hrv_data` reste vide après upload des FIT natifs. ADR-002 (`sync/wellness.py`) ne mentionne pas cette limitation. **Action :** ajouter une note dans ADR-002 ou ADR-007.

### D2 — Nom de fichier workout sur la montre non tranché

Le spike S-2 utilise `{workoutId}.FIT` (ex: `1656951822.FIT`). Le tree-FR55 montre des noms lisibles (`VMA_workout.fit`, `10k-08_workout.fit`) provenant de Garmin Express. ADR-002 (`sync/workouts.py`) ne spécifie pas le nommage. **Action :** trancher — `{workoutId}.FIT` (fiable, évite les problèmes d'encodage FAT32) ou `{slug(workout_name)}.fit` (lisible mais fragile sur FAT32 avec accents).

### D3 — Dépendances Python non consolidées

Sources dispersées : spike S-2 (`garminconnect`, `curl_cffi`, `pydantic`, `garmin-fit-sdk`), ADR-004 (`secretstorage`), ADR-006 (`pyudev`), ADR-003 (`PyGObject` — système). Pas de liste consolidée. **Action :** consolider dans ADR-002 ou un ADR dédié.

### D4 — Version Python minimum non spécifiée

Le spike S-2 utilise Python 3.14. Aucun ADR ne spécifie `requires-python`. **Action :** spécifier dans `pyproject.toml` et ADR-002.

### D5 — Dossiers de la montre non gérés non mentionnés

`tree-FR55.md` documente `Schedule/`, `Sports/`, `Records/`, `Goals/`, `Totals/`, `Settings/`, `Sleep/`, `Monitor/`, `Metrics/`, `SUMMARY/`, `Activity/`, `Workouts/`. ADR-002 mentionne les dossiers gérés (Activity, Workouts, Monitor, Sleep, Metrics) mais n'explicite pas les dossiers ignorés. **Action :** ajouter une liste explicite « dossiers gérés / dossiers ignorés » dans ADR-002 ou ADR-006.

### D6 — Implémentation anticipée de fonctionnalités Should

ADR-005 crée `operation_logs` (US-4.3 = Should). ADR-007 implémente le retry 429 (US-5.1 = Should). Ce n'est pas un problème (architecture prévoyante), mais il faut s'assurer que le MVP n'est pas gonflé par ces implémentations. **Action :** marquer clairement dans l'implémentation ce qui relève du MVP (Must) vs Should, pour ne pas surcharger les epics MVP.

### D7 — Dépendance PyGObject système vs pip

PyGObject s'installe via `dnf install python3-gobject` (ou `gtk4` + `libadwaita`), pas via pip. `pyproject.toml` ne peut pas lister cette dépendance proprement. **Action :** documenter les prérequis système dans un README ou ADR packaging (cf. C3).

### D8 — Aucun ADR UX / Design System

ADR-003 tranche GTK 4 + libadwaita mais ne définit pas les wireframes, parcours détaillés, design system, ni l'organisation interne des vues. ADR-002 propose une « vue montre unifiée » mais renvoie à l'UX Designer. **Action :** activer l'agent UX Designer pour produire l'ADR UX avant le dev de l'Epic 4. Non bloquant pour les Epics 1-3.

---

## Couverture des exigences — vérification

| Exigence | ADR(s) couvrant | Statut |
|----------|----------------|--------|
| EF-1 à EF-4 (Auth) | ADR-004, ADR-007 | ✅ |
| EF-5 à EF-10 (Workouts GC→Montre) | ADR-002, ADR-006 | ✅ |
| EF-11 à EF-15, EF-21 (Montre→GC) | ADR-002, ADR-007 | ✅ |
| EF-16 (UI native) | ADR-003 | ✅ |
| EF-17, EF-18 (Historique, logs) | ADR-005 | ✅ (mais voir C1) |
| EF-19 (429 backoff) | ADR-007 | ✅ |
| EF-20 (USB déconnexion) | ADR-006, ADR-007 | ✅ |
| ENF-1 (Perf < 30s) | — | ⚠️ Voir M2 |
| ENF-2 (Fiabilité) | ADR-005, ADR-007 | ✅ |
| ENF-3 (Portabilité Fedora) | ADR-003 | ✅ |
| ENF-4, ENF-5 (Sécurité credentials) | ADR-004 | ✅ |
| ENF-6 (Modules) | ADR-002 | ✅ |

**Toutes les exigences sont couvertes**, à l'exception de la tension ENF-1 vs ADR-007 (M2).

---

## Couverture des incertitudes — vérification

| Incertitude | Statut | ADR couvrant |
|-------------|--------|--------------|
| INC-1 (Auth sans navigateur) | ✅ Levée (spike S-2) | ADR-004, ADR-007 |
| INC-2 (Filtre FIT acceptés par GC) | ⚠️ Partiellement | ADR-002 (`fit/decoder.classify()`), mais classification exacte à valider empiriquement en dev |
| INC-3 (GTK vs web) | ✅ Tranchée | ADR-003 |

---

## Prochaine action recommandée

1. **Corriger M1, M2, M3** dans les ADRs concernés (révision architecte backend, ~2h).
2. **Trancher C1 à C6** : soit corriger les ADRs, soit documenter comme risques résiduels acceptés.
3. **Activer l'UX Designer** pour produire l'ADR UX (wireframes, parcours, design system) — non bloquant pour Epics 1-3 mais nécessaire avant Epic 4.
4. **Produire ADR-008** (stratégie de tests) et **ADR-009** (packaging) avant la fin du dev Epic 3.

Une fois M1-M3 corrigés, la gate de sortie de la phase de Conception peut être validée et le développement de l'Epic 1 (Auth) peut démarrer.

---

*Directeur de Projet — Rapport de supervision de la phase de Conception.*
