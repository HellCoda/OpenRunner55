"""Tests unitaires du keyring store (secretstorage mocké — pas de trousseau en CI).

Voir docs/decisions/adr-004.md et adr-008.md.
"""

from __future__ import annotations

import pytest

from openrunner55.auth.keyring_store import KeyringStore


class FakeItem:
    """Doublure minimale d'un item secretstorage."""

    def __init__(self, attrs: dict[str, str], secret: str | None = None) -> None:
        self._attrs = dict(attrs)
        self._secret = secret
        self.deleted = False

    def get_attributes(self) -> dict[str, str]:
        return self._attrs

    def set_attributes(self, attrs: dict[str, str]) -> None:
        self._attrs.update(attrs)

    def get_secret(self) -> str | None:
        return self._secret

    def set_secret(self, secret: str) -> None:
        self._secret = secret

    def delete(self) -> None:
        self.deleted = True


class FakeCollection:
    """Doublure de collection secretstorage avec recherche par attributs."""

    def __init__(self) -> None:
        self._items: list[FakeItem] = []
        self.locked = False

    def is_locked(self) -> bool:
        return self.locked

    def unlock(self) -> None:
        self.locked = False

    def create_item(self, label: str, attributes: dict, secret: str) -> FakeItem:
        item = FakeItem(attributes, secret)
        item._label = label
        self._items.append(item)
        return item

    def search_items(self, query: dict[str, str]) -> list[FakeItem]:
        return [
            item
            for item in self._items
            if not item.deleted
            and all(item.get_attributes().get(k) == v for k, v in query.items())
        ]


class FakeSecretstorage:
    """Module secretstorage factice, installé via monkeypatch."""

    def __init__(self) -> None:
        self.collection = FakeCollection()
        self.dbus_init_called = 0

    def dbus_init(self):
        self.dbus_init_called += 1
        return "bus-factice"

    def get_default_collection(self, bus):
        return self.collection


@pytest.fixture
def fake_secretstorage(monkeypatch):
    fake = FakeSecretstorage()
    monkeypatch.setattr("openrunner55.auth.keyring_store._bus_init", fake.dbus_init)
    monkeypatch.setattr(
        "openrunner55.auth.keyring_store._collection_getter",
        fake.get_default_collection,
    )
    return fake


@pytest.mark.unit
class TestKeyringStore:
    def test_save_then_load_roundtrip(self, fake_secretstorage) -> None:
        store = KeyringStore()
        assert store.save("user@example.com", "secret") is True
        assert store.load() == ("user@example.com", "secret")

    def test_load_returns_none_when_empty(self, fake_secretstorage) -> None:
        assert KeyringStore().load() is None

    def test_delete_removes_item(self, fake_secretstorage) -> None:
        store = KeyringStore()
        store.save("user@example.com", "secret")
        assert store.delete() is True
        assert store.load() is None

    def test_delete_returns_false_when_absent(self, fake_secretstorage) -> None:
        assert KeyringStore().delete() is False

    def test_save_overwrites_existing_item(self, fake_secretstorage) -> None:
        store = KeyringStore()
        store.save("user@example.com", "secret1")
        store.save("user@example.com", "secret2")
        assert store.load() == ("user@example.com", "secret2")
        # Un seul item en collection
        items = fake_secretstorage.collection.search_items({"application": "openrunner55"})
        assert len(items) == 1

    def test_load_updates_email_attribute_on_save(self, fake_secretstorage) -> None:
        store = KeyringStore()
        store.save("first@example.com", "secret1")
        store.save("second@example.com", "secret2")
        assert store.load() == ("second@example.com", "secret2")

    def test_uses_default_login_collection(self, fake_secretstorage) -> None:
        store = KeyringStore()
        assert store._collection_name == "login"

    def test_raises_no_exception_when_keyring_unavailable(self, monkeypatch) -> None:
        def boom():
            raise RuntimeError("DBus absent")

        monkeypatch.setattr("openrunner55.auth.keyring_store._bus_init", boom)
        store = KeyringStore()
        assert store.load() is None
        assert store.save("user@example.com", "secret") is False
        assert store.delete() is False

    def test_raises_no_exception_when_secretstorage_import_fails(self, monkeypatch) -> None:
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "secretstorage":
                raise ModuleNotFoundError("pas de secretstorage")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        store = KeyringStore()
        assert store.load() is None
        assert store.save("a@b.c", "x") is False
