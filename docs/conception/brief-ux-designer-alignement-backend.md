# Brief — Corrections d'alignement UX

- **Date** : 2026-08-09
- **Auteur** : Directeur de Projet
- **Agent cible** : UX Designer
- **Contexte :** Revue d'alignement de `docs/conception/ux-design.md` avec l'architecture backend (ADR-002 à ADR-009). L'UX est globalement solide, mais 5 corrections sont à appliquer pour verrouiller la gate de sortie de la phase de Conception. Les décisions ci-dessous ont été validées par Franck.

## Input obligatoire

À lire avant de commencer :
- `docs/conception/ux-design.md` (ton livrable, à corriger en place)
- `docs/decisions/adr-002.md` (architecture modulaire — notamment `sync/history.py`, `account_view`, flux workouts)
- `docs/decisions/adr-005.md` (table `transferred_files`)
- `docs/decisions/adr-007.md` (nommage workouts, rate limiting)

---

## Corrections à appliquer

### C-UX-1 — Référencer `sync/history.py` au lieu de `store/` (règle cardinale)

**Problème :** §9 "Notes pour le développeur" écrit : « le module `store/logger.py` (ADR-005) filtre déjà les credentials. L'UI affiche les logs bruts tels quels ». Cela sous-entend un appel UI → `store/` direct, qui viole la règle cardinale (UI → Services → Core).

**Décision :** L'UI appelle **uniquement** `sync/history.py` pour la consultation :
- `sync/history.py.get_sync_history(limit=50)` pour l'historique des syncs.
- `sync/history.py.get_operation_logs(limit=100, level=None)` pour les logs (le paramètre `level` permet le filtrage INFO/WARN/ERROR côté UI).

**Action :** Corriger §9. Remplacer toute référence à `store/logger.py` ou `store/history.py` comme point d'entrée UI par `sync/history.py`. Préciser que le filtrage anti-credentials est fait en amont dans `store/logger.py` (inchangé), mais que l'UI n'y accède jamais directement — elle passe par `sync/history.py`.

**Fichiers à modifier :** `docs/conception/ux-design.md` §9, et vérifier toute autre mention de `store/` comme appel UI (parcours F notamment).

### C-UX-2 — Retirer le Parcours E (suppression d'activités de la montre)

**Problème :** Le Parcours E décrit une suppression d'activités avec dialogue, mise à jour de `transferred_files`, etc. Cette fonctionnalité n'est dans aucune exigence EF, aucune user story, ni le MVP. Franck supprime directement ses activités depuis la montre. C'est du scope creep.

**Décision :** Retirer le Parcours E du document. Le noter explicitement comme **hors périmètre MVP** (backlog, éventuelle version ultérieure).

