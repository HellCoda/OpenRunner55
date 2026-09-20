# Contexte — OpenRunner55

- **Dernière mise à jour** : 2026-09-20
- **Phase** : 4 Développement — Epic 3 livré (backend + frontend), MVP fonctionnel bout en bout

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
| 4 — Historique & logs | ⏳ Prochain | — |
| 5 — Robustesse | ⏳ Post-MVP | — |

**Tests** : 248 verts (`pytest tests/ -m unit`).
**Validation réelle** : Epic 2 (workouts GC → FR55) et Epic 3 (activités FR55 → GC) validés sur montre réelle.

## Prochaine action

**Epic 4 — Historique & logs** : UI transverse (vue historique des syncs, vue logs d'opérations). Les stores backend existent depuis Epic 1/2 (`SyncHistoryStore`, `OperationLogger`). Backend quasi-néant — principalement du frontend.

**Points ouverts reportés d'Epic 3** (cf. `docs/dev/Epic-3-notes-frontend.md` § Points à trancher) :
- 409 « Duplicate Activity » traité comme échec au lieu de skip côté backend — gain d'UX majeur pour peu d'effort.
- Retry 5xx non couvert (ADR-007 couvre 429 seulement).
- Granularité historique : N entrées « 1/1 » au lieu d'une agrégée — affecte l'UX §4.2.
- Cosmétique : curseurs `Gtk.Paned`, placement bandeau montre connecté (transverse, hérité Epic 2).

## Navigation par phase

- Phase 1 Découverte → `docs/decouverte/context.md`
- Phase 2 Cadrage → `docs/cadrage/context.md`
- Exploration (spikes) → `docs/exploration/context.md`
- Décisions (ADR) → `docs/decisions/context.md`
- Phase 3 Conception → `docs/conception/context.md`
- Phase 4 Développement → `docs/dev/Phase-4-plan.md`
