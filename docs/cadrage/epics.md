# Epics — OpenRunner55

Découpage du PRD en 5 epics. Chaque epic couvre un ensemble cohérent d'exigences (référencées par ID).

---

## Epic 1 — Authentification Garmin Connect

**Objectif** — L'utilisateur peut s'authentifier auprès de Garmin Connect depuis l'application, sans navigateur ouvert.

**Périmètre**
- Dans : authentification email + mot de passe, stockage local sécurisé, gestion session/expiration.
- Hors : UI principale, sync de données.

**Exigences couvertes** : EF-1, EF-2, EF-3, EF-4, ENF-4, ENF-5

**User stories**

| ID | Story | Critères d'acceptance |
|----|-------|----------------------|
| US-1.1 | En tant qu'utilisateur, je veux saisir mes identifiants Garmin Connect dans l'application afin de m'authentifier sans navigateur. | 1. L'app accepte email + mot de passe. 2. L'authentification réussit sans session navigateur préalable (validation spike S-2). 3. Un message clair est affiché en cas d'échec. |
| US-1.2 | En tant qu'utilisateur, je veux que mes identifiants soient stockés localement et sécurisés afin de ne pas les ressaisir à chaque lancement. | 1. Les identifiants sont persistés localement (chiffrés ou via keyring GNOME). 2. Au redémarrage, l'authentification est automatique. 3. Les identifiants n'apparaissent jamais en clair dans les logs. |
| US-1.3 | En tant qu'utilisateur, je veux pouvoir mettre à jour ou supprimer mes identifiants stockés afin de garder le contrôle sur mes données. | 1. Un menu permet de modifier email/mot de passe. 2. Un bouton permet de supprimer les identifiants stockés. 3. Après suppression, l'app demande à nouveau les identifiants au prochain lancement. |
| US-1.4 | En tant qu'utilisateur, je veux être notifié si ma session expire ou si l'authentification échoue afin de pouvoir réagir. | 1. En cas d'expiration de session, l'app affiche un message explicite. 2. L'app propose de re-saisir les identifiants. 3. Aucune opération de sync n'est lancée tant que l'auth n'est pas valide. |

---

## Epic 2 — Workouts : Garmin Connect → Montre

**Objectif** — L'utilisateur sélectionne des workouts sur Garmin Connect et les pousse sur sa montre FR55 branchée en USB.

**Périmètre**
- Dans : récupération de la liste des workouts, sélection, téléchargement .FIT, copie sur la montre, détection USB.
- Hors : remontée des activités (Epic 3), interface historique (Epic 4).

**Exigences couvertes** : EF-5, EF-6, EF-7, EF-8, EF-9, EF-10, ENF-1, ENF-2

**User stories**

| ID | Story | Critères d'acceptance |
|----|-------|----------------------|
| US-2.1 | En tant qu'utilisateur, je veux voir la liste de mes workouts Garmin Connect triés du plus récent au plus ancien afin de trouver rapidement celui que je veux envoyer. | 1. La liste est récupérée via l'API Garmin Connect. 2. Le tri est du plus récent au plus ancien. 3. Chaque workout affiche au minimum : nom, date, type. |
| US-2.2 | En tant qu'utilisateur, je veux sélectionner un ou plusieurs workouts afin de choisir ce que j'envoie sur ma montre. | 1. La sélection multiple est possible. 2. Le nombre de workouts sélectionnés est affiché. 3. Un workout déjà présent sur la montre est signalé (si détectable). |
| US-2.3 | En tant qu'utilisateur, je veux que l'application détecte ma montre branchée en USB avant le transfert afin d'éviter les erreurs. | 1. L'app détecte la présence du FR55 en USB mass storage. 2. Si la montre n'est pas détectée, le bouton d'envoi est désactivé avec un message d'information. 3. Le chemin du dossier workouts de la montre est identifié automatiquement. |
| US-2.4 | En tant qu'utilisateur, je veux cliquer sur « Envoyer vers la montre » et que les workouts soient copiés afin de les retrouver sur ma montre. | 1. Les workouts sélectionnés sont téléchargés au format .FIT. 2. Les fichiers sont copiés dans le dossier workouts de la montre. 3. Une confirmation est affichée avec le nombre de fichiers transférés. 4. En cas d'échec partiel, les fichiers non transférés sont listés. |

---

## Epic 3 — Activités & métriques : Montre → Garmin Connect

**Objectif** — L'utilisateur remonte les activités et métriques de sa montre vers Garmin Connect.

**Périmètre**
- Dans : lecture des fichiers .FIT sur la montre, filtrage, téléversement via API, affichage du résultat.
- Hors : envoi de workouts vers la montre (Epic 2), interprétation graphique des données.

**Exigences couvertes** : EF-11, EF-12, EF-13, EF-14, EF-15, EF-21, ENF-2

**User stories**

