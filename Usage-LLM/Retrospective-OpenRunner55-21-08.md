
Voici quelques notes d'étapes sur la méthode de développement logiciel avec le projet OpenRunner 55. Cette note date du moment où on était dans la phase 4 de développement début de l'épic 3. 

## 2. Point sur Usage-LLM — ce qu'on éprouve sur OpenRunner55

Je m'appuie sur ce qu'on a réellement fait (3 epics, ~180 commits, 179 tests) et ton auto-critique (`Analyse critique-WORKFLOW.md`) que je viens de lire. Je la trouve lucide — je ne vais pas la paraphraser, je vais la confronter à la pratique.

### Ce qu'on fait bien — et qui tient la route

**1. Spec avant code.** C'est la pratique la plus rentable du projet. Les briefs de mission (`Epic-2-brief.md`, `Epic-2-brief-frontend.md`) avec contrats figés ont évité le piège classique : le dev qui improvise et le frontend qui casse le backend. Le frontend s'est appuyé sur des signatures gelées, zéro friction.

**2. Gates par epic avec validation runtime.** Le bug SQLite l'illustre : sans la gate « test runtime sur montre réelle avant merge », on aurait mergé un frontend qui semblait marcher mais dont l'app ne savait pas qu'elle avait envoyé un workout. C'est le filet qui a attrapé le défaut. Cette pratique seule justifie la méthode.

**3. ADR vivants.** 9 ADR produits en conception, 1 révisée en dev (ADR-005 `check_same_thread`). Le système n'est pas de la documentation fossile — il évolue quand la réalité le commande. Le format (Contexte → Décision → Alternatives → Conséquences) force à expliciter le *pourquoi*.

**4. Un chantier actif à la fois.** Le `Phase-4-plan.md` sérialise les epics. On n'a jamais lancé deux chantiers en parallèle. Pour un solo-dev, c'est non négociable — et respecté.

**5. Docs + code versionnés ensemble.** Chaque commit de code s'accompagne de notes de dev, briefs, ADR. Le `context.md` source unique mis à jour à chaque jalon. C'est ce qui m'a permis de reprendre le contexte en début de session sans te poser 10 questions.

**6. Notes de dev vivantes.** Le `Epic-2-notes-frontend.md` (choix, écarts, points à trancher) est le meilleur livrable du dev frontend. C'est ce qui m'a permis de faire la revue sans lire tout le code en détail — le dev avait déjà documenté ses décisions et ses doutes.

Exemple : Nous commençons la mission Epic 3. Le fichiers est docs/dev/Epic-3-brief. Je veux que tu prennes connaissance de tous les éléments avant de commencer le développement du code. Avant le début du dev, il faut faire la création de la branche feat/epic-3-activities. Tu vas certainement émettre un plan de développement. Je veux que tu t'arrêtes par phase et attendre ma validation pour la suite. Tu devras aussi documenté ton propre fichier pour te noter tes décisions et observations dans docs/dev/Epic-3-notes-backend. C'est pas forcément nécessaire de documenter à chaque partie si tu penses que c'est mieux d'avoir le contexte général de tous l'Epic pour tes notes et rapport.

### Ce qu'on ne fait pas — et qui manque

**1. Pas de rétrospective par epic.** On n'a jamais fait de pause « qu'est-ce qu'on a appris ? » après un epic. L'auto-critique dit « absence totale de métrique d'efficacité » — c'est vrai. On ne sait pas si l'Epic 2 a pris plus ou moins de temps que prévu, ni pourquoi. Une rétro courte (10 min) après chaque gate d'epic corrigerait ça sans lourdeur.

**2. Le handoff entre sessions est ad hoc.** Les notes de dev servent de handoff, mais c'est implicite. Quand je reprends une session, je dois relire le `context.md` + le `Phase-4-plan.md` + les notes de dev pour reconstruire l'état. Ça marche, mais c'est du coût d'entrée à chaque session. Un checkpoint structuré (3-5 lignes : état, bloquant, prochaine action) réduirait ce coût.

**3. Pas de calibrage des estimations.** Le MVP est estimé à ~7 j/h. On n'a pas mesuré le temps réel par epic. Sans ça, la prochaine estimation sera aussi approximative.

### Ce qui est overkill pour ce projet

**1. Le Grilling 50-60 tours.** Pas appliqué (la Découverte a été directe). Ton auto-critique a raison : c'est du gaspillage pour un problem statement qu'un humain écrit en 30 min. À abandonner.

**2. Les personas d'agents.** En pratique, on en utilise 3-4 : DP (moi), Dev Backend, Dev Frontend, et Analyst/PM pour le cadrage initial. Les 7 personas prescrits (Scrum Master, QA, DevOps, Maintainer) sont du cosplay — le système prompt et les outils font le vrai travail. À tailler à 3-4 rôles.

**3. Les scripts `quality-check.sh` / `guard.sh`.** Pas implémentés. `pytest` suffit pour le MVP. La gate est « tests verts + revue DP + validation runtime », pas un script qui tourne dans un CI. À abandonner jusqu'à ce qu'il y ait une vraie douleur.

**4. La méta-boucle différée.** Ton auto-critique dit « déjà sur-spécifiée ». Pas appliquée, à juste titre. Ne la réactive que si tu sens le besoin après 3-4 epics de plus.

**5. La structure `docs/` à 6 sous-dossiers.** En pratique, c'est gérable parce que chaque `context.md` est court (< 20 lignes) et sert de point d'entrée. Le sur-investissement documentaire est réel mais contenu. À surveiller : si un dossier dépasse 5 fichiers, c'est qu'il grossit trop.

### Ma recommandation

Ta méthode fonctionne parce qu'on applique **4 pratiques à haut levier** : spec avant code, gates avec validation runtime, ADR vivants, un chantier à la fois. Le reste est du bruit. 

Ce que je te suggère pour la suite :
- **Ajouter** une rétro courte après chaque gate d'epic (10 min, 3 questions : ce qu'on a appris, ce qui a pris plus de temps que prévu, ce qu'on changerait)
- **Tenir** un simple tableau de suivi du temps par epic (pour calibrer les estimations)
- **Abandonner** le grilling, les scripts quality-check, la méta-boucle, les personas au-delà de 4