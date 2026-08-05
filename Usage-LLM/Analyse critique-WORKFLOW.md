
---

### Ce qui tient la route

**Le concept de smart zone / dumb zone** est le meilleur atout de cette méthode. La discipline de sortir avant que l'agent (et l'humain) ne dégradent en boucle est sous-estimée partout. Le cadrage « un objectif unique par session » est la bonne unité atomique.

**La règle des deux explications** — « une contrainte expliquée 2× en 2 sessions = bug de doc → MAJ la spec, pas le chat » — est excellente. C'est le genre d'heuristique qui transforme un workflow réactif en amélioration continue sans lourdeur.

**Le blast radius** comme modulateur de cérémonie plutôt que binaire (process/uniforme) est une vraie bonne idée. Graduer la rigueur selon le risque plutôt que d'appliquer la même checklist à un fix de typo et à une migration de schéma.

**Docs + code versionnés ensemble.** Évident en rétrospective, rare en pratique.

**La doctrine anti-préemption** — « n'adopter la strate suivante que quand la précédente fait mal ». Ironiquement, c'est la règle que le document lui-même viole le plus.

---

### Ce qui cloche

#### 1. Le « Context Hub » comme point d'entrée unique est une bombe à tokens

Le workflow prescrit : « Charger le Context Hub (`AGENTS.md`) en premier, rien d'autre. » Or le matériau de référence lui-même [3] met en garde : « everything in it is always loaded. Instructions accumulate, most of them irrelevant to any given task, and a long AGENTS.md both costs tokens and dilutes itself — the more instructions in context, the less reliably the model follows any one of them. »

Le document Systemes-transverses mentionne bien une « alerte budget tokens », mais c'est une note en passant — aucun mécanisme concret n'est proposé à part… un script `check-context-hub.sh` qui, si je comprends bien, vérifie la *présence* du hub, pas son coût. Si ton AGENTS.md fait 8k tokens, tu brûles ça à chaque session, y compris pour un fix de lint. C'est le problème exact que le concept de *progressive disclosure* [3] cherche à résoudre, et ce workflow fait l'inverse : *premature disclosure* systématique.

#### 2. Le « Grilling » 50-60 tours est du gaspillage pur

« Laisser l'agent bombarder de questions (50-60 tours OK) » en phase Découverte. Cinquante à soixante tours pour produire un *problem statement* qu'un humain peut écrire en 30 minutes de réflexion structurée. La spec, comme le rappelle le matériau de référence [2], est « the durable statement of intent it reads at the start of every session » — pas la transcription d'un interrogatoire de 60 échanges. C'est de la productivité théâtrale : ça donne l'impression de creuser, mais le ratio signal/coût est désastreux.

#### 3. Les « personas » d'agents sont du cosplay

Analyst, PM, Architect, UX Expert, Scrum Master, QA, DevOps, Maintainer — c'est une distribution de rôles de théâtre. Le matériau de référence [6] est limpide : « the harness is where most of your configuration lives. » Ce qui distingue un agent « Architect » d'un agent « Dev », ce n'est pas le titre qu'on lui donne, c'est le système prompt, les outils disponibles, et les permissions. Les personas sont une couche d'abstraction qui ne fait que renommer ce qui est déjà un routage de modèle + prompt. Pire : ils créent l'illusion qu'un changement de rôle suffit à changer la compétence, alors que c'est le harness [6] qui détermine le comportement.

#### 4. Les quality gates sont auto-référentielles — pas de review externe

Le workflow fait exécuter `quality-check.sh` par le même agent qui a écrit le code, avec correction « jusqu'à 100 % ». Le matériau de référence [4] est sans ambiguïté : « Asking the agent that wrote the code to review its own work gets you very little — the session that produced the bug also contains the reasoning that produced it, and the agent reads its own conclusions back as confirmation. A reviewer with a fresh context window has none. »

Nulle part dans le workflow il n'est question d'*automated review* par un agent séparé [4], un modèle différent, ou même une passe déterministe hors-LLM. La gate est un miroir.

