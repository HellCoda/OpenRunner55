# Documentation — OpenRunner55

Toute la documentation projet est organisée par phase de la méthode Usage-LLM.

## Structure

```
docs/
├── context.md             # Point d'entrée — contexte global synthétique
├── decouverte/            # Phase 1 — Découverte (problème, persona)
├── cadrage/               # Phase 2 — Cadrage (PRD, MVP, epics, priorisation)
├── exploration/           # Spikes & recherche technique
├── decisions/             # ADR (Architecture Decision Records)
└── conception/            # Phase 3 — Conception (UX, architecture, briefs)
```

## Comment naviguer

- **Tu démarres une session ?** Lis [`context.md`](context.md) — synthèse globale + point d'entrée vers chaque phase.
- **Tu cherches une décision ?** Va dans [`decisions/`](decisions/) — 9 ADR indexés dans son `context.md`.
- **Tu travailles sur l'UX ?** Va dans [`conception/`](conception/) — `ux-design.md` est le livrable principal.
- **Tu veux le contexte d'une phase précise ?** Chaque sous-dossier a son propre `context.md` court.

## Convention de référencement

- Les ADR se référencent par nom (`ADR-002`, `ADR-005`) — pas par chemin.
- Les autres documents utilisent des chemins depuis la racine du projet (`docs/decisions/adr-002.md`).
- Chaque `context.md` de sous-dossier reste court (< 20 lignes) : contenu, état, point d'entrée.

## État courant

L'état du projet (phase, avancement, prochaine action) vit dans [`context.md`](context.md) — source unique. Ce fichier ne porte que la navigation.
