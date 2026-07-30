
"""
ERR-041A lot 1b — Tests TDAD du module redaction.

Le module src/forgeai/core/redaction.py est considéré EXISTANT (lot 1a) avec
l'API contractuelle :
  REDACTED: str
  SENSITIVE_KEY_TOKENS: frozenset[str]
  MAX_DEPTH: int
  is_sensitive_key(key) -> bool
  redact_text(s) -> str
  redact_mapping(d) -> dict
  redact_exception(exc) -> str
  import: from forgeai.core.redaction import (...)
"""

import ast
import copy
import re
import time
import types

import pytest

from forgeai.core.redaction import (
    MAX_DEPTH,
    REDACTED,
    SENSITIVE_KEY_TOKENS,
    is_sensitive_key,
    redact_exception,
    redact_mapping,
    redact_text,
)


# ---------------------------------------------------------------------------
# Secrets de test LONGS et distinctifs (n'apparaissent nulle part ailleurs)
# ---------------------------------------------------------------------------
SK = "sk-test00000000000000000000SECRET"
HEX32 = "a" * 32
HEX40 = "b" * 40
HEX64 = "c" * 64
HEX7 = "d" * 7  # sous le seuil M4 -> NON redacté
BEARER = "Bearer " + "e" * 40
PASSWORD = "f" * 24  # proof:allow (fixture faux-secret : test de redaction)
PASSPHRASE = "g" * 32
API_KEY = "h" * 32  # proof:allow (fixture faux-secret : test de redaction)
TOKEN = "i" * 32
LANGFUSE_KEY = "j" * 32


# ===========================================================================
# Groupe 1 — Formes redactables (secret ABSENT + REDACTED présent)
# ===========================================================================
FORMES = [
    pytest.param(BEARER, id="bearer"),
    pytest.param("authorization: " + SK, id="bearer-lowercase"),
    pytest.param("api_key=" + API_KEY, id="api_key_egal"),  # proof:allow (fixture faux-secret : test de redaction)
    pytest.param("api_key:" + API_KEY, id="api_key_deux_points"),  # proof:allow (fixture faux-secret : test de redaction)
    pytest.param("key=" + API_KEY, id="key_egal"),
    pytest.param("key:" + API_KEY, id="key_deux_points"),
    pytest.param("token=" + TOKEN, id="token_egal"),
    pytest.param("token:" + TOKEN, id="token_deux_points"),
    pytest.param("password=" + PASSWORD, id="password_egal"),  # proof:allow (fixture faux-secret : test de redaction)
    pytest.param("password:" + PASSWORD, id="password_deux_points"),  # proof:allow (fixture faux-secret : test de redaction)
    pytest.param("passphrase=" + PASSPHRASE, id="passphrase_egal"),
    pytest.param("passphrase:" + PASSPHRASE, id="passphrase_deux_points"),
    pytest.param("FORGEAI_API_TOKEN=" + SK, id="env_FORGEAI_API_TOKEN_egal"),
    pytest.param("FORGEAI_API_TOKEN:" + SK, id="env_FORGEAI_API_TOKEN_deux_points"),
    pytest.param("FORGEAI_API_KEY=" + SK, id="env_FORGEAI_API_KEY_egal"),  # proof:allow (fixture faux-secret : test de redaction)
    pytest.param("FORGEAI_API_KEY:" + SK, id="env_FORGEAI_API_KEY_deux_points"),  # proof:allow (fixture faux-secret : test de redaction)
    pytest.param("FORGEAI_SECRET=" + SK, id="env_FORGEAI_SECRET_egal"),  # proof:allow (fixture faux-secret : test de redaction)
    pytest.param("FORGEAI_SECRET:" + SK, id="env_FORGEAI_SECRET_deux_points"),  # proof:allow (fixture faux-secret : test de redaction)
    pytest.param("FORGEAI_PASSWORD=" + PASSWORD, id="env_FORGEAI_PASSWORD_egal"),  # proof:allow (fixture faux-secret : test de redaction)
    pytest.param("FORGEAI_PASSWORD:" + PASSWORD, id="env_FORGEAI_PASSWORD_deux_points"),  # proof:allow (fixture faux-secret : test de redaction)
    pytest.param("FORGEAI_PASSPHRASE=" + PASSPHRASE, id="env_FORGEAI_PASSPHRASE_egal"),
    pytest.param("FORGEAI_PASSPHRASE:" + PASSPHRASE, id="env_FORGEAI_PASSPHRASE_deux_points"),
    pytest.param("sk-" + SK, id="sk-prefix"),
    pytest.param("hex32:" + HEX32, id="hex32"),
    pytest.param("hex40:" + HEX40, id="hex40"),
    pytest.param("hex64:" + HEX64, id="hex64"),
]


