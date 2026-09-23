"""Configuration pytest partagée (ADR-008).

Markers : unit / integration / network.
Les tests integration nécessitent la montre FR55 branchée ; les tests network
nécessitent des credentials dans le keyring GNOME. Sans ces prérequis, les
tests concernés sont automatiquement ignorés (pytest.skip) pour éviter les
faux échecs.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# --- Markers ---------------------------------------------------------------


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "unit: tests unitaires (mocks uniquement, aucune dépendance externe)"
    )
    config.addinivalue_line(
        "markers", "integration: tests avec montre FR55 réelle branchée en USB"
    )
    config.addinivalue_line(
        "markers", "network: tests avec compte Garmin Connect réel"
    )


# --- Skips automatiques ----------------------------------------------------

WATCH_MOUNT_PATTERN = "/run/media/*/GARMIN/GARMIN/GarminDevice.xml"


def _watch_is_mounted() -> bool:
    media_root = Path("/run/media")
    if not media_root.is_dir():
        return False
    return any(media_root.glob("*/GARMIN/GARMIN/GarminDevice.xml"))


def _keyring_has_credentials() -> bool:
    """Détecte si un email est présent dans le keyring GNOME.

    Ne lève jamais d'exception : si le keyring est indisponible (headless,
    DBus absent), le test network sera simplement ignoré.
    """
    try:
        import secretstorage

        bus = secretstorage.dbus_init()
        collection = secretstorage.get_default_collection(bus)
        if not collection.is_locked():
            collection.unlock()
        return any(
            item.get_attributes().get("application") == "openrunner55"
            for item in collection.get_all_items()
        )
    except Exception:
        return False


@pytest.fixture(autouse=True)
def _apply_skips(request: pytest.FixtureRequest) -> None:
    marker = request.node.get_closest_marker("network")
    if marker is not None and not _keyring_has_credentials():
        pytest.skip("Test network ignoré : aucun credential OpenRunner55 dans le keyring GNOME")
    marker = request.node.get_closest_marker("integration")
    if marker is not None and not _watch_is_mounted():
        pytest.skip("Test integration ignoré : montre FR55 non branchée")


# --- Fixtures partagées ----------------------------------------------------

@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Chemin d'une base SQLite temporaire, détruite à la fin du test."""
    return tmp_path / "test.db"