#### 5. Over-engineering documentationnel pour un workflow solo

Regarde la structure `docs/` : `research/`, `exploration/`, `decisions/`, `architecture/`, `specs/`, `dev/`, `rules/`, `conventions/` — huit sous-dossiers. Plus `context/bugs/`, `context/meta/`, `context.db`. Plus `agents/` avec un fichier par persona. Plus `skills/`. Pour un développeur seul.

C'est de l'architecture de documentation conçue comme si une équipe de 8 allait la consommer. Le matériau de référence [3] prévient : « instructions accumulate, most of them irrelevant to any given task. » La maintenance de cette structure documentaire devient elle-même une charge cognitive qui rivalise avec le code.

#### 6. Le TDD « test rouge d'abord » est un rituel vide avec un LLM

Le workflow insiste : « test rouge d'abord, puis vert. » Mais un LLM ne vit pas l'échec du test rouge comme un humain — il ne déduit pas, il génère le test et l'implémentation dans le même souffle. Le rouge n'est pas un feedback d'apprentissage pour lui, c'est une case cochée pour toi. Tu peux le faire (c'est défendable comme discipline personnelle), mais le présenter comme un mécanisme d'amélioration de la qualité du code agent est une confusion entre le processus humain et le processus machine.

#### 7. Le « handoff propre » entre sessions est un vœu pieux

« Si tâche > 1 smart zone → handoff propre. » Le matériau de référence [1] décrit précisément le problème : « an agent re-learns the codebase from scratch every time — anything it figured out yesterday is gone unless it was written into the environment. » Le handoff, ici, n'a aucun mécanisme de transfert de contexte au-delà de « laisse des bons docs. » C'est une résolution, pas un mécanisme. Sans *compaction* structurée ou *context checkpointing* (concepts qui n'apparaissent nulle part), le handoff est une réinitialisation déguisée.

#### 8. La méta-boucle est marquée [DIFFÉRÉ] mais déjà sur-spécifiée

Quatre opérations (Generate, Evaluate, Distribute, Observe), une matrice d'interactions avec les six autres systèmes, un pipeline de rétrospectives… et tout ça marqué « à activer plus tard. » C'est le pattern classique de l'architecture spéculative : concevoir le système d'introspection avant d'avoir assez d'usage du système primaire pour savoir ce qui mérite d'être introspecté. La doctrine dit « anti-préemption », mais la page est déjà écrite.

#### 9. Le 4e diagramme manquant

La table de correspondance finale liste froidement « Règles transverses | 4e diagramme (à construire) ». Dans un document qui se présente comme la « colonne vertébrale au quotidien », livrer un TODO dans la table des correspondances, c'est admettre que le système n'est pas complet — mais continuer à le vendre comme tel.

#### 10. Absence totale de métrique d'efficacité

Aucun des sept systèmes ne mesure si tout ceci améliore réellement les résultats. La méta-boucle promet de le faire, mais elle est [DIFFÉRÉ]. En attendant, on adopte un niveau de cérémonie élevé sans aucune ligne de base : le code produit est-il meilleur ? Les bugs sont-ils moins nombreux ? La vélocité est-elle supérieure ? On ne sait pas. On ne mesure pas. On fait confiance à la structure.

---

### Verdict

Ce travail manifeste une vraie intelligence des problèmes : la contamination de contexte inter-sessions, le besoin de gates déterministes, la gestion du risque par graduation, la documentation comme artefact vivant. Les bons instincts sont là.

Mais le résultat est un système **sur-conçu et sous-validé**. Trop de couches, trop de dossiers, trop de personas, trop de scripts pour un développeur seul. La moitié des systèmes sont différés alors que leur spécification est déjà écrite — ce qui viole la propre doctrine anti-préemption du document.

Ce qui sauverait cette méthode : la tailler à 3-4 pratiques à haut levier (smart zone, blast radius, règle des deux explications, spec avant code), virer les personas, mesurer l'efficacité réelle pendant un mois, et *ensuite* ajouter ce qui manque — si et seulement si la douleur est avérée.