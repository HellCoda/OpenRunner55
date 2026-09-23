# OpenRunner55

Application desktop Linux (Fedora / GNOME) pour synchroniser bidirectionnellement Garmin Connect et une montre Forerunner 55 via USB — sans Windows ni smartphone.

## Fonctionnalités

- Authentification à Garmin Connect (headless, sans navigateur)
- Envoi des workouts Garmin Connect vers la montre
- Remontée des activités de la montre vers Garmin Connect
- Synchronisation automatique au branchement de la montre
- Historique et logs des opérations
- Gestion du compte et déconnexion

## Prérequis

- Linux (testé sur Fedora 44 / GNOME)
- Python 3.12+
- GTK 4 + libadwaita
- GNOME Keyring (stockage sécurisé des identifiants)

## Installation

```bash
# Dépendances système (Fedora)
dnf install python3-gobject gtk4 libadwaita

# Environnement
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

## Utilisation

```bash
python -m openrunner55
```

Branchez votre montre Forerunner 55 en USB. L'application détecte la montre et synchronise automatiquement les nouvelles activités vers Garmin Connect.

## Limitations

- L'authentification multi-facteurs (MFA) Garmin Connect n'est pas supportée.
- Prévu pour Fedora / GNOME. Non testé sur d'autres environnements.
- La montre doit être montée comme système de fichiers USB (MTP).

## Licence

MIT — voir [LICENSE](LICENSE).
