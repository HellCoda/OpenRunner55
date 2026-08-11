"""Tests unitaires de l'authenticator (garminconnect mocké — aucun appel réseau).

Voir docs/decisions/adr-004.md (MFA non supporté), adr-007.md (cascade 401)
et adr-008.md.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from openrunner55.auth.authenticator import (
    TOKENSTORE_FILE,
    Authenticator,
    GarminLoginError,
    GarminMFAError,
    SessionNotFoundError,
)
from openrunner55.auth.keyring_store import KeyringStore
from garminconnect import (
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)


def _make_jwt(exp: datetime) -> str:
    """Construit un JWT factice avec l'expiration demandée (3 segments)."""
    import base64
    import json

    def b64url(data: dict) -> str:
        raw = json.dumps(data).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    header = b64url({"alg": "none"})
    payload = b64url({"exp": int(exp.timestamp())})
    return f"{header}.{payload}.signature"


def _fake_client(exp: datetime | None = None, has_token: bool = True) -> object:
    """Client factice imitant la structure `Garmin().client` de la lib."""
    class FakeInner:
        def __init__(self):
            self.di_token = _make_jwt(exp) if exp is not None else ("token" if has_token else None)

    class FakeGarmin:
        def __init__(self):
            self.client = FakeInner()

    return FakeGarmin()


class FakeGarminConnect:
    """Doublure de Garmin() : expose .client.di_token et .login(tokenstore)."""

    def __init__(self, *, email=None, password=None):
        self.email = email
        self.password = password
        self.client = self  # Garmin().client → self (structure de la lib)
        self.di_token = None
        self.last_tokenstore = None

    def login(self, tokenstore: str | None = None):
        self.last_tokenstore = tokenstore
        effect = _FAKE_STATE["login_effect"]
        if effect is not None:
            return effect(self)
        self.di_token = "token-valide"
        return None, None


_FAKE_STATE = {"login_effect": None}


@pytest.fixture
def fake_garmin(monkeypatch):
    """Injecte un constructeur Garmin factice + capture les instances créées."""
    import openrunner55.auth.authenticator as auth_mod

    instances: list[FakeGarminConnect] = []

    class GarminFactory:
        def __call__(self, email=None, password=None, **kwargs):
            instance = FakeGarminConnect(email=email, password=password)
            instances.append(instance)
            return instance

    monkeypatch.setattr(auth_mod, "Garmin", GarminFactory())
    _FAKE_STATE["login_effect"] = None  # reset entre tests
    return {"instances": instances}


@pytest.fixture
def fake_keyring(monkeypatch) -> KeyringStore:
    """Keyring en mémoire : les credentials ne passent jamais par DBus."""

    class MemoryKeyring(KeyringStore):
        def __init__(self):
            self._stored: tuple[str, str] | None = None
            self.deleted = False

        def save(self, email: str, password: str) -> bool:
            self._stored = (email, password)
            return True

        def load(self):
            return self._stored

        def delete(self) -> bool:
            self._stored = None
            self.deleted = True
            return True

    return MemoryKeyring()


@pytest.mark.unit
class TestAuthenticatorLogin:
    def test_login_success_returns_client(self, fake_garmin, fake_keyring) -> None:
        auth = Authenticator(keyring=fake_keyring)
        client = auth.login("user@example.com", "password")
        assert client is not None
        assert fake_keyring._stored == ("user@example.com", "password")

    def test_login_saves_tokenstore_path_to_lib(self, fake_garmin, fake_keyring) -> None:
        auth = Authenticator(keyring=fake_keyring)
        auth.login("user@example.com", "password")
        assert fake_garmin["instances"][0].last_tokenstore == str(TOKENSTORE_FILE)

    def test_login_mfa_raises_clear_error(self, fake_garmin, fake_keyring) -> None:
        _FAKE_STATE["login_effect"] = lambda _c: ("needs_mfa", None)
        auth = Authenticator(keyring=fake_keyring)
        with pytest.raises(GarminMFAError) as excinfo:
            auth.login("user@example.com", "password")
        assert "MFA" in str(excinfo.value)

    def test_login_wrong_credentials_raises_login_error(self, fake_garmin, fake_keyring) -> None:
        def reject(client):
            raise GarminConnectAuthenticationError("bad credentials")

        _FAKE_STATE["login_effect"] = reject
        auth = Authenticator(keyring=fake_keyring)
        with pytest.raises(GarminLoginError):
            auth.login("user@example.com", "wrong")

    def test_login_rate_limit_raises_login_error(self, fake_garmin, fake_keyring) -> None:
        def ratelimit(client):
            raise GarminConnectTooManyRequestsError("429")

        _FAKE_STATE["login_effect"] = ratelimit
        auth = Authenticator(keyring=fake_keyring)
        with pytest.raises(GarminLoginError) as excinfo:
            auth.login("user@example.com", "password")
        assert "429" in str(excinfo.value)

    def test_login_network_error_raises_login_error(self, fake_garmin, fake_keyring) -> None:
        def offline(client):
            raise GarminConnectConnectionError("timeout")

        _FAKE_STATE["login_effect"] = offline
        auth = Authenticator(keyring=fake_keyring)
        with pytest.raises(GarminLoginError):
            auth.login("user@example.com", "password")

    def test_login_does_not_save_keyring_on_failure(self, fake_garmin, fake_keyring) -> None:
        _FAKE_STATE["login_effect"] = lambda _c: (_ for _ in ()).throw(
            GarminConnectAuthenticationError("no")
        )
        auth = Authenticator(keyring=fake_keyring)
        with pytest.raises(GarminLoginError):
            auth.login("user@example.com", "password")
        assert fake_keyring._stored is None