@pytest.mark.parametrize("entree", FORMES)
def test_redact_text_secret_absent_et_REDACTED_present(entree):
    out = redact_text(entree)
    # Le secret de l'entrée est la partie située après le séparateur/préfixe.
    # On identifie la "queue" comme tout ce qui suit le séparateur reconnu.
    # Pour les formes simples, on extrait le dernier "token" alphanumérique long.
    queue = entree.split(":", 1)[-1].split("=", 1)[-1].strip()
    # Si la queue est le secret entier (cas sk-prefix), on l'utilise telle quelle.
    if entree.startswith("sk-") and queue.startswith("sk-"):
        queue = entree  # tout le contenu est sensible
    # Le secret doit avoir été retiré (fenêtre de 8 caractères du secret, cf. §9).
    for secret in (SK, API_KEY, TOKEN, PASSWORD, PASSPHRASE, HEX32, HEX40, HEX64, "e" * 40):
        if secret in entree:
            for i in range(0, max(0, len(secret) - 7)):
                fenetre = secret[i : i + 8]
                assert fenetre not in out, (
                    f"Fuite partielle détectée pour la fenêtre {fenetre!r} "
                    f"dans la sortie {out!r}"
                )
    # Le jeton REDACTED doit apparaître.
    assert REDACTED in out


# ===========================================================================
# Groupe 2 — Bornes M4 (hex court NON redacté, hex 32 redacté)
# ===========================================================================
def test_hex_7_non_redige():
    out = redact_text("hex7:" + HEX7)
    assert HEX7 in out
    assert REDACTED not in out


def test_hex_32_redige():
    out = redact_text("hex32:" + HEX32)
    assert HEX32 not in out
    assert REDACTED in out


# ===========================================================================
# Groupe 3 — M1 conserve «Bearer REDACTED»
# ===========================================================================
def test_m1_bearer_conserve_label():
    out = redact_text(BEARER)
    assert "Bearer" in out
    # La queue (e*40) doit être remplacée.
    assert "e" * 40 not in out
    assert REDACTED in out


def test_m1_bearer_valeur_courte_prouve_m1_essentiel():
    # DÉTECTANCE M1 (ajouté par l'orchestrateur après analyse de mutation) : une
    # valeur < 32 alphanumériques n'est captée NI par M2 (aucune clé=), NI par M3
    # (aucun préfixe sk-), NI par M4 (seuil 32) — SEUL M1 la rédige. Sans ce test,
    # retirer M1 resterait invisible car les autres fixtures Bearer utilisent des
    # valeurs ≥ 32 que M4 rattrape (sur-rédaction). Le schème d'autorisation doit
    # rédiger sa valeur quelle que soit sa longueur.
    val = "e" * 20
    out = redact_text("Bearer " + val)
    assert val not in out
    assert "Bearer" in out
    assert REDACTED in out


# ===========================================================================
# Groupe 4 — M2 conserve nom + séparateur, rédige valeur + guillemets
# ===========================================================================
def test_m2_nom_separateur_conserves_valeur_redigee():
    entree = 'api_key="' + API_KEY + '"'  # proof:allow (fixture faux-secret : test de redaction)
    out = redact_text(entree)
    assert "api_key" in out
    # Le signe = et les guillemets doivent subsister, la valeur non.
    assert "=" in out
    assert '"' in out
    assert API_KEY not in out
    assert REDACTED in out


# ===========================================================================
# Groupe 5 — Mapping imbriqué
# ===========================================================================
def test_redact_mapping_imbrique():
    S = "h" * 32
    P = "g" * 32
    payload = {
        "routes": [{"api_key": S, "name": "openai"}],
        "meta": {"passphrase": P},
        "tags": ["a", S],
        "top_key": "sk-" + SK,
    }
    payload_copy = copy.deepcopy(payload)
    out = redact_mapping(payload)

    # Structure préservée pour les clés non-sensibles.
    assert set(out.keys()) == {"routes", "meta", "tags", "top_key"}
    assert isinstance(out["routes"], list) and len(out["routes"]) == 1
    assert isinstance(out["routes"][0], dict)
    assert out["routes"][0]["name"] == "openai"
    assert out["tags"][0] == "a"
    assert isinstance(out["meta"], dict)

    # Valeurs sensibles == REDACTED.
    assert out["routes"][0]["api_key"] == REDACTED
    assert out["meta"]["passphrase"] == REDACTED
    assert out["tags"][1] == REDACTED
    # top_key commence par sk- -> redact_text appliqué sur la valeur.
    assert out["top_key"] != ("sk-" + SK)
    assert REDACTED in out["top_key"] or "sk-" not in out["top_key"] or SK not in out["top_key"]
    assert SK not in out["top_key"]
    assert S not in (out["routes"][0]["api_key"], out["tags"][1])
    assert P not in out["meta"]["passphrase"]

    # Entrée NON mutée.
    assert payload == payload_copy


