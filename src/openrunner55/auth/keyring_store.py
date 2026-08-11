"""Stockage des credentials dans le GNOME Keyring (auth Core).

Conforme ADR-004 : les credentials (email, mot de passe) sont stockés dans la
collection `login` du trousseau GNOME via secretstorage (bindings DBus
libsecret). Jamais écrits en clair dans les logs ou le code.

Comportement headless : si le service Secret Storage est indisponible (DBus
pas lancé, session sans trousseau), les méthodes échouent proprement —
`load()` retourne None, `save()`/`delete()` retournent False — sans jamais
lever d'exception. L'application fonctionne alors sans persistance des
credentials (login manuel à chaque session).
"""

from __future__ import annotations

import logging
from collections.abc import Callable

_LOGGER = logging.getLogger(__name__)

# Attributs d'item : filtrent les entrées de l'application dans la collection.
_ATTR_APPLICATION = "application"
_APPLICATION_ID = "openrunner55"
_ATTR_ITEM_TYPE = "item-type"
_ITEM_TYPE_CREDENTIALS = "credentials"
_ATTR_EMAIL = "email"

_COLLECTION_DEFAULT = "login"

# Fonctions d'accès au Secret Service, injectables pour les tests.
_bus_init: Callable[[], object] | None = None
_collection_getter: Callable[[object], object] | None = None


class KeyringStore:
    """Accès aux credentials OpenRunner55 dans le trousseau GNOME."""

    def __init__(self, collection_name: str = _COLLECTION_DEFAULT) -> None:
        self._collection_name = collection_name

    # -- accès bas niveau ---------------------------------------------------

    def _collection(self):
        """Retourne la collection `login` déverrouillée ou None si indisponible."""
        try:
            import secretstorage

            bus = _bus_init() if _bus_init is not None else secretstorage.dbus_init()
            if _collection_getter is not None:
                collection = _collection_getter(bus)
            else:
                collection = secretstorage.get_default_collection(bus)
            if collection.is_locked():
                collection.unlock()
            return collection
        except Exception as exc:  # DBus absent, service down, permissions...
            _LOGGER.debug("Keyring indisponible : %s", exc)
            return None

    def _find_item(self, collection):
        """Retourne l'item credentials de l'application, ou None."""
        if collection is None:
            return None
        items = collection.search_items(
            {_ATTR_APPLICATION: _APPLICATION_ID, _ATTR_ITEM_TYPE: _ITEM_TYPE_CREDENTIALS}
        )
        try:
            return next(iter(items), None)
        except Exception as exc:
            _LOGGER.debug("Recherche keyring échouée : %s", exc)
            return None

    # -- API publique -------------------------------------------------------

    def save(self, email: str, password: str) -> bool:
        """Stocke les credentials dans la collection `login`.

        Retourne False si le keyring est indisponible.
        """
        collection = self._collection()
        if collection is None:
            _LOGGER.warning("Keyring indisponible : credentials non persistés")
            return False
        try:
            item = self._find_item(collection)
            if item is None:
                item = collection.create_item(
                    label=f"OpenRunner55 — {email}",
                    attributes={
                        _ATTR_APPLICATION: _APPLICATION_ID,
                        _ATTR_ITEM_TYPE: _ITEM_TYPE_CREDENTIALS,
                        _ATTR_EMAIL: email,
                    },
                    secret=password,
                )
            else:
                item.set_attributes(
                    {**item.get_attributes(), _ATTR_EMAIL: email}
                )
                item.set_secret(password)
            return True
        except Exception as exc:
            _LOGGER.error("Écriture keyring échouée : %s", exc)
            return False

    def load(self) -> tuple[str, str] | None:
        """Retourne (email, password) ou None (absent ou keyring indisponible)."""
        collection = self._collection()
        item = self._find_item(collection)
        if item is None:
            return None
        try:
            attrs = item.get_attributes()
            email = attrs.get(_ATTR_EMAIL)
            password = item.get_secret()
            if not email or not password:
                return None
            return email, password
        except Exception as exc:
            _LOGGER.error("Lecture keyring échouée : %s", exc)
            return None

    def delete(self) -> bool:
        """Supprime l'item credentials. Retourne True si supprimé, False sinon."""
        collection = self._collection()
        item = self._find_item(collection)
        if item is None:
            return False
        try:
            item.delete()
            return True
        except Exception as exc:
            _LOGGER.error("Suppression keyring échouée : %s", exc)
            return False
