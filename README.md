# OpenRunner55

Application desktop Linux (Fedora / GNOME) pour synchroniser bidirectionnellement Garmin Connect et une montre Forerunner 55 via USB — sans Windows ni smartphone.

## État du projet

- **Phase** : 3 Conception — gate validée, prête pour Phase 4 Développement.
- **MVP** : 10 user stories, ~7 jours/homme. Détail dans [`docs/cadrage/mvp.md`](docs/cadrage/mvp.md).

## Documentation

Toute la documentation est dans [`docs/`](docs/). Point d'entrée : [`docs/context.md`](docs/context.md).

Organisation par phase :

- [`docs/decouverte/`](docs/decouverte/) — Phase 1 : project brief, persona
- [`docs/cadrage/`](docs/cadrage/) — Phase 2 : PRD, MVP, epics, priorisation
- [`docs/exploration/`](docs/exploration/) — Spikes & recherche technique
- [`docs/decisions/`](docs/decisions/) — ADR (Architecture Decision Records)
- [`docs/conception/`](docs/conception/) — Phase 3 : UX design, architecture, briefs

## Stack

- **Langage** : Python 3.12+
- **UI** : GTK 4 + libadwaita
- **API Garmin** : `garminconnect` (headless)
- **Stockage** : SQLite + GNOME Keyring
- **USB** : pyudev
- **Packaging** : AppImage

## Développement

```bash
# Prérequis système (Fedora)
dnf install python3-gobject gtk4 libadwaita

# Environnement
python -m venv .venv && source .venv/bin/activate
pip install -e .
python -m openrunner55
```

## Licence

MIT (à confirmer). Usage personnel à l'origine.