# ===========================================================================
# Groupe 6 — Prédicat is_sensitive_key
# ===========================================================================
@pytest.mark.parametrize(
    "cle",
    [
        "FORGEAI_API_TOKEN",
        "LANGFUSE_ENCRYPTION_KEY",
        "api_key",
        "key",
        "secret",
    ],
)
def test_is_sensitive_key_true(cle):
    assert is_sensitive_key(cle) is True


@pytest.mark.parametrize(
    "cle",
    [
        "monkey",
        "keyboard",
        "note",
        "FORGEAI_HOSTNAME",  # pas dans les env sensibles
        "user_name",
    ],
)
def test_is_sensitive_key_false(cle):
    assert is_sensitive_key(cle) is False


def test_sensitive_key_tokens_est_frozenset():
    assert isinstance(SENSITIVE_KEY_TOKENS, frozenset)
    assert len(SENSITIVE_KEY_TOKENS) > 0


# ===========================================================================
# Groupe 7 — Non-lever (robustesse)
# ===========================================================================
def test_redact_text_none():
    out = redact_text(None)
    assert isinstance(out, str)


def test_redact_text_non_str():
    assert isinstance(redact_text(123), str)
    assert isinstance(redact_text(b"bytes"), str)


def test_redact_text_str_qui_leve():
    class Boom:
        def __str__(self):
            raise RuntimeError("boom")

    out = redact_text(Boom())
    assert isinstance(out, str)


def test_redact_mapping_dict_autoreferent():
    d = {"a": 1}
    d["self"] = d  # auto-référencé
    # Doit retourner (sans exception) et produire un dict.
    out = redact_mapping(d)
    assert isinstance(out, dict)


def test_redact_mapping_valeur_bytes():
    d = {"name": b"openai", "api_key": "h" * 32}
    out = redact_mapping(d)
    assert isinstance(out, dict)
    assert "name" in out
    # Pas d'exception, on accepte la conversion.


def test_redact_mapping_valeur_objet_etranger():
    class Obj:
        def __repr__(self):
            return "<Obj>"

    d = {"k": Obj(), "api_key": "h" * 32}
    out = redact_mapping(d)
    assert isinstance(out, dict)
    assert "k" in out


# ===========================================================================
# Groupe 8 — Idempotence
# ===========================================================================
TEXT_FIXTURES = [
    "Bearer " + "e" * 40,
    "api_key=" + "h" * 32,  # proof:allow (fixture faux-secret : test de redaction)
    "FORGEAI_API_TOKEN=" + SK,
    "hex32:" + HEX32,
    "sk-" + SK,
    "password=" + PASSWORD,  # proof:allow (fixture faux-secret : test de redaction)
    "passphrase:" + PASSPHRASE,
    "key=" + API_KEY,
    "token:" + TOKEN,
    "Authorization: " + "f" * 32,
]


@pytest.mark.parametrize("entree", TEXT_FIXTURES)
def test_redact_text_idempotent(entree):
    once = redact_text(entree)
    twice = redact_text(once)
    assert once == twice


def test_redact_mapping_idempotent():
    payload = {
        "routes": [{"api_key": "h" * 32, "name": "openai"}],
        "meta": {"passphrase": "g" * 32},
        "tags": ["a", "h" * 32],
    }
    once = redact_mapping(payload)
    twice = redact_mapping(once)
    assert once == twice


# ===========================================================================
# Groupe 9 — Absence sans fuite partielle (fenêtre de 8 caractères)
# ===========================================================================
SECRETS_LONGS = [
    SK,
    API_KEY,
    TOKEN,
    PASSWORD,
    PASSPHRASE,
    HEX32,
    HEX40,
    HEX64,
    "e" * 40,
]


