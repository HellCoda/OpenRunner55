# Plan de finalisation — 2026-09-22

> Dernier cycle avant publication. Le MVP+ est fonctionnel, validé en réel,
> UI validée par Franck. Pas d'audit approfondi (décision DP : non pertinent).

## État de départ

- 5/5 epics livrés et mergés sur `main`
- 298 tests verts (`pytest tests/ -m unit`)
- Validation réelle FR55 OK (Epics 2, 3, 5)
- `main` en avance de 1 commit sur `origin` (checkpoint 2026-09-21 non pushé)

## Décisions de tranchage (validées par Franck le 2026-09-22)

| Item | Décision | Raison |
|------|----------|--------|
| Vue Compte & Paramètres (US-1.3) | **À faire** | Dernière feature visible, spec UX §4.3 prête |
| Retry 5xx | **Reporté post-publication** | ADR-007 couvre 429, 5xx rare sur GC |
| Granularité historique (N entrées 1/1) | **Reporté** | Cosmétique, pas bloquant |
| Uniformisation timestamps UTC/local | **Reporté** | Technique invisible, pas de bug utilisateur |
| Cosmétique Paned / bandeau montre | **Reporté** | UI validée par Franck |
| Dette 409 (`garminconnect` dans `sync/`) | **Reporté** | Fonctionne, isolé, pas de fuite |
| Sync auto descendante (workouts GC → montre) | **Reporté** | Hors scope MVP+ |
| Audit approfondi du projet | **Écarté** | Fonctionnalités et UI validées en réel |
| Licence | **MIT** (validé 22/09) | Usage perso open-source, compatible, simple. Corrige `pyproject.toml` (GPL-3.0 → MIT) en séquence C |
| Modification email/mdp dans la vue | **Écarté** (validé 22/09) | Géré côté Garmin Connect. La vue se contente de déconnexion → re-login |

## Périmètre de la vue Compte & Paramètres (US-1.3)

Source : `docs/conception/ux-design.md` §4.3, ADR-002 (`ui/account_view.py`).

**Carte « Compte Garmin Connect »**
- Email affiché en lecture seule (icône utilisateur)
- Statut : ● Connecté (vert) / ○ Déconnecté (gris)
- Bouton « Se déconnecter » (`destructive-action`) → dialogue de confirmation
  - Texte : « Se déconnecter ? Les identifiants seront supprimés du trousseau et le tokenstore sera effacé. »
  - Boutons : Annuler / Se déconnecter
  - Après confirmation : `auth.delete_credentials()` + suppression tokenstore → redirection `auth_view`
- Pas de bouton « Modifier email/mdp » : pour changer d'identifiants, se déconnecter puis se reconnecter.

**Carte « Stockage local »** (informatif)
- Tokenstore → `~/.config/openrunner55/tokens.json`
- Base de données → `~/.config/openrunner55/openrunner.db`
- Trousseau → GNOME Keyring (session)

**Carte « Application »** (informatif)
- Version : 0.1.0
- Licence : MIT
- Lien GitHub (ouvre le navigateur si facile, sinon non cliquable)

**État actuel** : `app.py` contient un placeholder `_build_section_placeholder("Compte & Paramètres")`. Créer `src/openrunner55/ui/account_view.py` et le wire dans `app.py` à la place du placeholder.

## Séquences d'exécution

### Séquence A — Ménage repo (pas de code métier)
- [x] Commiter ou gitignorer `tests/test-21-09.txt` et `tests/test-epic3.txt` → déplacés vers `docs/tests-reels/`
- [x] Supprimer les branches locales mergées : `feat/epic-4-history`, `feat/epic-5-sync-auto`
- [x] Push du commit en attente sur `origin/main`
- [x] Mettre à jour `docs/context.md` : Epic 5 mergé (`ea248bc`), état réel, prochaine action

### Séquence B — Vue Compte & Paramètres (US-1.3)
- [x] Créer `src/openrunner55/ui/account_view.py` (3 cartes selon spec §4.3)
- [x] Wire dans `app.py` (remplacer le placeholder)
- [x] `Authenticator.get_email()` + 2 tests unitaires (300 verts)
- [x] Merge sur `main` (PR #2, squash `878a9b2`)
- [ ] Validation réelle : déconnexion → retour écran de login → re-login OK

### Séquence C — Packaging & publication
- [ ] AppImage (ADR-009) — agent DevOps/sys-admin
- [ ] README final (installation, usage, limitations connues)
- [ ] Licence MIT (corriger `pyproject.toml` : GPL-3.0 → MIT)
- [ ] Premier release (tag `v0.1.0`)

## Items reportés (post-publication, à reprendre si besoin)

- Retry 5xx (ADR-007 à étendre)
- Granularité historique (agrégation des entrées « 1/1 »)
- Uniformisation globale timestamps (UTC vs localtime)
- Cosmétique : curseurs `Gtk.Paned`, placement bandeau montre
- Dette technique : exception domaine 409 (`garminconnect` importé dans `sync/activities.py`)
- Sync auto descendante (workouts GC → montre au branchement)
- Export logs

---

*Directeur de Projet — Plan de finalisation. Document de suivi, à cocher au fur et à mesure.*