**Actions :**
- Supprimer le Parcours E (section 2).
- Supprimer le bouton "🗑 Supprimer (N)" du wireframe section 3 (architecture d'information, zone Montre) et de la section 4.1 (description wireframe zone droite).
- Supprimer la mention "Checkbox pour sélection multiple (suppression)" en section 4.1.
- Ajouter une note en section 7 ou 8 : « Suppression d'activités depuis l'app : hors périmètre MVP. L'utilisateur supprime directement sur la montre. »
- Vérifier qu'aucun critère d'acceptance ne référence la suppression (Epic 5 ne concerne que la robustesse des transferts, pas la suppression).

**Fichiers à modifier :** `docs/conception/ux-design.md` §2, §3, §4.1, §7 ou §8.

### C-UX-3 — Nommage des fichiers workout en slugifié

**Problème :** Parcours C écrit « Copie USB → `GARMIN/Workouts/{nom}.FIT` ». Or le nom brut d'un workout GC peut contenir accents, espaces, caractères spéciaux (ex: "Fractioné 6×1k"), incompatibles avec FAT32. L'architecture (ADR-002, après correction architecte) spécifie `{slug(workout_name)}.FIT`.

**Décision :** Le nom du fichier sur la montre est **slugifié** : minuscules, accents supprimés, espaces → `_`, caractères spéciaux supprimés, longueur max 40. Gestion des collisions (`_2`, `_3`...) si un fichier du même nom existe déjà.

**Précision importante à ajouter :** le nom affiché par la montre pour un workout vient du champ `wkt_name` à l'intérieur du FIT, **pas du nom du fichier**. Le slugify ne concerne que la lisibilité du dossier `Workouts/` quand l'utilisateur branche la montre en USB sur son PC.

**Action :** Mettre à jour le Parcours C : « Copie USB → `GARMIN/Workouts/{slug(nom)}.FIT` ». Ajouter une note en §8 (points laissés au développement) ou §9 précisant la règle de slugify et le fait que l'affichage montre est indépendant du nom de fichier.

**Fichiers à modifier :** `docs/conception/ux-design.md` §2 (Parcours C), §8 ou §9.

### C-UX-4 — Séparer `auth_view` (écran login) et `account_view` (section Compte & Paramètres)

**Problème :** La section "Compte & Paramètres" (3 cartes) n'est pas mappée à une vue backend. L'architecture (ADR-002, après correction) introduit une vue dédiée `account_view`, distincte de `auth_view` (écran de login pré-auth).

**Décision :** Ce sont deux vues distinctes :
- `auth_view` = écran de login pré-authentification (fenêtre centrée, pas de navigation). Déjà décrit en §4.4.
- `account_view` = section post-authentification "Compte & Paramètres" dans l'app (navigation latérale). C'est la §4.3 actuelle.

**Action :** En §3 (architecture d'information) et §4.3, préciser explicitement que cette section correspond à la vue `account_view` (post-auth), distincte de `auth_view` (§4.4, pré-auth). Pas de changement de contenu, juste un alignement de nommage pour cohérence avec ADR-002.

**Fichiers à modifier :** `docs/conception/ux-design.md` §3, §4.3.

### C-UX-5 — Supprimer les boutons "Modifier l'email" / "Modifier le mot de passe"

**Problème :** §4.3 (carte "Compte Garmin Connect") et Parcours G proposent des boutons "Modifier l'email" et "Modifier le mot de passe" via dialogues. L'Authenticator n'expose pas d'API `update` (cf. ADR-002). Le parcours retenu est : déconnexion → reconnexion avec nouveaux identifiants.

**Décision :** Supprimer les boutons "Modifier l'email" et "Modifier le mot de passe". La carte "Compte Garmin Connect" ne conserve que :
- Email affiché en lecture seule.
- Statut : ● Connecté / ○ Déconnecté.
- Bouton "Se déconnecter" (classe `destructive-action`) → dialogue de confirmation → suppression keyring + tokenstore → redirection écran de login (`auth_view`).

**Note à ajouter :** pour changer d'identifiants (email ou mot de passe modifié côté Garmin Connect), l'utilisateur se déconnecte puis se reconnecte avec les nouveaux identifiants. La validité est vérifiée par Garmin Connect lors du login.

**Actions :**
- §4.3 : retirer les deux boutons "Modifier" et leurs dialogues associés.
- §2 (Parcours G) : retirer les lignes "Modifier l'email" et "Modifier le mot de passe". Le parcours G se réduit à : consultation + déconnexion.
- §6 (critères UX US-1.3) : mettre à jour le critère. US-1.3 devient : « Depuis Compte & Paramètres, se déconnecter se fait en ≤ 2 clics (section → bouton → confirmer). Pour changer d'identifiants, l'utilisateur se déconnecte puis se reconnecte. »

**Fichiers à modifier :** `docs/conception/ux-design.md` §2 (Parcours G), §4.3, §6 (US-1.3).

---

## Done criteria

- [ ] §9 : `store/` n'est plus référencé comme point d'entrée UI ; `sync/history.py` est le seul pont (avec paramètre `level`).
- [ ] Parcours E supprimé ; bouton "Supprimer" retiré des wireframes ; note backlog ajoutée.
- [ ] Parcours C : nommage `{slug(nom)}.FIT` + note sur `wkt_name` indépendant du nom de fichier.
- [ ] §3 et §4.3 : `account_view` nommée explicitement, distincte de `auth_view`.
- [ ] §4.3 et Parcours G : boutons "Modifier l'email/mdp" supprimés ; US-1.3 mise à jour.
- [ ] Aucune référence résiduelle à la suppression d'activités ou à la modification directe de credentials.

---

## Périmètre hors brief

- Ne pas modifier les ADR (rôle de l'Architecte Backend, brief séparé).
- Ne pas toucher au design system (§5), déjà aligné.
- Ne pas ajouter de nouveau parcours ou fonctionnalité.

---

*Directeur de Projet — Brief de correction UX, phase de Conception.*
