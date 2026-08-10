# UX Design — OpenRunner55

- **Date** : 2026-08-09
- **Auteur** : UX Designer (grilling utilisateur Franck/Leakorn)
- **Périmètre** : Parcours utilisateur, architecture d'information, wireframes, design system, critères d'acceptance
- **Références** : PRD, MVP, Epics, ADR-001 à 009, Spike S-2, tree-FR55

---

## 1. Rappel du contexte utilisateur

| Élément | Réalité observée |
|---------|-----------------|
| **Fréquence de sync** | 1 à 2 fois par semaine, variable |
| **Création de workouts** | Sur Garmin Connect Web, régulièrement. Quelques favoris conservés. |
| **Stockage montre** | ~25-30 activités max. Suppression par glissement. |
| **Session de sync** | Les deux sens : envoi workouts + remontée activités et données santé |
| **Nommage** | Le nom défini dans GC est le nom visible partout. Pas d'accents, pas d'espaces. |
| **Gestion des erreurs** | Détail par fichier, compteur de retry 429, logs consultables |
| **Authentification** | Premier lancement : login. Ensuite : tokenstore GNOME + auto-login. Déconnexion possible. |
| **Plateforme** | Fedora 44 / GNOME. GTK 4 + libadwaita. |

---

## 2. Parcours utilisateur

### Parcours A — Premier lancement (authentification)

```
[App ouverte, jamais utilisée]
    │
    ├── Écran de login centré
    │   ├── Champ email
    │   ├── Champ mot de passe (avec toggle visibilité)
    │   └── Bouton "Se connecter"
    │
    ├── ✅ Succès
    │   ├── Credentials stockés dans le trousseau GNOME
    │   ├── Tokenstore créé dans ~/.config/openrunner55/
    │   └── Redirection vers la section Activité
    │
    ├── ❌ Échec
    │   ├── Identifiants incorrects → message sous le formulaire
    │   ├── MFA activé → "Le MFA n'est pas supporté. Désactivez-le dans vos paramètres Garmin Connect."
    │   └── Réseau indisponible → "Impossible de contacter Garmin Connect. Vérifiez votre connexion."
    │
    └── Fermeture de l'app
        └── Les identifiants ne sont pas sauvegardés si l'auth a échoué
```

### Parcours B — Lancements suivants (reconnexion automatique)

```
[App ouverte, déjà authentifiée]
    │
    ├── Tentative resume_session() depuis tokenstore
    │   ├── ✅ Token valide → Section Activité directement (aucun écran de login)
    │   ├── ⚠️ Token expiré → Refresh token automatique → Section Activité
    │   └── ❌ Refresh échoué → Lecture credentials keyring → Nouveau login → Section Activité
    │
    └── ❌ Tout échoue → Écran de login avec message "Session expirée, veuillez vous reconnecter."
```

### Parcours C — Envoyer des workouts vers la montre

```
[Section Activité, connecté GC, montre branchée]
    │
    ├── Zone gauche "Garmin Connect" : liste complète des workouts GC
    │   ├── Tri du plus récent au plus ancien
    │   ├── Chaque ligne = ☐ + nom du workout
    │   └── Rafraîchie automatiquement au clic sur "↻ Synchroniser"
    │
    ├── 1. L'utilisateur coche 1+ workouts
    │      → Bouton "Envoyer (N)" s'active avec le compte
    │
    ├── 2. Clic sur "Envoyer (N) ▶"
    │      ├── Vérification : montre toujours branchée
    │      ├── Téléchargement .FIT via API GC (séquentiel, délai 3s entre requêtes)
    │      ├── Copie USB → GARMIN/Workouts/{slug(nom)}.FIT
    │      ├── Barre de progression : "Workout X/N — NomDuWorkout" + pourcentage
    │      └── Pas de bouton d'annulation
    │
    ├── ✅ Succès total
    │      ├── Message : "N workouts envoyés"
    │      └── La zone Montre est rafraîchie
    │
    ├── ⚠️ Échec partiel
    │      ├── Message : "X/N envoyés. Y échecs."
    │      ├── Détail par fichier : "✗ NomWorkout — Erreur 406"
    │      └── Les fichiers échoués restent cochés pour réessayer
    │
    ├── ❌ Montre débranchée pendant le transfert
    │      ├── Alerte : "Montre déconnectée — X/N transférés"
    │      ├── Les fichiers déjà copiés restent sur la montre
    │      └── Les fichiers non copiés restent cochés
    │
    └── ❌ Erreur réseau / 429
           ├── 429 → Backoff exponentiel avec compteur visible
           │   └── "Tentative 2/3 — attente 2s..."
           └── Épuisé → "Quota Garmin atteint. X/N envoyés. Réessayez dans quelques minutes."
```

