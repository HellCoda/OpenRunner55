# Contexte — OpenRunner55

- **Dernière mise à jour** : 2026-09-22
- **Phase** : 6 Déploiement — Finalisation (vue Compte & Paramètres + packaging AppImage). MVP+ fonctionnel bout en bout, validé en réel.

## Vision

Application desktop Linux (Fedora 44 / GNOME) pour synchroniser bidirectionnellement Garmin Connect et une montre Forerunner 55 via USB, sans Windows ni smartphone. Usage personnel, publication open-source prévue.

## Stack

- **Langage** : Python 3.12+
- **UI** : GTK 4 + libadwaita (ADR-003)
- **API Garmin** : `garminconnect` (headless, validé spike S-2)
- **Stockage** : SQLite (historique, logs, déduplication), GNOME Keyring (credentials)
- **USB** : pyudev + polling (ADR-006)
- **FIT** : `garmin-fit-sdk`
- **Packaging** : AppImage (ADR-009)

## Architecture

3 couches — UI → Services → Core. 7 packages, 10 modules. Détail : `docs/decisions/adr-002.md`.

```
src/openrunner55/
├── auth/        # Core — login, tokenstore, keyring
├── garmin/      # Core — wrapper API GC, retry, re-login 401
├── watch/       # Core — détection USB, lecture/écriture FIT
├── fit/         # Core — décodage, classification FIT
├── store/       # Core — SQLite (history, logs, transfers)
├── sync/        # Services — workouts, activities, wellness, history
└── ui/          # UI — auth_view, watch_view, history_view, account_view
```

## Décisions structurantes

| ADR | Sujet |
|-----|-------|
| ADR-001 | `garminconnect` validé |
| ADR-002 | Architecture 3 couches, `auth/` en Core |
| ADR-003 | GTK 4 + libadwaita |
| ADR-004 | GNOME Keyring, MFA non supporté (risque accepté) |
| ADR-005 | SQLite + `transferred_files` |
| ADR-006 | pyudev + polling |
| ADR-007 | Retry/backoff, délai 3s configurable |
| ADR-008 | Stratégie de tests |
| ADR-009 | Packaging AppImage |

## État d'avancement

| Epic | État | Merge |
|------|------|-------|
| 1 — Auth | ✅ Livré | `2a762a0` |
| 2 — Workouts Cloud → Montre | ✅ Livré (backend + frontend) | `bd68650`, `221002b` |
| 3 — Activités Montre → Cloud | ✅ Livré (backend + frontend) | `b87e3d5`, `f91a7ff` |
| 4 — Historique & logs | ✅ Livré | `cab70b9` |
| 5 — Sync auto & UX quotidienne | ✅ Livré | `ea248bc` |

**Tests** : 298 verts (`pytest tests/ -m unit`).
**Validation réelle** : Epics 2, 3 et 5 validés sur montre réelle (workouts GC → FR55, activités FR55 → GC, sync auto au branchement).

## Prochaine action

**Finalisation** (cf. `docs/finalisation-2026-09-22.md`, plan de suivi) :
- Séquence A — ménage repo ✅ (fait le 22/09)
- Séquence B — vue Compte & Paramètres (US-1.3, spec `docs/conception/ux-design.md` §4.3)
- Séquence C — packaging AppImage (ADR-009), README, licence MIT, release `v0.1.0`

**Items reportés post-publication** (tranchés le 22/09, non bloquants) :
- Retry 5xx non couvert (ADR-007 couvre 429 seulement)
- Granularité historique : N entrées « 1/1 » au lieu d'une agrégée
- Cosmétique : curseurs `Gtk.Paned`, placement bandeau montre connecté
- Uniformisation globale des timestamps (stockage UTC vs localtime)
- Dette technique : exception domaine pour le 409 (import direct
  `garminconnect` dans `sync/activities.py`)
- Sync auto descendante (workouts GC → montre au branchement)
- Export logs

## Navigation par phase

- Phase 1 Découverte → `docs/decouverte/context.md`
- Phase 2 Cadrage → `docs/cadrage/context.md`
- Exploration (spikes) → `docs/exploration/context.md`
- Décisions (ADR) → `docs/decisions/context.md`
- Phase 3 Conception → `docs/conception/context.md`
- Phase 4 Développement → `docs/dev/Phase-4-plan.md`
