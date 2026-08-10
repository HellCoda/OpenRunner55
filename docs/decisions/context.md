# Contexte — Décisions (ADR)

- **État** : 9 ADR produits et alignés
- **Format** : Contexte → Décision → Alternatives → Conséquences

## Registre

| ADR | Sujet | Statut |
|-----|-------|--------|
| ADR-001 | Bibliothèque `garminconnect` | ✅ Validé (spike) |
| ADR-002 | Architecture 3 couches, 7 packages, `auth/` en Core | ✅ Aligné |
| ADR-003 | GTK 4 + libadwaita | ✅ |
| ADR-004 | GNOME Keyring, MFA risque résiduel accepté | ✅ |
| ADR-005 | SQLite + `transferred_files` (déduplication) | ✅ |
| ADR-006 | pyudev + polling (détection USB) | ✅ |
| ADR-007 | Retry/backoff 429, délai 3s configurable, cascade 401 | ✅ |
| ADR-008 | Stratégie de tests | ✅ |
| ADR-009 | Packaging AppImage | ✅ |

## Convention

Les ADR se référencent par nom (`ADR-002`), pas par chemin. Aucune modification d'ADR en phase de développement sauf découverte majeure — toute évolution est un nouvel ADR ou une révision datée.
