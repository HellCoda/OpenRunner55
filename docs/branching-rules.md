# Règles de Branches — OpenRunner55

## Principe

> **`main` = ce qui est livré. La branche = ce sur quoi on travaille.**

`main` est protégée : seul un merge validé y entre. Tout développement se fait sur une branche dédiée.

---

## Qui merge sur `main` ?

**Uniquement le Directeur de Projet** (agent `project-director`).

Les autres agents (Developer, Architect, QA, etc.) ne mergent jamais sur `main`. Ils poussent leur branche et le Directeur de Projet valide le merge — idéalement via une Pull Request.

---

## Types de branches

| Préfixe | Usage | Exemple |
|---------|-------|---------|
| `feat/` | Nouvelle fonctionnalité | `feat/decodage-gpx` |
| `fix/` | Correction de bug | `fix/erreur-parsing-tcx` |
| `refacto/` | Refactoring sans changement fonctionnel | `refacto/extraction-parser` |
| `spike/` | Exploration, prototypage, recherche | `spike/api-garmin-sdk` |
| `docs/` | Documentation uniquement | `docs/workflow-agents` |
| `chore/` | Tâche technique (config, CI, deps) | `chore/mise-a-jour-python` |

---

## Workflow quotidien

### 1. Départ — créer sa branche

```bash
git checkout main
git pull origin main
git checkout -b feat/mon-truc
```

### 2. Développement — commits fréquents

```bash
git add -A
git commit -m "feat: description claire de ce qui est fait"
```

Les messages de commit suivent la convention [Conventional Commits](https://www.conventionalcommits.org/) :
- `feat:` nouvelle fonctionnalité
- `fix:` correction de bug
- `docs:` documentation
- `refactor:` refactoring
- `chore:` tâche technique
- `spike:` exploration

### 3. Fin de tâche — pousser et demander le merge

```bash
git push origin feat/mon-truc
```

Puis le Directeur de Projet :
1. Ouvre une Pull Request via `gh pr create`
2. Vérifie que la branche est propre (tests, cohérence)
3. Merge dans `main`
4. Supprime la branche distante et locale

---

## Commandes pour le Directeur de Projet

### Créer une PR

```bash
gh pr create --base main --head feat/mon-truc --title "feat: description" --body "Contexte et changements."
```

### Merger la PR

```bash
gh pr merge feat/mon-truc --squash --delete-branch
```

### Nettoyer après merge

```bash
git checkout main
git pull origin main
git branch -d feat/mon-truc
```

---

## Règles d'or

1. **Jamais de commit direct sur `main`** sauf pour des typo/docs triviaux.
2. **Une branche = une tâche.** Pas de branche fourre-tout.
3. **Main à jour avant de créer une branche.** Pas de merge depuis une branche en retard.
4. **Les agents ne mergent pas.** Ils poussent, le Directeur de Projet merge.
5. **Branche mergée = branche supprimée.** Pas de branches zombies.

---

## Références

- [Conventional Commits](https://www.conventionalcommits.org/)
- [GitHub CLI — gh pr](https://cli.github.com/manual/gh_pr)