### Parcours D — Remonter les données vers Garmin Connect

```
[Section Activité, connecté GC, montre branchée]
    │
    ├── Zone droite "Montre" : activités présentes sur la montre
    │   ├── ○ = non synchronisé (pas encore remonté vers GC)
    │   ├── ✓ = déjà synchronisé (grisé, non sélectionnable pour la sync)
    │   └── Affichage : type d'activité + date + durée (extraits du FIT)
    │
    ├── 1. Clic sur "↻ Synchroniser" (barre d'en-tête)
    │      ├── Lecture de Activity/, Monitor/, Sleep/, Metrics/
    │      ├── Filtrage : exclusion SUMMARY (406), exclusion doublons (table transferred_files)
    │      ├── Upload séquentiel des activités vers GC
    │      ├── Upload silencieux des données santé (Monitor, Sleep, Metrics) — non listées dans la zone Montre
    │      └── Rafraîchissement de la liste des workouts GC (nouvelles créations/suppressions)
    │
    ├── Progression
    │      ├── Barre globale : "Synchronisation en cours — X/Y fichiers"
    │      └── Mise à jour en temps réel : ○ → ✓ pour chaque activité uploadée
    │
    ├── ✅ Succès total
    │      ├── "Synchronisation terminée — N fichiers envoyés"
    │      └── Toutes les activités affichent ✓
    │
    ├── ⚠️ 429 Rate limiting
    │      ├── Compteur : "Tentative 2/3 — attente 4s..."
    │      └── Si épuisé : "Quota atteint. X/Y envoyés. Les fichiers restants sont conservés pour la prochaine synchronisation."
    │
    └── ❌ Erreur réseau
           └── "Erreur de connexion — X/Y envoyés" avec liste des fichiers en échec
```

### Parcours E — Consulter l'historique et les logs

```
[Section Logs & Historique]
    │
    ├── Tableau des synchronisations
    │   ├── Colonnes : Date, Direction, Fichiers, Statut
    │   ├── Tri : plus récent en haut (par défaut)
    │   └── Ligne cliquable → expand les détails
    │
    ├── Détail d'une sync (expand)
    │   ├── Liste par fichier :
    │   │   ✓ 10k-08_workout.fit — Envoyé
    │   │   ✓ VMA_workout.fit — Envoyé
    │   │   ✗ Fractionné_workout.fit — Erreur 406 : fichier non supporté
    │   └── Pour les 429 : nombre de tentatives et délais
    │
    └── Logs bruts (onglet ou section basse)
        ├── Filtrables par niveau (INFO, WARN, ERROR)
        └── Horodatés, sans credentials
```

### Parcours F — Gestion du compte

```
[Section Compte & Paramètres]
    │
    ├── Carte "Compte Garmin Connect"
    │   ├── Email : leakorn@exemple.com
    │   ├── Statut : ● Connecté
    │   └── "Se déconnecter" → dialogue de confirmation
    │       └── Confirmé → suppression keyring + tokenstore + redirection écran de login (auth_view)
    │
    ├── Carte "Stockage local"
    │   ├── Tokenstore : ~/.config/openrunner55/tokens.json
    │   ├── Base SQLite : ~/.config/openrunner55/openrunner.db
    │   └── Keyring : GNOME (trousseau de session)
    │
    └── Carte "Application"
        ├── Version : 0.1.0
        └── Dépendances : garminconnect X.Y.Z, etc.
```

