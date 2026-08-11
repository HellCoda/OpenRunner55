"""Tests unitaires de l'UI auth_view.

Seule la logique pure est testée (mapping exception → message utilisateur,
UX §4.4). L'instanciation des widgets GTK nécessite un display — hors
périmètre des tests unitaires (ADR-008 : tests UI = responsabilité UX).
"""

from __future__ import annotations

import pytest

from openrunner55.auth.authenticator import GarminLoginError, GarminMFAError
from openrunner55.ui.auth_view import MFA_MESSAGE, NETWORK_MESSAGE, AuthView


@pytest.mark.unit
class TestErrorMapping:
    def test_mfa_error_uses_ux_message(self) -> None:
        message = AuthView.error_message(GarminMFAError("MFA requis"))
        assert message == MFA_MESSAGE
        assert "MFA" in message

    def test_login_error_uses_exception_message(self) -> None:
        message = AuthView.error_message(GarminLoginError("Identifiants incorrects."))
        assert message == "Identifiants incorrects."

    def test_unknown_error_uses_network_message(self) -> None:
        message = AuthView.error_message(RuntimeError("booom"))
        assert message == NETWORK_MESSAGE
        assert "Garmin Connect" in message

    def test_messages_match_ux_spec(self) -> None:
        # UX §4.4 liste trois messages d'erreur — on vérifie leur présence
        assert "Identifiants incorrects" in GarminLoginError(
            "Identifiants incorrects. Vérifiez votre email et mot de passe."
        ).args[0]
        assert "multi-facteurs" in MFA_MESSAGE
        assert "connexion Internet" in NETWORK_MESSAGE