@pytest.mark.parametrize("secret", SECRETS_LONGS)
def test_redact_text_absence_sans_fuite_partielle(secret):
    # On fabrique une entrée "key=" + secret (forme redactable garantie).
    entree = "key=" + secret
    out = redact_text(entree)
    assert secret not in out
    # Vérification fenêtre glissante de 8 caractères.
    for i in range(0, max(0, len(secret) - 7)):
        fenetre = secret[i : i + 8]
        assert fenetre not in out, (
            f"Fuite partielle: fenêtre {fenetre!r} présente dans {out!r}"
        )


@pytest.mark.parametrize("secret", SECRETS_LONGS)
def test_redact_mapping_absence_sans_fuite_partielle(secret):
    payload = {"api_key": secret, "name": "openai"}
    out = redact_mapping(payload)
    s = str(out)
    assert secret not in s
    for i in range(0, max(0, len(secret) - 7)):
        fenetre = secret[i : i + 8]
        assert fenetre not in s, (
            f"Fuite partielle mapping: fenêtre {fenetre!r} dans {s!r}"
        )


# ===========================================================================
# Groupe 10 — Chemin réel via RouteError-like (stub autonome, pas d'import routes)
# ===========================================================================
def test_chemin_reel_route_error_like():
    """
    Construit un message d'exception façon RouteError avec la clé interpolée
    dans le message, et vérifie que la sortie redact_exception retire bien
    le secret (critère strict + fenêtres §9).
    """
    api_key = "h" * 32  # proof:allow (fixture faux-secret : test de redaction)
    # Stub local d'une RouteError (pas d'import de forgeai.routes).
    class RouteErrorLike(Exception):
        pass

    msg = f"Failed to call upstream: api_key={api_key} status=500"  # proof:allow (fixture faux-secret : test de redaction)
    exc = RouteErrorLike(msg)

    s = redact_exception(exc)
    # Le secret ne doit pas apparaître (mêmes fenêtres).
    assert api_key not in s
    for i in range(0, len(api_key) - 7):
        fenetre = api_key[i : i + 8]
        assert fenetre not in s
    # REDACTED doit apparaître.
    assert REDACTED in s


# ===========================================================================
# Groupe 11 — Anti-ReDoS (le test EST le détecteur)
# ===========================================================================
def test_anti_redos_key_eq_long():
    entree = "key=" + ("A" * 100000)
    t0 = time.monotonic()
    out = redact_text(entree)
    dt = time.monotonic() - t0
    # Pas d'assert de durée, mais le test ne doit pas traîner plusieurs secondes.
    assert dt < 5.0
    assert isinstance(out, str)
    # Le secret de 100k A ne doit pas avoir fui.
    assert "A" * 100000 not in out


def test_anti_redos_sk_prefix_long():
    entree = "sk-" + ("z" * 100000)
    t0 = time.monotonic()
    out = redact_text(entree)
    dt = time.monotonic() - t0
    assert dt < 5.0
    assert isinstance(out, str)
    assert "z" * 100000 not in out


# ===========================================================================
# Groupe 12 — Contrat de couche : AST ne doit révéler aucun import forgeai
# ===========================================================================
def test_module_redaction_sans_import_forgeai():
    import forgeai.core.redaction as mod

    source = ast.parse(open(mod.__file__, "r", encoding="utf-8").read())
    for node in ast.walk(source):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("forgeai"), (
                    f"Import interdit de {alias.name!r} dans core/redaction.py"
                )
                assert not alias.name.startswith("forgeai."), (
                    f"Import interdit de {alias.name!r} dans core/redaction.py"
                )
        elif isinstance(node, ast.ImportFrom):
            assert node.module is None or not node.module.startswith("forgeai"), (
                f"from-import interdit de {node.module!r} dans core/redaction.py"
            )


# ===========================================================================
# Tests additionnels de cohérence (non requis mais utiles au harnais)
# ===========================================================================
def test_redact_exception_avec_chaine_brute():
    exc = ValueError("api_key=" + API_KEY)  # proof:allow (fixture faux-secret : test de redaction)
    out = redact_exception(exc)
    assert API_KEY not in out
    assert REDACTED in out


def test_redact_mapping_vide():
    assert redact_mapping({}) == {}


def test_redact_text_chaine_vide():
    assert redact_text("") == ""


def test_redact_text_sans_marqueur():
    texte = "Bonjour, ceci est un message anodin sans secret."
    assert redact_text(texte) == texte


def test_max_depth_entier_positif():
    assert isinstance(MAX_DEPTH, int)
    assert MAX_DEPTH > 0
