# Backlog post-Epic 4

> Issues des tests réels du 21/09/2026 (`tests/test-21-09.txt`).
> Points hors périmètre Epic 4, à traiter dans des epics/chantiers ultérieurs.
> Le DP les ventile par priorité et par nature.

## Contexte

Le 21/09 matin, Franck a testé l'app en conditions réelles (course à pied,
branchement montre, création d'activité sur Garmin Connect). L'Epic 4
(Logs & Historique) est validé en UX. Les observations ci-dessous concernent
le comportement global de l'app, pas l'Epic 4.

---

## P1 — Sync automatique au branchement de la montre

**Observation** : Franck branche sa montre, ouvre l'app, s'attend à ce qu'une
sync se déclenche. Rien ne se passe — la liste des fichiers est identique à
la veille. Il doit déclencher la sync manuellement.

**Attente utilisateur** : « Je rentre de sport, je branche ma montre, j'ouvre
l'app → mes métriques et activités remontent à Garmin Connect. »

**Nature** : Feature / UX (Epic 3 ou chantier dédié).
**Périmètre** : `watch/detector.py` (détection USB) + controllers
`WorkoutsController` / `ActivitiesController` (déclenchement auto).

**À spécifier avant dev** :
- Déclencheur : connexion USB seule ? Ou connexion USB + app déjà ouverte ?
- Sens : sync montante (activités → GC) seule, ou aussi descendante
  (workouts GC → montre) ?
- Feedback UI : indicateur de sync en cours, progression, fin.
- Conflit avec sync manuelle en cours.

---

## P1 — Détection des nouveaux fichiers / activités récentes

**Observation** : activités postérieures au 13/09 non visibles dans l'app,
alors que Garmin Connect a bien reçu les métriques (pas, etc.) après sync.
L'app semble afficher une liste figée.

**Attente** : les nouvelles activités présentes sur la montre doivent être
détectées et proposées à la sync.

**Nature** : Bug ou comportement attendu ? À diagnostiquer.
**Périmètre** : `watch/filesystem.py` (énumération fichiers) +
`ActivitiesController` (rafraîchissement liste).

**À diagnostiquer avant dev** :
- La liste des fichiers de la montre est-elle réellement lue à chaque sync,
  ou mise en cache ?
- Le filtre « déjà transférés » (`TransferredFilesStore`) exclut-il trop
  largement ?
- Repro : brancher montre avec nouvelle activité → lancer sync → vérifier
  ce qui est proposé.

---

## P2 — Grisement / masquage des fichiers déjà transférés

**Observation** : à chaque sync, l'app propose plus de 200 fichiers déjà
transférés. Franck veut qu'ils soient grisés ou masqués — pas d'intérêt de
les revoir à chaque fois.

**Attente** : les fichiers déjà transférés (présents dans
`transferred_files`) ne devraient pas être proposés, ou affichés en grisé
non sélectionnables par défaut.

**Nature** : UX / US à spécifier.
**Périmètre** : `WorkoutsController` / `ActivitiesController` (filtrage de
la liste) + vue (`WatchView`).

**À spécifier avant dev** :
- Masquer purement et simplement, ou afficher en grisé ?
- Bouton « afficher tout » pour les revoir ?
- Comportement identique pour workouts (descendant) et activités
  (montant) ?

---

## P2 — Rafraîchissement de la liste des workouts après création sur GC

**Observation** : Franck crée une activité (workout) sur Garmin Connect
depuis le web. L'app ouverte, il n'a aucun moyen de la voir apparaître sans
fermer/rouvrir l'app.

**Attente** : un refresh de la liste des workouts GC devrait être possible
depuis l'app (bouton ou action auto).

**Nature** : Feature / UX (Epic 2 ou chantier dédié).
**Périmètre** : `WorkoutsController` + `WatchView` (bouton refresh).

**À spécifier avant dev** :
- Bouton « ↻ Rafraîchir » dans la section Activité ?
- Refresh auto au focus de la fenêtre ? Au branchement montre ?

---

## P3 — Dette technique : uniformisation des timestamps

**Observation** : le schéma SQLite utilise `DEFAULT (datetime('now'))` qui
stocke en UTC. L'Epic 4 corrige l'affichage à la volée (conversion UTC →
local dans `HistoryController.format_timestamp`), mais les autres tables
(`transferred_files`) ont le même problème si un jour elles affichent des
timestamps.

**Décision** : correction localisée Epic 4 (affichage), pas de toucher au
schéma figé.

**Dette** : uniformiser globalement le stockage des timestamps :
- Soit stocker en UTC explicite partout + convertir à la lecture côté
  service/store.
- Soit stocker en `localtime` partout (plus simple, mais casse la
  portabilité inter-fuseau).

À traiter dans un chantier « cohérence timestamps » global, pas urgent tant
que l'affichage est corrigé à la source de consommation.

---

## Priorisation proposée

| # | Item | Priorité | Effort estimé | Dépendance |
|---|------|----------|---------------|------------|
| 1 | Sync auto au branchement montre | P1 | Moyen | Spéc UX |
| 2 | Détection nouveaux fichiers | P1 | Diagnostic puis dev | Item 1 ? |
| 3 | Grisement fichiers déjà transférés | P2 | Faible | Spéc UX |
| 4 | Refresh liste workouts | P2 | Faible | — |
| 5 | Uniformisation timestamps | P3 | Faible | — |

**Recommandation DP** : traiter 1 et 2 ensemble dans un epic « Sync auto &
détection » — c'est le cœur du cas d'usage quotidien. 3 et 4 en suivi. 5 en
maintenance.

---

*Document vivant — à mettre à jour à chaque traitement d'item.*