> **Note** : pour changer d'identifiants (email ou mot de passe modifié côté Garmin Connect), l'utilisateur se déconnecte puis se reconnecte avec les nouveaux identifiants. La validité est vérifiée par Garmin Connect lors du login.

---

## 3. Architecture d'information

```
┌──────────────────────────────────────────────────────────────────┐
│  BARRE D'EN-TÊTE (Adw.HeaderBar)                                 │
│  [● Montre connectée] / [○ Déconnectée]    [↻ Synchroniser]      │
├─────────────┬────────────────────────────────────────────────────┤
│             │                                                    │
│  NAVIGATION │              ZONE DE CONTENU                       │
│  (Adw.      │                                                    │
│  Navigation │  ┌─────────────────────┐ ┌──────────────────────┐  │
│  SplitView) │  │                     │ │                      │  │
│             │  │   GARMIN CONNECT    │ │      MONTRE          │  │
│  ▸ Activité │  │                     │ │                      │  │
│             │  │  ☐ VMA              │ │  ○ Course à pied     │  │
│    Logs &   │  │  ☐ 10k-08           │ │    07/08/2026        │  │
│    Histori- │  │  ☐ Fractionné 6×1k  │ │    5.2 km · 28:34    │  │
│    que      │  │  ☐ Sortie longue    │ │  ✓ Course à pied     │  │
│             │  │  ...                │ │    04/08/2026        │  │
│    Compte   │  │                     │ │    8.1 km · 42:10    │  │
│    & Para-  │  │                     │ │  ○ Vélo              │  │
│    mètres   │  │                     │ │    02/08/2026        │  │
│             │  │                     │ │    22.3 km · 1:05    │  │
│             │  │                     │ │  ...                 │  │
│             │  │  [▶ Envoyer (2)]    │ │                      │  │
│             │  └─────────────────────┘ └──────────────────────┘  │
│             │                                                    │
└─────────────┴────────────────────────────────────────────────────┘
```

### Navigation : 3 sections

| Section                 | Vue backend    | Contenu                                        | État vide                              |
| ----------------------- | -------------- | ---------------------------------------------- | -------------------------------------- |
| **Activité**            | `watch_view`   | Deux zones côte à côte : GC (workouts) | Montre (activités) | Zones vides avec les titres de section, pas de texte d'aide |
| **Logs & Historique**   | `history_view` | Tableau des syncs passées + logs détaillés     | Tableau vide avec en-têtes de colonnes |
| **Compte & Paramètres** | `account_view` | Gestion credentials + infos stockage + version | Cartes avec valeurs par défaut         |

> **Note** : `account_view` (post-authentification, accessible depuis la navigation latérale) est distincte de `auth_view` (pré-authentification, écran de login centré sans navigation, décrite en §4.4).

### Barre d'en-tête (commune à toutes les sections)

| Élément | Position | Comportement |
|---------|----------|-------------|
| **Indicateur montre** | À gauche | Puce verte "● Montre connectée" ou puce grise "○ Montre déconnectée". Mise à jour en temps réel (pyudev + polling). |
| **Bouton Synchroniser** | À droite | Sensible uniquement si montre connectée ET authentifié GC. Déclenche la remontée des données (activités + santé). Rafraîchit aussi la liste des workouts GC. Icône : `view-refresh-symbolic`. |

---

## 4. Description des wireframes

### 4.1 Section "Activité"

**Agencement général :**
- Split horizontal 40/60 entre la zone GC et la zone Montre
- Chaque zone est une carte (Adw.Bin ou Gtk.Frame avec classe `.card`)
- Titre de section en haut de chaque zone, compteur entre parenthèses

**Zone Gauche — Garmin Connect :**