@pytest.mark.unit
class TestResumeSession:
    def test_resume_returns_none_without_tokenstore(self, fake_garmin, fake_keyring, monkeypatch) -> None:
        monkeypatch.setattr(
            "openrunner55.auth.authenticator.TOKENSTORE_FILE",
            Path("/nonexistent/tokens.json"),
        )
        auth = Authenticator(keyring=fake_keyring)
        assert auth.resume_session() is None

    def test_resume_returns_client_with_valid_tokenstore(self, fake_garmin, fake_keyring, tmp_path, monkeypatch) -> None:
        token_file = tmp_path / "tokens.json"
        token_file.write_text("{}")
        monkeypatch.setattr(
            "openrunner55.auth.authenticator.TOKENSTORE_FILE", token_file
        )
        auth = Authenticator(keyring=fake_keyring)
        client = auth.resume_session()
        assert client is not None
        # Tokenstore passé à la lib
        assert fake_garmin["instances"][-1].last_tokenstore == str(token_file)

    def test_resume_returns_none_on_invalid_tokens(self, fake_garmin, fake_keyring, tmp_path, monkeypatch) -> None:
        token_file = tmp_path / "tokens.json"
        token_file.write_text("{}")
        monkeypatch.setattr(
            "openrunner55.auth.authenticator.TOKENSTORE_FILE", token_file
        )

        def reject(client):
            raise GarminConnectAuthenticationError("stale token")

        _FAKE_STATE["login_effect"] = reject
        auth = Authenticator(keyring=fake_keyring)
        assert auth.resume_session() is None


@pytest.mark.unit
class TestIsAuthenticated:
    def test_none_client_is_not_authenticated(self) -> None:
        assert Authenticator.is_authenticated(None) is False

    def test_valid_token_is_authenticated(self) -> None:
        client = _fake_client(exp=datetime.now(timezone.utc) + timedelta(hours=1))
        assert Authenticator.is_authenticated(client) is True

    def test_expired_token_is_not_authenticated(self) -> None:
        client = _fake_client(exp=datetime.now(timezone.utc) - timedelta(hours=1))
        assert Authenticator.is_authenticated(client) is False

    def test_no_token_is_not_authenticated(self) -> None:
        client = _fake_client(has_token=False)
        assert Authenticator.is_authenticated(client) is False

    def test_token_without_expiry_is_considered_valid(self) -> None:
        # exp absent : la lib a validé le token au login → authentifié
        client = _fake_client(exp=None, has_token=True)
        assert Authenticator.is_authenticated(client) is True


@pytest.mark.unit
class TestGetClient:
    def test_get_client_returns_session(self, fake_garmin, fake_keyring, tmp_path, monkeypatch) -> None:
        token_file = tmp_path / "tokens.json"
        token_file.write_text("{}")
        monkeypatch.setattr(
            "openrunner55.auth.authenticator.TOKENSTORE_FILE", token_file
        )
        auth = Authenticator(keyring=fake_keyring)
        assert auth.get_client() is not None

    def test_get_client_raises_without_session(self, fake_garmin, fake_keyring, monkeypatch) -> None:
        monkeypatch.setattr(
            "openrunner55.auth.authenticator.TOKENSTORE_FILE",
            Path("/nonexistent/tokens.json"),
        )
        auth = Authenticator(keyring=fake_keyring)
        with pytest.raises(SessionNotFoundError):
            auth.get_client()


@pytest.mark.unit
class TestCredentials:
    def test_save_credentials_delegates_to_keyring(self, fake_keyring) -> None:
        auth = Authenticator(keyring=fake_keyring)
        assert auth.save_credentials("a@b.c", "pw") is True
        assert fake_keyring._stored == ("a@b.c", "pw")

    def test_delete_credentials_removes_tokenstore(self, fake_keyring, tmp_path, monkeypatch) -> None:
        token_file = tmp_path / "tokens.json"
        token_file.write_text("{}")
        monkeypatch.setattr(
            "openrunner55.auth.authenticator.TOKENSTORE_FILE", token_file
        )
        auth = Authenticator(keyring=fake_keyring)
        assert auth.delete_credentials() is True
        assert not token_file.exists()
        assert fake_keyring.deleted is True
