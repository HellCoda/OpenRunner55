# Brief de mission — US-1.3 : Vue « Compte & Paramètres »

Tu es le Developer (frontend GTK4/libadwaita) du projet OpenRunner55.
Voici ta mission pour la vue « Compte & Paramètres » (US-1.3), dernière
feature avant publication.

## Contexte rapide

OpenRunner55 est une app desktop Linux (Python 3.12+, GTK4/libadwaita) qui
synchronise Garmin Connect et une montre FR55 via USB. **Epics 1 à 5 livrés
et mergés sur `main`** (298 tests verts), validation réelle OK.

La section « Compte & Paramètres » est actuellement un placeholder dans
`ui/app.py` (`_build_section_placeholder`). Ta mission : créer la vraie vue
conforme à `docs/conception/ux-design.md` §4.3.

## Décisions de cadrage (DP — figées)

| Sujet | Décision |
|-------|----------|
| Périmètre | 3 cartes informatives + déconnexion. **Pas** de « modifier email/mdp ». |
| Changement d'identifiants | Se déconnecter puis se reconnecter (validité vérifiée par GC au login). |
| Email affiché | Lecture depuis le keyring (source de vérité des identifiants), fallback `client.display_name`. |
| Déconnexion | `authenticator.delete_credentials()` (existe déjà), puis signal `logged_out`. |
| Pas de controller dédié | La vue est statique + une action simple. Elle reçoit les dépendances injectées, comme `auth_view`. |
| Licence affichée | **MIT** (décision DP validée par Franck le 22/09 — constante centralisée). |
| Lien GitHub | `https://github.com/fr4nk-crux/OpenRunner55` |

## Périmètre

### Chantier 1 — `Authenticator.get_email()` (micro backend)

`ui/account_view.py` a besoin de l'email du compte connecté. La source la
plus fiable est le keyring (`auth/keyring_store.py`), où l'email est stocké
au login (US-1.2).

Ajouter à `auth/authenticator.py` :

```python
def get_email(self) -> str | None:
    """Retourne l'email stocké dans le keyring, ou None si indisponible."""
    creds = self._keyring.load()
    return creds[0] if creds else None
```

`KeyringStore.load()` retourne `(email, password)` ou `None` — on ne garde
que l'email, jamais le mot de passe.

**Tests** (`tests/unit/test_authenticator.py`) :
- `get_email` retourne l'email quand le keyring en a un.
- `get_email` retourne `None` quand le keyring est vide/indisponible.

### Chantier 2 — `ui/account_view.py` (nouvelle vue)

Créer `src/openrunner55/ui/account_view.py`, une `Gtk.Box` (comme
`auth_view`), contenant 3 cartes empilées verticalement. Suivre la spec
`docs/conception/ux-design.md` §4.3.

**Carte « Compte Garmin Connect »**
- Email en lecture seule, icône utilisateur (`user-info-symbolic` ou label).
- Statut : « ● Connecté » (classe `success`) si `is_authenticated(client)`,
  sinon « ○ Déconnecté » (`dim-label`).
- Bouton « Se déconnecter » (`destructive-action`) → dialogue de
  confirmation :
  - Texte : « Se déconnecter ? Les identifiants seront supprimés du
    trousseau et le tokenstore sera effacé. »
  - Boutons : « Annuler » / « Se déconnecter ».
  - Après confirmation : `authenticator.delete_credentials()` puis
    `self.emit("logged_out")`.

**Carte « Stockage local »** (informatif, chemins réels)
- Tokenstore → `~/.config/openrunner55/tokens.json`
- Base de données → `~/.local/share/openrunner55/openrunner.db`
- Trousseau → GNOME Keyring (session)

> ⚠️ Écart spec vs code : la spec UX §4.3 écrit `~/.config/openrunner55/
> openrunner.db`, mais le code réel (ADR-005 révisé) place la base dans
> `~/.local/share/openrunner55/`. **Afficher le chemin réel**
> (`store/database.py` → `DEFAULT_DB_PATH`), pas celui de la spec.

**Carte « Application »**
- Version : `openrunner55.__version__` (0.1.0)
- Licence : `MIT` (constante en tête de module)
- Lien GitHub : `https://github.com/fr4nk-crux/OpenRunner55` (non cliquable
  MVP, ou `Gtk.LinkButton` si trivial — au choix, privilégier le simple).

**Signal** :

```python
__gsignals__ = {
    "logged_out": (GObject.SignalFlags.RUN_FIRST, None, ()),
}
```

**Constructeur** : `AccountView(authenticator, client, **kwargs)` — les deux
dépendances injectées, jamais importées depuis `auth/` ou `garmin/`
directement dans la vue au-delà du type.

### Chantier 3 — Wiring dans `ui/app.py`

1. Importer `AccountView`.
2. Remplacer le placeholder :
   ```python
   self._content_stack.add_named(
       self._build_section_placeholder("Compte & Paramètres"), "account"
   )
   ```
   par la construction d'`AccountView(self._authenticator, client)`,
   connectée à un handler `_on_logged_out`.
3. `_on_logged_out` :
   - stopper le détecteur USB (`self._detector.stop()` si non None),
   - réinitialiser `self._detector`, `self._history_controller` à None,
   - `self._show_login_view()`.

## Règles d'architecture (non négociables)

- **ADR-002** : UI → Services → Core. La vue n'importe jamais
  `garminconnect` directement. Les dépendances (`Authenticator`, `client`)
  sont injectées.
- Pas de logique GTK dans un controller (il n'y en a pas ici).
- Aucun appel réseau dans la vue : `delete_credentials()` est local
  (keyring + suppression fichier), pas besoin de thread.

## Tests

ADR-008. Marqueur `@pytest.mark.unit`. Mocks uniquement.

- `get_email` : 2 tests (email présent / absent).
- La vue GTK n'est **pas** testée unitairement (nécessite un display,
  ADR-008 — même règle que `auth_view`).

```bash
python -m pytest tests/ -m unit -v
```

Doit passer à 100 % (298 existants + nouveaux).

## Critères de done

- `get_email()` implémenté et testé.
- `ui/account_view.py` créé, 3 cartes conformes à la spec §4.3 (avec le
  chemin DB **réel**).
- Déconnexion : dialogue de confirmation → suppression credentials +
  tokenstore → retour écran de login.
- `ui/app.py` : placeholder remplacé, `logged_out` câblé, détecteur stoppé.
- `python -m pytest tests/ -m unit -v` passe à 100 %.
- `import openrunner55.ui.app` ne lève pas.
- Aucun TODO non résolu.

## Ordre de construction

| Étape | Contenu | Fichiers |
|-------|---------|----------|
| 1 | `get_email()` + tests | `auth/authenticator.py`, `tests/unit/test_authenticator.py` |
| 2 | Vue `account_view.py` | `ui/account_view.py` |
| 3 | Wiring app.py | `ui/app.py` |

## Branche

`feat/account-view` (déjà créée). Commits conventionnels (`feat:`, `test:`).

## Références dans le repo

- `docs/conception/ux-design.md` §4.3 — spec de la vue
- `docs/decisions/adr-002.md` — architecture 3 couches
- `docs/decisions/adr-008.md` — stratégie de tests
- `src/openrunner55/auth/authenticator.py` — `delete_credentials()`, `is_authenticated()`
- `src/openrunner55/auth/keyring_store.py` — `load()`
- `src/openrunner55/ui/auth_view.py` — pattern de vue (signaux, injection)
- `src/openrunner55/store/database.py` — `DEFAULT_DB_PATH` (chemin DB réel)
- `tests/unit/test_authenticator.py` — pattern de test