| ID | Story | Critères d'acceptance |
|----|-------|----------------------|
| US-3.1 | En tant qu'utilisateur, je veux voir les fichiers présents sur ma montre afin de savoir ce qui peut être remonté. | 1. Les fichiers .FIT sont lus depuis les dossiers de la montre (activités, métriques). 2. Chaque fichier affiche : type, date, taille. 3. Les fichiers natifs (activités, métriques) sont visuellement séparés des fichiers importés (workouts). |
| US-3.2 | En tant qu'utilisateur, je veux que l'application filtre les fichiers exploitables par Garmin Connect afin de ne pas envoyer de fichiers inutiles. | 1. Les fichiers spécifiques à la montre non pris en charge par Garmin Connect sont exclus. 2. La liste des fichiers exclus est consultable. 3. Le filtrage est documenté (règles identifiables). |
| US-3.3 | En tant qu'utilisateur, je veux cliquer sur « Synchroniser vers Garmin Connect » afin de remonter mes données. | 1. Les fichiers filtrés sont téléversés via l'API Garmin Connect. 2. Le résultat est affiché par fichier (succès/échec). 3. En cas d'échec partiel, les fichiers non téléversés restent identifiables pour une nouvelle tentative. |

---

## Epic 4 — Interface, historique & logs

**Objectif** — L'application offre une interface graphique claire, un historique des syncs et des logs consultables.

**Périmètre**
- Dans : UI native (GTK privilégié), onglets/vues pour chaque fonctionnalité, historique des syncs, logs.
- Hors : logique d'authentification, logique de sync (Epics 1-3).

**Exigences couvertes** : EF-16, EF-17, EF-18

**User stories**

| ID | Story | Critères d'acceptance |
|----|-------|----------------------|
| US-4.1 | En tant qu'utilisateur, je veux une interface graphique native afin d'utiliser l'application confortablement sur Fedora/GNOME. | 1. L'UI est en GTK (ou app web locale si fallback décidé en Phase 3). 2. Les trois fonctions principales sont accessibles : workouts Cloud→Montre, données Montre→Cloud, historique. 3. L'interface est responsive et fonctionnelle. |
| US-4.2 | En tant qu'utilisateur, je veux consulter l'historique des synchronisations afin de suivre ce qui a été transféré. | 1. Chaque sync est enregistrée avec : date, sens (→ ou ←), nombre de fichiers, statut global. 2. L'historique est trié du plus récent au plus ancien. 3. L'historique persiste entre les redémarrages. |
| US-4.3 | En tant qu'utilisateur, je veux consulter les logs d'opération afin de diagnostiquer un problème éventuel. | 1. Les logs sont accessibles depuis l'interface. 2. Les logs incluent : horodatage, opération, résultat. 3. Les identifiants ne apparaissent jamais dans les logs. |

---

## Epic 5 — Robustesse & gestion d'erreurs

**Objectif** — L'application gère les erreurs réseau, API et USB sans perte de données ni blocage.

**Périmètre**
- Dans : retry 429, gestion déconnexion USB, notifications d'erreur, intégrité des transferts.
- Hors : logique fonctionnelle de sync.

**Exigences couvertes** : EF-19, EF-20, ENF-2, ENF-6

**User stories**

| ID | Story | Critères d'acceptance |
|----|-------|----------------------|
| US-5.1 | En tant qu'utilisateur, je veux que l'application gère le rate limiting (429) automatiquement afin de ne pas avoir à relancer manuellement. | 1. En cas d'erreur 429, l'app réessaie avec un backoff exponentiel. 2. L'utilisateur est informé du délai d'attente. 3. Après épuisement des retries, l'opération est marquée en échec avec un message clair. |
| US-5.2 | En tant qu'utilisateur, je veux être notifié si ma montre est débranchée en cours de transfert afin de comprendre ce qui s'est passé. | 1. La déconnexion USB en cours de transfert est détectée. 2. L'opération est interrompue proprement. 3. Les fichiers déjà transférés sont conservés ; les fichiers en cours sont signalés comme incomplets. |
| US-5.3 | En tant qu'utilisateur, je veux qu'aucune donnée ne soit perdue en cas d'échec partiel d'une sync. | 1. Les fichiers réussis et échoués sont listés séparément. 2. Les fichiers échoués peuvent être relancés individuellement. 3. L'état de chaque fichier est persistant jusqu'à la prochaine sync. |

---

## Matrice de couverture PRD → Epics

| Exigence | Epic | Story(s) |
|----------|------|----------|
| EF-1 | 1 | US-1.1 |
| EF-2 | 1 | US-1.2 |
| EF-3 | 1 | US-1.3 |
| EF-4 | 1 | US-1.4 |
| EF-5 | 2 | US-2.1 |
| EF-6 | 2 | US-2.1 |
| EF-7 | 2 | US-2.2 |
| EF-8 | 2 | US-2.4 |
| EF-9 | 2 | US-2.4 |
| EF-10 | 2 | US-2.3 |
| EF-11 | 3 | US-3.1 |
| EF-12 | 3 | US-3.1 |
| EF-13 | 3 | US-3.2 |
| EF-14 | 3 | US-3.3 |
| EF-15 | 3 | US-3.3 |
| EF-16 | 4 | US-4.1 |
| EF-17 | 4 | US-4.2 |
| EF-18 | 4 | US-4.3 |
| EF-19 | 5 | US-5.1 |
| EF-20 | 5 | US-5.2 |
| EF-21 | 3 | US-3.1 |
| ENF-1 | 2 | US-2.4 |
| ENF-2 | 2, 3, 5 | US-2.4, US-3.3, US-5.3 |
| ENF-3 | 4 | US-4.1 |
| ENF-4 | 1 | US-1.2 |
| ENF-5 | 1 | US-1.2 |
| ENF-6 | 5 | US-5.3 |

**Toutes les exigences du PRD (EF-1 à EF-21, ENF-1 à ENF-6) sont couvertes.** Aucune exigence orpheline.