- **Titre** : "Garmin Connect" | Sous-titre : "Workouts (12)"
- **Liste** : Gtk.ListBox ou Gtk.ColumnView avec une colonne checkbox + une colonne nom
  - Chaque ligne = Gtk.CheckButton avec le nom du workout
  - Pas d'ID visible, pas de date (le tri récent→ancien suffit)
  - Survol : fond légèrement surligné
  - Sélection : checkbox cochée, fond accentué
- **Bouton** : "▶ Envoyer (N)" en bas de la carte
  - Inactif (grisé) si N=0
  - Actif (classe `suggested-action`) si N≥1, affiche le compte en temps réel
- **État de chargement** : spinner centré si la liste est en cours de récupération
- **Exercice prioritaire (amélioration future)** : un workout déjà présent sur la montre pourrait être grisé avec un indicateur "Déjà sur la montre"

**Zone Droite — Montre :**

- **Titre** : "Montre — FR55" | Sous-titre : optionnel, espace utilisé si disponible
- **Liste des activités** : Gtk.ListBox avec une ligne par activité
  - Chaque ligne affiche :
    - Icône de statut : ○ (non sync) ou ✓ (sync, grisé)
    - Type d'activité + date (ex: "Course à pied — 07/08/2026")
    - Métadonnées extraites du FIT : distance, durée (ex: "5.2 km · 28:34")
  - Tri : du plus récent au plus ancien
  - Les activités ✓ synchronisées sont semi-grisées mais restent listées
- **État déconnecté** : si la montre n'est pas branchée, la zone affiche "Branchez votre montre FR55 en USB" en texte centré grisé. Aucun bouton n'est actif.

**Barre de progression (pendant un transfert) :**

- Apparaît en bas de la fenêtre (Gtk.Revealer ou overlay)
- Barre horizontale (Gtk.ProgressBar) + texte : "Workout 2/3 — 10k-08" ou "Synchronisation — 8/15"
- Pourcentage à droite
- Pas de bouton d'annulation

**Comportement du bouton Synchroniser (↻) :**

1. Vérifie que la montre est connectée
2. Lance la lecture des dossiers Activity/, Monitor/, Sleep/, Metrics/
3. Filtre les doublons (table `transferred_files`)
4. Upload séquentiel vers GC :
   - Activités : visibles dans la progression ("Activité 2/5")
   - Données santé : upload groupé sans détail dans la barre, juste "Données santé — OK"
5. Rafraîchit la liste des workouts GC (récupère les nouveaux, retire les supprimés)
6. Journalise tout dans `sync_history` et `operation_logs`

### 4.2 Section "Logs & Historique"

**Agencement :**
- Vue unique plein contenu (pas de split)
- Deux zones superposées : tableau d'historique (haut) + logs détaillés (bas), ou deux onglets

**Tableau d'historique :**
- Gtk.ColumnView avec colonnes :
  - **Date** : format `dd/mm/yyyy HH:MM`
  - **Direction** : ↓ (GC → Montre) ou ↑ (Montre → GC)
  - **Fichiers** : "8/10" (réussis/total)
  - **Statut** : icône + texte (✓ Succès, ⚠ Partiel, ✗ Échec)
- Tri : plus récent en haut
- Ligne cliquable → expand une zone de détail en dessous (Gtk.ListBox imbriquée ou Gtk.Expander)

**Détail d'une sync (expand) :**
- Liste fichier par fichier :
  - ✓ `VMA_workout.fit` — Envoyé
  - ✗ `Fractionné_workout.fit` — Erreur 406 : format non supporté par Garmin Connect
  - ⚠ `10k-08_workout.fit` — 429 après 3 tentatives (7s), quota atteint

**Logs bruts :**
- Gtk.TextView en lecture seule, scrollable
- Chaque ligne : `[2026-08-09 14:32:01] [ERROR] Upload échoué pour 2026-08-07-08-29-33.fit : 429 Too Many Requests`
- Filtre par niveau : boutons toggle INFO / WARN / ERROR
- Pas d'export (MVP), pas de recherche full-text (MVP)

### 4.3 Section "Compte & Paramètres" (`account_view`)

