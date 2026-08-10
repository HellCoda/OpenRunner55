# Brief — Corrections d'alignement architecture backend

- **Date** : 2026-08-09
- **Auteur** : Directeur de Projet
- **Agent cible** : Architecte Backend
- **Contexte** : Revue d'alignement UX ↔ backend post-livraison de `docs/conception/ux-design.md`. L'architecture (ADR-002 à ADR-009) a déjà été corrigée des points M1/M3/C1/C5/C6 du rapport du 08/08. Quatre ajustements résiduels restent à appliquer pour verrouiller la gate de sortie de la phase de Conception.

## Input obligatoire

À lire avant de commencer :
- `docs/decisions/adr-002.md` (architecture modulaire)
- `docs/decisions/adr-005.md` (SQLite, `transferred_files`)
- `docs/decisions/adr-007.md` (rate limiting, flux workouts)
- `docs/conception/ux-design.md` (livrable UX à aligner)
- `docs/exploration/spike-S2-resultat.md` (référence nommage workouts)

---

## Corrections à appliquer

### C-ARCH-1 — Nommage des fichiers workout en slugifié

**Problème :** ADR-002 (flux de données) et ADR-007 spécifient `watch.write_fit(GARMIN/Workouts/{id}.FIT)`. Le spike S-2 a effectivement utilisé `{workoutId}.FIT` (ex: `1656951822.FIT`). Or la décision produit est de nommer les fichiers avec le **nom du workout slugifié** pour la lisibilité du dossier `Workouts/` en USB, conformément à l'expérience Garmin Express.

**Décision :** Le nom du fichier sur la montre est `{slug(workout_name)}.FIT`.

**Précisions techniques à documenter dans ADR-002 :**
- Le slugify est de la responsabilité de `sync/workouts.py` (Service), pas de `watch/filesystem.py` (Core). `watch/filesystem.py` reçoit le path final et écrit.
- Règles de slugify : minuscules, suppression des accents (NFKD), espaces → `_`, suppression des caractères non alphanumériques (sauf `_`), longueur max 40 caractères.
- **Gestion des collisions :** si un fichier `{slug}.FIT` existe déjà dans `GARMIN/Workouts/`, suffixer `_2`, `_3`, etc. La vérification d'existence se fait via `watch/filesystem.py`.
- **Note importante à ajouter :** le nom affiché par la montre pour un workout vient du champ `wkt_name` à l'intérieur du FIT, pas du nom du fichier. Le slugify ne concerne que la lisibilité du système de fichiers USB (FAT32).

**Fichiers à modifier :** ADR-002 (flux de données + interface `sync/workouts.py`), ADR-007 (mention du nommage si pertinent).

### C-ARCH-2 — Ajout de la vue `account_view` à l'architecture UI

**Problème :** ADR-002 liste les vues `ui/` : `app`, `auth_view`, `watch_view`, `history_view`, `widgets`. L'UX a introduit une 3e section de navigation "Compte & Paramètres" (3 cartes : Compte GC, Stockage local, Application) qui n'est pas mappée à une vue.

**Décision :** Ajouter `account_view.py` à la liste des vues `ui/`.

**Responsabilité de `account_view` :**
- Affichage lecture seule : email du compte GC, statut de connexion, chemins de stockage (tokenstore, SQLite, keyring), version de l'app.
- Action unique : "Se déconnecter" → délègue à `auth/authenticator.py` (`delete_credentials` + suppression tokenstore) puis redirige vers `auth_view`.
- Aucune logique de modification de credentials (cf. C-ARCH-3).

**Séparation `auth_view` / `account_view` :**
- `auth_view` = écran de login pré-authentification (fenêtre centrée, pas de navigation).
- `account_view` = section post-authentification dans l'app (navigation latérale).

**Fichiers à modifier :** ADR-002 (tableau modules + structure `src/` + interface publique si besoin).

### C-ARCH-3 — Confirmation : pas d'API de mise à jour des credentials

**Problème :** L'UX (parcours G, section 4.3) proposait des boutons "Modifier l'email" / "Modifier le mot de passe". L'Authenticator (ADR-002) n'expose que `save_credentials` / `delete_credentials`, pas d'`update`.

**Décision :** Pas d'API `update`. Le parcours "modifier ses identifiants" = déconnexion (`delete_credentials` + suppression tokenstore) → reconnexion (`login` avec nouveaux identifiants). La validité des nouveaux identifiants est vérifiée côté Garmin Connect lors du `login`.

**Action :** Confirmer dans ADR-002 (note explicite) que l'Authenticator n'expose pas d'`update` et que le parcours de changement d'identifiants passe par delete + login. Aucune modification d'interface publique.

**Fichiers à modifier :** ADR-002 (note dans la section `auth/`).

### C-ARCH-4 — Renforcer le pont `sync/history.py` et exposer le filtrage par niveau

**Problème :** ADR-002 (corrigé) a créé `sync/history.py` comme pont UI → `store/` pour respecter la règle cardinale. L'UX §9 référence encore `store/logger.py` directement (corrigé côté UX par ailleurs). L'interface publique de `sync/history.py` doit être complète pour couvrir le besoin UX de filtrage des logs par niveau (INFO/WARN/ERROR).

**Décision :** Confirmer et compléter l'interface de `sync/history.py` :
- `get_sync_history(limit=50) -> list[SyncRecord]` (déjà présent)
- `get_operation_logs(limit=100, level=None) -> list[LogRecord]` — ajouter le paramètre `level` optionnel (`"DEBUG"|"INFO"|"WARN"|"ERROR"|None`). Si `None`, tous niveaux confondus.

**Action :** Mettre à jour l'interface publique dans ADR-002. Préciser explicitement que l'UI n'appelle jamais `store/` directement — `sync/history.py` est le seul point d'entrée pour la consultation des logs et de l'historique.

**Fichiers à modifier :** ADR-002 (interface publique `sync/history.py` + note de renforcement de la règle cardinale).

---

## Done criteria

- [ ] ADR-002 : flux workouts mis à jour avec `{slug(workout_name)}.FIT` + règles slugify + gestion collisions + note sur `wkt_name`.
- [ ] ADR-002 : `account_view` ajouté au tableau modules, à la structure `src/`, avec sa responsabilité.
- [ ] ADR-002 : note explicite sur l'absence d'API `update` credentials (parcours delete + login).
- [ ] ADR-002 : interface `sync/history.py` complétée avec paramètre `level` + renforcement règle cardinale (UI → `sync/history.py` uniquement, jamais `store/` direct).
- [ ] ADR-007 : aligner toute mention du nommage workout si nécessaire.
- [ ] Aucune incohérence résiduelle entre ADR-002/007 et `ux-design.md` sur les 4 points ci-dessus.

---

## Périmètre hors brief

- Ne pas modifier les parcours UX (rôle de l'UX Designer, brief séparé).
- Ne pas toucher aux ADR-003/004/005/006/008/009 (déjà alignés).
- Ne pas produire de code (phase de Conception, pas de Dev).

---

*Directeur de Projet — Brief de correction architecture, phase de Conception.*
