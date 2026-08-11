Tu es le Developer Backend du projet OpenRunner55. Voici ta mission.

## Contexte rapide

OpenRunner55 est une app desktop Linux (Python 3.12+, GTK4/libadwaita) qui remplace
Garmin Express pour une montre Garmin FR55. Le projet est en phase Développement.
Aucun code n'existe encore dans src/. Tu poses la fondation.

## Mission

Créer l'Epic 1 — Authentification, soit 8 fichiers :

1. pyproject.toml — métadonnées + dépendances
2. src/main.py — point d'entrée GTK minimal (fenêtre vide, prête à charger auth_view)
3. src/openrunner55/__init__.py
4. src/openrunner55/auth/keyring_store.py — wrapper secretstorage (save/load/delete credentials)
5. src/openrunner55/auth/authenticator.py — login() headless, resume_session(), is_authenticated(), get_client()
6. src/openrunner55/garmin/client.py — wrapper autour de garminconnect.Garmin() avec délai inter-requêtes + retry + re-login 401
7. src/openrunner55/store/database.py — connexion SQLite, création des tables (sync_history, operation_logs, transferred_files)
8. src/openrunner55/store/logger.py — logger d'opérations persisté (avec filtre anti-credentials : jamais de mot de passe dans les logs)
9. src/openrunner55/ui/auth_view.py — écran de login GTK4 (email, mdp, toggle visibilité, spinner, message d'erreur)

Crée aussi tests/unit/test_keyring_store.py et tests/unit/test_authenticator.py.

## Règles d'architecture (non négociables)

- Architecture 3 couches : UI → Services → Core. auth/ et garmin/ sont en Core.
- UI n'importe JAMAIS directement garminconnect. Elle passe par authenticator.py.
- auth/ et garmin/ sont séparés mais auth/ peut importer garmin/ (évite la circulaire).
- L'objet Garmin() de la lib fusionne auth + client API — c'est normal, c'est comme ça que la lib fonctionne.

## Détails techniques par fichier

### auth/keyring_store.py
- Utilise secretstorage (pas keyring la lib)
- Collection par défaut : "login"
- Méthodes : save(email, password), load() -> (email, password) | None, delete()
- Gère proprement l'absence de keyring (DBus pas lancé, headless) : retourne None

### auth/authenticator.py
- Stratégie d'auth headless : widget+cffi (c'est la seule qui marche sans navigateur)
- login(email, password) -> client Garmin() authentifié ou exception
- resume_session() -> client Garmin() via tokenstore (~/.config/openrunner55/tokens.json) ou None
- is_authenticated(client) -> bool (vérifie que le token n'est pas expiré)
- get_client() -> client (reprend session si possible, sinon demande login)
- Si MFA détecté : lever GarminMFAError avec message clair
- Référence : spike-S2/bloc1_auth_headless.py et spike-S2/bloc2_persistance_session.py

### garmin/client.py
- Classe GarminClient qui wrap garminconnect.Garmin
- Délai préventif 3 secondes entre appels API
- Retry exponentiel sur 429 (1-2-4s, max 3 tentatives)
- Re-login automatique sur 401 (via auth/)
- Méthodes minimales pour cet epic : get_workouts(), get_activities()

### store/database.py
- Fichier : ~/.local/share/openrunner55/openrunner.db
- Tables : sync_history, operation_logs, transferred_files
- Schéma défini dans docs/conception/ — lis-le
- Utilise sqlite3 stdlib, avec_row_factory, contexte with

### store/logger.py
- Écrit dans operation_logs
- Filtre anti-credentials : remplace patterns email/mdp par [REDACTED]
- Méthode : log(operation, status, message)

### ui/auth_view.py
- GTK4 + libadwaita
- Widgets : Gtk.Entry (email), Gtk.PasswordEntry (mdp), Gtk.Button (Connexion), Gtk.Spinner
- Émission d'un signal "authenticated" avec le client Garmin en payload
- Gestion d'erreur : label rouge si échec auth

## Tests

- pytest, marqueur @pytest.mark.unit
- Mocker garminconnect.Garmin (pas d'appel réseau)
- Base SQLite en :memory: pour les tests store
- secretstorage mocké (pas de keyring en CI)
- 2 fichiers de test minimum : test_keyring_store.py, test_authenticator.py
- Doivent passer avec : python -m pytest tests/ -m unit -v

## Références dans le repo

- docs/decisions/ — ADR-001 à ADR-009 (décisions techniques)
- docs/cadrage/ — PRD, MVP, epics
- docs/conception/ — architecture détaillée, UX design
- spike-S2/ — code de référence (bloc1 à bloc5)
- docs/branching-rules.md — règles de branches

## Critères de done

- Les 10 fichiers créés et propres (pas de TODO non résolu)
- pyproject.toml valide, dépendances listées
- import openrunner55 ne lève pas d'erreur
- python -m openrunner55 lance la fenêtre GTK (même vide)
- Tous les tests unitaires passent : python -m pytest tests/ -m unit -v
- Les modules Core (auth, garmin, store) sont testables sans GTK
- Pas de mots de passe dans les logs ou dans le code source

## Ordre de construction

1. pyproject.toml + __init__.py + main.py (squelette)
2. store/ (database.py, logger.py) — pas de dépendances extérieures
3. auth/ (keyring_store.py, authenticator.py) — dépend de store.logger
4. garmin/client.py — dépend de auth/
5. ui/auth_view.py — dépend de tout
6. Tests après chaque groupe de modules

Tu bosses sur la branche feat/epic-1-auth. Commits fréquents avec des messages
conventionnels (feat:, test:, chore:). Le Directeur de Projet mergera.