**Agencement :**
- Vue unique plein contenu, accessible depuis la navigation latérale (post-authentification)
- Distincte de `auth_view` (écran de login pré-auth, §4.4)
- Cartes verticales empilées (Adw.PreferencesGroup ou Gtk.ListBox stylisé)

**Carte "Compte Garmin Connect" :**
- Email affiché en lecture seule avec icône utilisateur
- Statut : ● Connecté (vert) ou ○ Déconnecté (gris)
- Bouton "Se déconnecter" (classe `destructive-action`) → dialogue de confirmation :
  - "Se déconnecter ? Les identifiants seront supprimés du trousseau et le tokenstore sera effacé."
  - Boutons : "Annuler" / "Se déconnecter"
  - Après confirmation : suppression keyring + suppression tokenstore + redirection écran de login (`auth_view`)
- **Note** : pour changer d'identifiants (email ou mot de passe modifié côté Garmin Connect), l'utilisateur se déconnecte puis se reconnecte avec les nouveaux identifiants. La validité est vérifiée par Garmin Connect lors du login.

**Carte "Stockage local" :**
- Ligne : Tokenstore → `~/.config/openrunner55/tokens.json`
- Ligne : Base de données → `~/.config/openrunner55/openrunner.db`
- Ligne : Trousseau → GNOME Keyring (session)
- Icônes dossier pour chacun, purement informatif

**Carte "Application" :**
- Version : 0.1.0
- Licence : MIT
- Lien GitHub (non cliquable dans le MVP, ou ouvre le navigateur si facile)

### 4.4 Écran de login (`auth_view`)

**Agencement :**
- Fenêtre centrée, pas de barre de navigation latérale
- Cette vue est affichée **avant** authentification (pré-auth). Une fois connecté, elle est remplacée par l'interface principale avec navigation (`account_view`, `watch_view`, `history_view`).
- Logo / nom "OpenRunner55" en haut
- Sous-titre : "Connectez-vous à Garmin Connect"

**Formulaire :**
- Champ email (Gtk.Entry avec placeholder `adresse@email.com`)
- Champ mot de passe (Gtk.Entry avec mode `password`, icône toggle visibilité)
- Bouton "Se connecter" (classe `suggested-action`, pleine largeur)
- Spinner à droite du bouton pendant l'authentification

**Messages d'erreur :**
- Bannière en dessous du formulaire (Gtk.Label avec classe `error`) :
  - "Identifiants incorrects. Vérifiez votre email et mot de passe."
  - "L'authentification multi-facteurs (MFA) n'est pas supportée. Désactivez-la dans vos paramètres Garmin Connect."
  - "Impossible de contacter Garmin Connect. Vérifiez votre connexion Internet."

---

## 5. Design system

### 5.1 Palette

Le thème natif libadwaita est utilisé. Aucune couleur personnalisée n'est définie — l'utilisateur bénéficie du thème clair/sombre GNOME et des couleurs d'accentuation système.

| Rôle | Token libadwaita |
|------|-----------------|
| Fond fenêtre | `@window_bg_color` |
| Fond carte | `@card_bg_color` |
| Texte principal | `@window_fg_color` |
| Texte secondaire (dates, tailles) | `@window_fg_color` (70% opacité) |
| Accent (boutons, sélection, liens) | `@accent_bg_color` |
| Succès (✓, connecté) | `@success_color` |
| Erreur (✗, échec, destructive) | `@error_color` |
| Attention (⚠, partiel) | `@warning_color` |

### 5.2 Typographie

Utilisation exclusive des classes de style libadwaita. Aucune police personnalisée.

