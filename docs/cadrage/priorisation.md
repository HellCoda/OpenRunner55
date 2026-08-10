# Priorisation MoSCoW — OpenRunner55

> Phase 2 — Product Manager
> Références : [PRD](prd.md) · [Epics](epics.md)

---

## Tableau de priorisation

| ID | Story / Exigence | Must | Should | Could | Won't |
|----|-----------------|------|--------|-------|-------|
| US-1.1 | Authentifier l'utilisateur (email + mot de passe) | ✅ | | | |
| US-1.2 | Stocker les identifiants localement de façon sécurisée | ✅ | | | |
| US-1.3 | Mettre à jour ou supprimer les identifiants stockés | ✅ | | | |
| US-1.4 | Notifier si la session expire ou l'authentification échoue | ✅ | | | |
| US-2.1 | Lister les workouts disponibles sur Garmin Connect (tri récent → ancien) | ✅ | | | |
| US-2.2 | Détecter les workouts déjà présents sur la montre | | ✅ | | |
| US-2.3 | Sélectionner et envoyer un workout vers la montre | ✅ | | | |
| US-2.4 | Supprimer un workout de la montre | | ✅ | | |
| US-3.1 | Lister les fichiers .FIT présents sur la montre (activités + métriques) | ✅ | | | |
| US-3.2 | Remonter les activités et métriques vers Garmin Connect | ✅ | | | |
| US-3.3 | Filtrer les fichiers .FIT réellement acceptés par Garmin Connect | | ✅ | | |
| US-4.1 | Afficher les fichiers de la montre avec métadonnées (séparation visuelle natifs vs importés) | ✅ | | | |
| US-4.2 | Afficher l'historique des synchronisations | ✅ | | | |
| US-4.3 | Afficher les logs d'opération | | ✅ | | |
| US-5.1 | Gérer le rate limiting (429) avec retry et backoff | | ✅ | | |
| US-5.2 | Reconnexion automatique après expiration de session | | | ✅ | |
| US-5.3 | Notifications desktop de fin de synchronisation | | | ✅ | |
| — | Synchronisation automatique en arrière-plan (daemon/polling) | | | | ✅ |
| — | Interprétation graphique des données santé (graphes, tendances) | | | | ✅ |
| — | Mise à jour firmware OTA de la montre | | | | ✅ |
| — | Support multi-utilisateurs | | | | ✅ |

---

## Rationale

### Must (10 stories) — le produit n'existe pas sans

Ces stories constituent le MVP. Sans elles, l'application ne remplit aucun de ses objectifs fondamentaux.

- **Authentification (US-1.1 à 1.4)** : pas d'accès à Garmin Connect = pas d'application.
- **Workouts Cloud → Montre (US-2.1, US-2.3)** : c'est le cas d'usage principal validé par le spike.
- **Activités Montre → Cloud (US-3.1, US-3.2)** : c'est la seconde direction de la bidirectionnalité.
- **Interface (US-4.1, US-4.2)** : une app desktop sans UI n'est pas un produit quotidien.

### Should (5 stories) — expérience complète

Le produit fonctionne sans, mais l'expérience est dégradée. À intégrer dès que possible après le MVP.

- **US-2.2** (détection doublons) : évite d'écraser ou dupliquer des workouts. Si simple techniquement, peut monter en Must.
- **US-2.4** (suppression workouts) : évite la saturation de la montre.
- **US-3.3** (filtre .FIT) : évite les erreurs de remontée. Découverte empirique en tests.
- **US-4.3** (logs) : utile pour le debug, pas bloquant pour l'usage.
- **US-5.1** (retry 429) : le rate limiting est rare en sync manuelle, mais le retry améliore la robustesse.

### Could (2 stories) — nice to have

- **US-5.2** (reconnexion auto) : confort, pas critique.
- **US-5.3** (notifications desktop) : confort, pas critique.

### Won't (4 items) — exclu de cette version

- Sync automatique : explicitement exclu par l'utilisateur (risque de rate limiting, pas de besoin).
- Interprétation graphique : Garmin Connect Web le fait déjà. L'app affiche les fichiers, pas l'interprétation.
- Firmware OTA : hors périmètre.
- Multi-utilisateurs : application personnelle.

---

## Répartition par Epic

| Epic | Must | Should | Could | Won't | Total |
|------|------|--------|-------|-------|-------|
| 1 — Authentification | 4 | 0 | 0 | 0 | 4 |
| 2 — Workouts Cloud → Montre | 2 | 2 | 0 | 0 | 4 |
| 3 — Activités Montre → Cloud | 2 | 1 | 0 | 0 | 3 |
| 4 — Interface & historique | 2 | 1 | 0 | 0 | 3 |
| 5 — Robustesse | 0 | 1 | 2 | 0 | 3 |
| Hors epics | — | — | — | 4 | 4 |
| **Total** | **10** | **5** | **2** | **4** | **21** |

---

## MVP = 10 Must

Le MVP correspond à l'ensemble des stories marquées **Must**. Voir [docs/cadrage/mvp.md](mvp.md) pour la définition détaillée.