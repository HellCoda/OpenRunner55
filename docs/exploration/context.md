# Contexte — Exploration (spikes)

- **État** : terminée, verdict GO
- **Livrable principal** : `spike-S2-resultat.md`

## Contenu

- `spike-S1-resultat.md` — chaîne `.FIT → FR55` validée, auth en fallback navigateur.
- `mission-spike-S2.md` — mission du spike S-2 (5 blocs).
- `spike-S2-resultat.md` — auth headless validée, pipeline bidirectionnel validé, verdict GO.
- `tree-FR55.md` — arborescence des dossiers/fichiers de la montre FR55 (référence pour `watch/`).

## Risques levés

- INC-1 : auth sans navigateur — ✅ levée (stratégie `widget+cffi`).
- INC-2 : filtre FIT acceptés par GC — ⚠️ partiel (à valider empiriquement en dev).
- INC-3 : GTK vs web — ✅ tranchée (ADR-003, GTK 4).

## Limitations identifiées

Routes mobile GC bloquées (429/403), `SUMMARY` rejeté (406), HRV non peuplé, MFA non testée. Détail dans `spike-S2-resultat.md` §8.