| Usage | Classe |
|-------|--------|
| Titre de fenêtre | `title-1` |
| Titre de section/carte | `title-2` |
| Labels principaux (noms de workout, types d'activité) | `body` |
| Labels secondaires (dates, durées, compteurs) | `caption` |
| Monospace (logs, chemins de fichiers) | `monospace` |

### 5.3 Espacement

| Contexte | Valeur |
|----------|--------|
| Marge de fenêtre | 18px |
| Espacement entre cartes | 12px |
| Padding interne carte | 12px |
| Espacement entre lignes de liste | 6px |
| Espacement checkbox ↔ label | 8px |
| Marge boutons (bas de carte) | 12px (top seulement) |

### 5.4 Composants

| Composant | Implémentation GTK | Notes |
|-----------|-------------------|-------|
| **Liste avec checkbox** | Gtk.ListBox + Gtk.CheckButton | Une ligne = une Gtk.ListBoxRow contenant un Gtk.CheckButton avec le label |
| **Bouton d'action principal** | Gtk.Button + classe `suggested-action` | Ex: "Envoyer", "Se connecter", "Synchroniser" |
| **Bouton destructif** | Gtk.Button + classe `destructive-action` | Ex: "Se déconnecter" |
| **Indicateur connexion** | Gtk.Box horizontal dans HeaderBar | Puce colorée (Gtk.DrawingArea 8×8px arrondi) + Gtk.Label |
| **Barre de progression** | Gtk.ProgressBar | Avec Gtk.Label superposé pour le texte "X/N" |
| **Dialogue de confirmation** | Adw.MessageDialog | Pour déconnexion, confirmation destructive |
| **Carte** | Adw.Bin stylisé | Fond `@card_bg_color`, coins arrondis 12px |
| **Icônes** | Icônes symboliques GNOME (`-symbolic`) | `view-refresh-symbolic`, `user-symbolic`, `folder-symbolic`, `list-symbolic` |
| **Spinner** | Gtk.Spinner | Pendant chargement des listes et authentification |
| **Navigation latérale** | Gtk.ListBox dans une Adw.NavigationSplitView | 3 entrées, largeur fixe ~200px |

### 5.5 États des éléments de liste

| État | Apparence |
|------|-----------|
| **Normal** | Fond transparent, texte normal |
| **Survol (hover)** | Fond légèrement surligné (`@card_bg_color` + overlay 5%) |
| **Sélectionné** | Checkbox cochée, fond accentué (`@accent_bg_color` à 10%), texte normal |
| **Synchronisé (✓)** | Texte semi-grisé (40% opacité), icône ✓ en `@success_color` |
| **En cours (spinner)** | Spinner à la place de la checkbox/icône |
| **Erreur (✗)** | Icône ✗ en `@error_color`, texte normal |
| **Désactivé** | Grisé uniforme (30% opacité), non cliquable |

---

## 6. Critères UX d'acceptance

### Epic 1 — Authentification

| ID | Story | Critères UX |
|----|-------|------------|
| US-1.1 | Login email + mot de passe | L'écran de login est centré, sans distraction. Le spinner remplace le bouton pendant l'auth. L'erreur est sous le formulaire, pas en popup. Le bouton est inactif tant que les deux champs ne sont pas remplis. |
| US-1.2 | Stockage et reprise automatique | Au 2ᵉ lancement, l'utilisateur ne voit **jamais** l'écran de login si le tokenstore est valide. Il arrive directement sur la section Activité en ≤ 2 secondes. |
| US-1.3 | Mise à jour / suppression credentials | Depuis Compte & Paramètres (`account_view`), se déconnecter se fait en ≤ 2 clics (section → bouton → confirmer). Pour changer d'identifiants (email ou mot de passe modifié côté Garmin Connect), l'utilisateur se déconnecte puis se reconnecte avec les nouveaux identifiants. |
| US-1.4 | Notification session expirée | Si le token expire et que le refresh échoue, une bannière "Session expirée" s'affiche dans la barre d'en-tête (pas de popup intrusive), puis l'écran de login remplace le contenu si tout échoue. |

### Epic 2 — Cloud → Montre

| ID | Story | Critères UX |
|----|-------|------------|
| US-2.1 | Liste des workouts GC | Chargée en ≤ 3s après auth. Tri récent→ancien. Chaque ligne = nom du workout (pas d'ID). Le compteur "(N)" dans le titre est mis à jour en temps réel. |
| US-2.3 | Détection montre USB | Après branchement USB, la puce passe au vert en ≤ 2s. Le bouton "Envoyer" et "Synchroniser" sont inactifs tant que la montre n'est pas détectée. La zone Montre affiche "Branchez votre montre" si déconnectée. |
| US-2.4 | Envoi des workouts | Après clic, une barre de progression est visible dans la même fenêtre (pas de popup). Le feedback est double : progression par workout + confirmation finale. La zone Montre est rafraîchie automatiquement après succès. |

### Epic 3 — Montre → Cloud

| ID | Story | Critères UX |
|----|-------|------------|
| US-3.1 | Affichage des fichiers montre | Chaque activité affiche : type (Course à pied, Vélo…), date, distance, durée. Les données santé ne sont pas listées — elles sont remontées silencieusement. Les activités déjà synchronisées sont visuellement distinctes (✓, grisé). Tri : plus récent en haut. |
| US-3.2 | Filtrage fichiers supportés | Les fichiers non supportés (SUMMARY) sont exclus silencieusement de la remontée. L'utilisateur n'a pas à s'en préoccuper. Les logs en gardent trace. |
| US-3.3 | Remontée vers GC | Après clic sur "Synchroniser", les ○ passent à ✓ en temps réel. La barre de progression montre le compte global. En cas d'erreur 429, un compteur de tentatives est visible. En fin de sync, un résumé "X fichiers envoyés, Y échecs" s'affiche. |

### Epic 4 — UI

| ID | Story | Critères UX |
|----|-------|------------|
| US-4.1 | Interface GTK | Les 3 sections sont navigables en 1 clic depuis la navigation latérale. La navigation est persistante (la section active est visuellement marquée). L'état des sélections dans Activité est conservé quand on change de section et qu'on revient. |
| US-4.2 | Historique des syncs | Chaque ligne affiche : date, direction (↓/↑), ratio fichiers, statut. Un clic expand les détails. Tri par défaut : plus récent en haut. |
| US-4.3 | Logs d'opération | Accessibles depuis Logs & Historique. Filtrables par niveau (INFO/WARN/ERROR). Horodatés. Aucun email/mot de passe visible. Texte monospace. |

### Epic 5 — Robustesse

| ID | Story | Critères UX |
|----|-------|------------|
| US-5.1 | Gestion 429 | Le compteur de retry est visible ("Tentative 2/3 — attente 4s"). Le temps d'attente décompte en temps réel. Après épuisement, message clair avec le ratio fichiers réussis/échoués. |
| US-5.2 | Déconnexion USB pendant transfert | Une alerte immédiate dans la barre de progression : "Montre déconnectée — X/N transférés". Les fichiers déjà copiés sont conservés. L'état des fichiers restants est préservé. |
| US-5.3 | Pas de perte de données | Les fichiers réussis et échoués sont listés distinctement dans le résumé de fin de sync. Les fichiers échoués restent dans leur état pré-sync et peuvent être relancés au prochain "Synchroniser" ou "Envoyer". |

---

## 7. Comportements implicites (non discutés, déduits)

| Comportement | Justification |
|-------------|---------------|
| **La liste GC est rafraîchie à chaque "Synchroniser"** | Franck veut que les nouveaux workouts apparaissent et les supprimés disparaissent. "Synchroniser" est le seul déclencheur naturel pour ça. |
| **Pas de refresh automatique périodique** | Usage ponctuel 1-2×/semaine. Pas de processus background. L'app est réactive, pas proactive. |
| **La sélection multiple est par checkbox, pas par Ctrl+clic** | Cohérent avec GTK. Plus accessible. Plus simple à implémenter. |
| **Les données santé (Monitor, Sleep, Metrics) sont uploadées sans être listées** | Franck l'a dit explicitement : "ça n'a aucun intérêt de les voir". Seules les activités méritent une liste. |
| **Suppression d'un workout de GC : pas d'action automatique sur la montre** | Si Franck supprime un workout sur GC, sa copie sur la montre reste. L'inverse (suppression montre → suppression GC) n'a pas de sens. |
| **Pas de mode hors-ligne** | L'authentification GC nécessite Internet. Si pas de réseau, l'app est en lecture seule (état montre) avec un message. |
| **La fenêtre est redimensionnable** | Minimum ~900×600 pour le split GC/Montre. En dessous, le layout pourrait basculer en mode empilé (futur). |
| **Suppression d'activités depuis l'app : hors périmètre MVP** | L'utilisateur supprime ses activités directement sur la montre (menu FR55). La suppression depuis l'application (avec dialogue, mise à jour `transferred_files`, etc.) n'est dans aucune exigence EF ni user story du MVP. Backlog pour une version ultérieure. |

---

## 8. Points laissés au développement

- **Extraction des métadonnées FIT** : le type d'activité, la distance et la durée sont extraits via `garmin-fit-sdk`. Si le décodage d'un fichier échoue, afficher "Fichier inconnu" avec la date et la taille. Ne pas bloquer l'affichage de toute la liste pour un fichier corrompu.
- **Détection des activités déjà présentes sur GC** : la table `transferred_files` fait foi. Si un fichier y est marqué comme uploadé, il est affiché avec ✓. La comparaison timestamps avec `get_activities()` GC est un fallback, pas la source primaire.
- **Comportement si l'utilisateur supprime une activité sur GC après l'avoir uploadée** : la table `transferred_files` garde trace de l'upload. L'activité sur la montre reste affichée avec ✓. Si Franck supprime manuellement l'activité sur GC, l'app ne le saura pas — c'est acceptable (pas de sync bidirectionnelle des suppressions).
- **Déduplication des workouts envoyés** : si un workout est déjà dans `GARMIN/Workouts/`, on pourrait l'indiquer dans la liste GC. Pour le MVP, on fait confiance à l'utilisateur (il voit ce qui est sur la montre dans la zone de droite).
- **Nommage des fichiers workout sur la montre** : les noms de workout GC sont slugifiés avant écriture sur la montre (minuscules, accents supprimés, espaces → `_`, caractères spéciaux supprimés, longueur max 40). Gestion des collisions (`_2`, `_3`…) si un fichier du même nom existe déjà. **Important** : le nom affiché par la montre pour un workout vient du champ `wkt_name` intégré dans le fichier .FIT, pas du nom de fichier sur le disque. Le slugify ne concerne que la lisibilité du dossier `Workouts/` quand l'utilisateur explore la montre branchée en USB sur son PC.

---

## 9. Notes pour le développeur (backend ↔ UI)

- **Le bouton "Synchroniser" appelle `sync/activities.py` ET `sync/wellness.py`** : la barre de progression doit refléter le total des deux. Les activités sont uploadées en premier (avec feedback), les données santé en second (avec un feedback groupé).
- **Le bouton "Envoyer" appelle `sync/workouts.py`** : chaque workout téléchargé et copié est un pas de progression. Le délai inter-requêtes de 3s est de la responsabilité de `garmin/client.py` — l'UI ne fait qu'afficher la progression.
- **La puce de connexion montre** : mise à jour via le signal `on_status_changed` de `WatchDetector`. L'UI ne poll pas, elle réagit.
- **Les logs UI ne doivent jamais afficher de token ou de mot de passe** : le module `store/logger.py` (ADR-005) filtre les credentials en amont avant insertion en base. L'UI accède aux logs et à l'historique **uniquement** via `sync/history.py` (Service) — jamais directement via `store/`. Le service `sync/history.py` expose `get_sync_history()` (historique) et `get_operation_logs(limit=100, level=None)` (logs filtrables par niveau INFO/WARN/ERROR) — c'est la seule interface que l'UI appelle pour la consultation. Le filtrage anti-credentials est transparent pour l'UI.

---

*UX Designer — Conception finalisée. Prête pour la gate de sortie de la Phase 3.*
