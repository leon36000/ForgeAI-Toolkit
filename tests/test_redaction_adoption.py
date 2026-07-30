"""ERR-041A lot 2 — Tests d'adoption de la redaction centrale (chemins réels).

Chaque test traverse le VRAI point d'entrée public (construction de RouteError,
persistance du deploy-state, validation de route à l'export) et porte sur le
contenu RÉELLEMENT rendu/écrit — jamais sur un appel isolé du module redaction.

Auteur des tests : crew Kimi-K3 (dispatch lot 2). L'orchestrateur a complété la
troncature max-tokens du dernier test et corrigé une assertion (le round-trip
lisait la valeur de retour de `_load_deploy_state`, qui retourne None et restaure
dans le global `_DEPLOY_STATE`). Structure et intention crew inchangées.
"""

import json

import pytest

from forgeai.core.redaction import REDACTED
from forgeai.models.routes import RouteError
from forgeai.portability import PortabilityError, _validate_route


# ---------------------------------------------------------------------------
# A1 — Site 1 : RouteError rédige le secret interpolé à la construction
# ---------------------------------------------------------------------------

def test_routeerror_redige_secret_dans_le_message():
    api_key = "h" * 40  # proof:allow (fixture faux-secret : test de redaction)
    exc = RouteError(f"test de connexion RED : upstream a renvoyé api_key={api_key}")  # proof:allow (fixture faux-secret : test de redaction)
    assert api_key not in str(exc)
    assert REDACTED in str(exc)
    # fenêtre glissante de 8 : aucun fragment du secret ne survit
    for i in range(0, len(api_key) - 7):
        assert api_key[i:i + 8] not in str(exc)


def test_routeerror_message_anodin_inchange():
    message = "route 'demo' introuvable"
    exc = RouteError(message)
    assert str(exc) == message


def test_routeerror_args_non_str_ne_leve_pas():
    exc = RouteError(42)
    rendu = str(exc)
    assert isinstance(rendu, str)
    assert "42" in rendu


# ---------------------------------------------------------------------------
# A2 — Site 4 : _persist_deploy_state rédige les lignes avant persistance
# ---------------------------------------------------------------------------

def test_persist_deploy_state_redige_les_lignes(tmp_path, monkeypatch):
    from forgeai.web import server
    monkeypatch.setattr(server, "forgeai_home", lambda: tmp_path)
    secret = "z" * 40  # proof:allow (fixture faux-secret : test de redaction)
    with server._DEPLOY_STATE["lock"]:
        server._DEPLOY_STATE["lines"].clear()
        server._DEPLOY_STATE["lines"].append(f"deploy: export TOKEN=Bearer {secret}")
        server._DEPLOY_STATE["done"] = True
        server._DEPLOY_STATE["exit_code"] = 0
    server._persist_deploy_state()
    raw = (tmp_path / "deploy" / "deploy-state.json").read_text(encoding="utf-8")
    assert secret not in raw
    assert "«REDACTED»" in raw


def test_load_deploy_state_relit_un_etat_redige_sans_lever(tmp_path, monkeypatch):
    """Round-trip : un état persisté (déjà rédigé) se relit sans lever et ne fuit pas."""
    from forgeai.web import server
    monkeypatch.setattr(server, "forgeai_home", lambda: tmp_path)
    secret = "y" * 40  # proof:allow (fixture faux-secret : test de redaction)
    with server._DEPLOY_STATE["lock"]:
        server._DEPLOY_STATE["lines"].clear()
        server._DEPLOY_STATE["lines"].append(f"deploy: api_key={secret}")  # proof:allow (fixture faux-secret : test de redaction)
        server._DEPLOY_STATE["done"] = True
        server._DEPLOY_STATE["exit_code"] = 0
    server._persist_deploy_state()
    # _load_deploy_state() restaure dans le global _DEPLOY_STATE et retourne None :
    # on vide d'abord, on recharge depuis le disque, puis on inspecte le global.
    with server._DEPLOY_STATE["lock"]:
        server._DEPLOY_STATE["lines"].clear()
    server._load_deploy_state()
    brut = json.dumps(server._DEPLOY_STATE["lines"], ensure_ascii=False)
    assert secret not in brut
    assert REDACTED in brut


# ---------------------------------------------------------------------------
# A3 — Site 5 : _validate_route étend la détection SANS casser key_fingerprint
# ---------------------------------------------------------------------------

def test_validate_route_rejette_nouveau_champ_secret():
    # 'auth_token' n'était PAS dans l'ancien set {api_key, key, secret}. La garde
    # « champs inconnus » le rejetait déjà, mais avec un message générique ; la
    # délégation à is_sensitive_key le CLASSE comme secret (message dédié). On
    # assERT le message pour isoler la délégation (sinon test vert pour la mauvaise
    # raison : l'ancien code passerait aussi via la garde des champs inconnus).
    with pytest.raises(PortabilityError, match="secrète en clair"):
        _validate_route({"name": "x", "auth_token": "h" * 40})


def test_validate_route_accepte_key_fingerprint():
    # key_fingerprint contient 'key' mais est un champ SÛR (empreinte) :
    # il ne doit JAMAIS être rejeté, sinon toute route valide serait refusée.
    _validate_route({
        "name": "x",
        "provenance": "openrouter",
        "base_url": "u",
        "model_id": "m",
        "key_fingerprint": "abc123",
        "created_at": "2026-01-01",
    })


def test_validate_route_compat_trois_historiques():
    # Compatibilité : les trois champs historiquement rejetés le restent.
    for champ in ("api_key", "key", "secret"):
        with pytest.raises(PortabilityError):
            _validate_route({"name": "x", champ: "v"})
