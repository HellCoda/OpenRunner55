# WORKFLOW — Guide opérationnel

> Colonne vertébrale au quotidien. Les **diagrammes** montrent la topologie
> (quoi s'enchaîne avec quoi) ; **ce guide** dit quoi faire, dans quel ordre,
> avec quel critère de passage. Structuré par cycle, du démarrage à la fin,
> avec la boucle journalière imbriquée. Chaque case porte un mot-clé de
> *pourquoi* en marge (`→ mot`). On coche, on ne relit pas.
>
> Se lit avec : `SDLC.png` (cycle long), `Day-cycle-LLM.png` (boucle courte),
> `Architecture-outils.png` (structure repo + outils).

---

## CYCLE LONG — les 7 phases (réf. SDLC.png)

> Une phase = un ou plusieurs jalons. On n'entre pas dans une phase sans que
> la gate de sortie de la précédente soit au vert. Tout retour arrière met à
> jour l'artefact concerné **avant** de reprendre.

### Phase 1 — Découverte / Analyse besoin
Agent : Analyst.

- [x] Cadrer le problème avant toute solution `→ alignement`
- [x] Grilling : laisser l'agent bombarder de questions (50-60 tours OK) `→ §2.1`
- [x] Produire le Project Brief (problem statement) `→ artefact`
- [x] **Gate** : go/no-go — le problème vaut-il d'être résolu, et par moi ? `→ sortie`

### Phase 2 — Planification
Agent : PM.

- [x] Entrée : Project Brief validé `→ prérequis`
- [x] Rédiger le PRD, découper en epics, prioriser (MoSCoW) `→ périmètre`
- [x] Définir le MVP `→ focus`
- [x] **Gate** : PRD complet, epics couvrant le besoin, MVP identifié `→ sortie`

### Phase 3 — Conception
Agent : Architect + UX.

- [x] Entrée : PRD + epics `→ prérequis`
- [x] Choix stack/patterns, schéma d'archi, modèle de données, contrats d'API `→ structure`
- [x] Écrire les ADR — **rationale + alternatives écartées + constraints** obligatoires `→ §19`
- [x] **Gate** : archi cohérente avec le PRD, aucune zone d'ombre majeure `→ sortie`

### Phase 4 — Développement
Agent : Scrum Master (découpe) → Dev (exécution).

- [ ] Entrée : PRD + Architecture *shardés* `→ prérequis`
- [ ] SM découpe les epics en stories contextualisées `→ atomicité`
- [ ] Dev : implémentation story par story → **boucle journalière ci-dessous** `→ exécution`
- [ ] **Gate par story** : critères d'acceptation remplis + tests passants `→ sortie`

### Phase 5 — Test / Validation / Optimisation
Agent : QA (Test Architect).

- [ ] Profil de risque, plan de test, tests d'intégration/e2e `→ robustesse`
- [ ] Revue de qualité, optimisation perf, audit sécurité `→ qualité`
- [ ] **Gate** : quality gate au vert (ou risques acceptés consciemment) `→ sortie`

### Phase 6 — Déploiement
Agent : Release / DevOps.

- [ ] Config CI/CD, préparation environnement, migration données `→ repro`
- [ ] Déploiement (blue-green/canary si pertinent), smoke tests post-déploiement `→ fiabilité`
- [ ] **Gate** : appli en prod, fonctionnelle, rollback prêt `→ sortie`

### Phase 7 — Maintenance / Évolution
Agent : Maintainer.

- [ ] Correction bugs, veille dépendances/sécurité, monitoring `→ santé`
- [ ] Collecte feedback, priorisation des évolutions `→ boucle`
- [ ] **Gate** : les évolutions retenues réinjectent dans Découverte `→ itération`

---

## BOUCLE JOURNALIÈRE — exécution d'une tâche (réf. Day-cycle-LLM.png)

> C'est le cœur du travail quotidien, à l'intérieur de la Phase 4 (mais aussi
> utilisable en 5/7). Une session = un objectif. On entre dans le smart zone,
> on en sort avant le dumb zone.

### Ouverture de session
- [ ] `git` : commit du **baseline** propre avant de lancer l'agent `→ rollback`
- [ ] Charger le Context Hub (`AGENTS.md`) en premier, rien d'autre `→ §17`
- [ ] Nommer l'objectif unique de la session (un seul) `→ smart zone`

### Cadrage de la tâche
- [ ] **Référence existe ?** Spec ou ADR couvrant la tâche `→ ancrage`
  - [ ] NON → définir le livrable, écrire Spec/ADR, commit `docs/` avant de coder `→ pas de code sans cible`
  - [ ] OUI → charger Contexte + Rules + Conventions pertinents `→ langage partagé`
- [ ] **Blast radius** : nommer le niveau `→ §12`
  - [ ] 🟢 Local (1-2 fichiers) → process léger : lint + tests unitaires
  - [ ] 🟡 Feature (module, endpoint, règle métier) → spec légère + TDD + quality gates complètes
  - [ ] 🔴 Architecture (multi-modules, DB, sécurité) → cycle doc complet + **validation humaine obligatoire**
- [ ] **Tier de modèle** selon la phase/tâche `→ §13`

### Exécution
- [ ] Lancer l'agent contre un livrable défini (jamais « débrouille-toi ») `→ direction`
- [ ] TDD où c'est un seam : test rouge d'abord, puis vert `→ §11`
- [ ] **Test** : baser le résultat attendu sur un fichier/épreuve déjà défini `→ falsifiable`

### Issue ? (le point de bascule)
- [ ] ✅ Vert → `quality-check.sh` doit passer à 100 % `→ gate déterministe`
  - [ ] Validation check fichier → **commit** `→ jalon`
- [ ] 🔴 Rouge → diagnostiquer la nature de l'échec :
  - [ ] **Erreur locale** → boucle de correction courte, on reste dans la session `→ auto-réparation`
  - [ ] **Échec structurel** → STOP. Rapport pour nouvelle conversation, mise à jour `docs/` `→ contexte pollué`
- [ ] **Garde-fou** : 3 tentatives infructueuses → `guard.sh` escalade `→ §14`

### Fermeture de session
- [ ] Toute contrainte expliquée 2× → bug de doc, mettre à jour la spec (pas le chat) `→ §10.3`
- [ ] Note rapide pour la méta-boucle si apprentissage notable `→ §18`
- [ ] Sortir avant le dumb zone ; si tâche > 1 smart zone → handoff propre `→ smart zone`

---

## RÈGLES TRANSVERSES — toujours actives

> Ne s'attachent à aucune phase : elles tournent en permanence. (Le 4e diagramme
> les représentera greffées sur les deux cycles.)

- [ ] **Backward step** : tout retour en arrière met à jour l'artefact concerné avant de reprendre `→ cohérence`
- [ ] **Anti-over-engineering** : n'adopter la strate suivante que quand la précédente fait mal `→ doctrine`
- [ ] **Sécurité** : transverse à toutes les phases, jamais une étape isolée `→ §11`
- [ ] **Git discipline** : `main` toujours déployable ; dev sur `feat/story-x.y` ; merge seulement si gate au vert `→ filet`
- [ ] **Rollback** : `git revert` (poussé) / `git reset` (local) ; checkpoint avant chaque modif `→ §14`
- [ ] **Contrat d'autonomie** — points d'arrêt obligatoires : décision archi irréversible, ambiguïté métier, conflit de contrainte, 3 échecs reproductibles `→ §14.2`
- [ ] **Anti-péremption** : une spec périmée est pire que pas de spec `→ §10.1`

---
