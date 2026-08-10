# Mission Spike S-2 — Authentification headless & pipeline bidirectionnel GC

**Agent cible :** Developer  
**Input obligatoire :** Lire avant de commencer
- `docs/decouverte/project-brief.md`
- `docs/cadrage/prd.md` (sections en lien avec l'auth et les activités)
- `docs/exploration/spike-S1-resultat.md`
- `docs/exploration/tree-FR55.md`

---

## Contexte

Le projet OpenRunner55 nécessite de communiquer avec Garmin Connect sans navigateur. Le spike S-1 a validé la chaîne `.FIT → FR55` mais l'authentification a nécessité un fallback navigateur. Ce spike S-2 doit lever les risques restants.

---

## Règle impérative

> **Tu exécutes un seul bloc à la fois. Tu montres le résultat. Tu attends ma confirmation avant de passer au suivant.**

Ne produis pas tout d'un coup. Chaque bloc se termine par :
- Le résultat (succès / échec / partiel)
- La preuve (sortie console, fichier, capture)
- La question : « Je passe au bloc suivant ? »

---

## Blocs

### Bloc 1 — Auth headless sans navigateur
Login via `garminconnect` en mode headless (pas de fallback Selenium/Playwright). Tester avec et sans MFA.

**Critère succès :** Session active sans ouverture de navigateur.

### Bloc 2 — Persistance de session
Après login réussi, sauvegarder le tokenstore. Simuler la reprise de session : nouveau script, pas de credentials, juste le fichier token.

**Critère succès :** L'API répond sans nouvelle authentification. Le refresh token fonctionne.

### Bloc 3 — Upload d'activité FR55 → GC
Prendre un `.fit` réel depuis le dossier `GARMIN/Activity/` de la FR55 (cf. tree-FR55.md). L'uploader dans Garmin Connect via `upload_activity()`.

**Critère succès :** L'activité apparaît dans GC. Noter le temps de propagation.

### Bloc 4 — Upload de données non-activité vers GC
Explorer les endpoints disponibles pour les données Monitor/Sleep/Metrics. Tester l'upload de données de santé (pas, FC repos, sommeil) vers GC si un endpoint existe.

**Critère succès :** Déterminer si le pipeline est bidirectionnel pour les données non-activité. Documenter ce qui est possible et ce qui ne l'est pas.

### Bloc 5 — Roundtrip complet (si blocs 1-4 OK)
Créer workout → upload → push → (activité simulée ou réelle) → sync → download FIT → vérifier l'intégrité.

**Critère succès :** Le FIT téléchargé contient la structure du workout original.

---

## Livrable final

À la fin des 5 blocs, tu rédigeras le fichier `docs/exploration/spike-S2-resultat.md` contenant :

1. **Tableau de synthèse** avec le statut de chaque bloc
2. **Pour chaque bloc :** protocole, résultat, preuve, observations
3. **Verdict GO/NOGO :** le projet peut-il avancer en l'état ?
4. **Limitations identifiées :** ce que l'API ne permet pas de faire
5. **Recommandations pour la Phase 3 (Conception)**

Tu écriras ce rapport dans `docs/exploration/spike-S2-resultat.md` uniquement quand tous les blocs auront été validés et que je t'aurai donné le feu vert pour rédiger le rapport.
