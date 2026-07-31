"""OPS-031A — `forgeai status` et santé re-sondable.

Vérifie la séparation liveness / santé profonde : `/api/health` reste statique, public et bon
marché, tandis que `/api/status` révèle l'état de l'infra ET coûte des sondes — il doit donc être
gardé d'office par la classification fail-closed de WEB-017.
"""

import json
import secrets
import threading
import urllib.error
import urllib.request

import pytest

import forgeai.web.server as server
from forgeai.status import INDISPONIBLE, collect_status, format_status_humain
from forgeai.web.server import build_server


def _get(base, path, headers=None):
    req = urllib.request.Request(base + path, method="GET", headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


@pytest.fixture()
def live():
    srv = build_server("127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


@pytest.fixture()
def live_avec_jeton(monkeypatch):
    """Serveur lié 0.0.0.0 AVEC jeton : l'autorisation est donc exigée (WEB-017)."""
    # Jeton GÉNÉRÉ plutôt que littéral : aucune chaîne à forte entropie n'entre au dépôt (gitleaks
    # ne peut pas distinguer un faux jeton d'un vrai), et le test n'a besoin d'aucune valeur fixe.
    monkeypatch.setattr(server, "_WEB_TOKEN", secrets.token_hex(8))
    srv = build_server("0.0.0.0", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


def test_g1_degradation_gracieuse_une_sonde_en_echec():
    """CA1 : une sonde en panne n'empêche pas les autres d'être renseignées."""
    def _casse():
        raise RuntimeError("kubectl injoignable")

    etat = collect_status(
        backends=lambda: ["compose"],
        cluster=_casse,
        deploiement=lambda: {"done": True},
        materiel=lambda: {"cpu": "x"},
    )

    assert etat["backends"]["etat"] == "ok" and etat["backends"]["valeur"] == ["compose"]
    assert etat["cluster"]["etat"] == INDISPONIBLE, "la section en panne doit être marquée"
    assert "kubectl injoignable" in etat["cluster"]["detail"]
    assert etat["deploiement"]["etat"] == "ok", "une panne ne doit pas contaminer les autres sections"
    assert etat["materiel"]["etat"] == "ok"
    assert etat["version"]


def test_g2_message_de_sonde_est_redige():
    """CA1 : un message d'outil porteur d'un faux-secret est rédigé avant d'entrer dans l'agrégat."""
    faux = "api_key=" + "z" * 32  # proof:allow (faux jeton de test)

    def _fuit():
        raise RuntimeError(f"echec outil {faux}")

    etat = collect_status(
        backends=_fuit, cluster=lambda: [], deploiement=lambda: {}, materiel=lambda: {},
    )
    detail = etat["backends"]["detail"]
    assert faux not in detail, "le message de sonde doit être rédigé"
    assert "«REDACTED»" in detail


def test_g3_api_status_loopback_200(live):
    """CA2 : GET /api/status en loopback renvoie l'agrégat."""
    code, corps = _get(live, "/api/status")
    assert code == 200
    etat = json.loads(corps)
    assert set(etat) >= {"version", "backends", "cluster", "deploiement", "materiel"}


def test_g4_api_status_exige_le_jeton_hors_loopback(live_avec_jeton):
    """CA2 : la santé profonde n'est JAMAIS anonyme — 401 sans jeton (hérité de WEB-017)."""
    code, _ = _get(live_avec_jeton, "/api/status")
    assert code == 401, f"attendu 401 sans jeton sur /api/status, reçu {code}"


def test_g5_health_reste_public_et_statique(live_avec_jeton, live):
    """CA3 : /api/health reste 200 SANS jeton et strictement statique (liveness bon marché)."""
    code, corps = _get(live_avec_jeton, "/api/health")
    assert code == 200, "la liveness ne doit pas devenir gardée"
    assert json.loads(corps) == {"status": "ok"}, "la liveness doit rester statique"

    code2, corps2 = _get(live, "/api/health")
    assert code2 == 200 and json.loads(corps2) == {"status": "ok"}


def test_g6_cli_status_json(capsys):
    """CA4 : `forgeai status --json` imprime le MÊME agrégat (mêmes clés que la route)."""
    from forgeai.cli import main

    rc = main(["status", "--json"])
    assert rc == 0
    sortie = capsys.readouterr().out
    etat = json.loads(sortie)
    assert set(etat) >= {"version", "backends", "cluster", "deploiement", "materiel"}


def test_g6b_cli_status_humain(capsys):
    """CA4 : la sortie humaine est lisible et mentionne chaque section."""
    from forgeai.cli import main

    rc = main(["status"])
    assert rc == 0
    sortie = capsys.readouterr().out
    for section in ("backends", "cluster", "deploiement", "materiel"):
        assert section in sortie


def test_g7_format_humain_marque_les_sections_indisponibles():
    """CA1 : le rendu humain distingue clairement une section indisponible."""
    etat = {
        "version": "0.1.0",
        "backends": {"etat": "ok", "valeur": ["compose"]},
        "cluster": {"etat": INDISPONIBLE, "detail": "RuntimeError: injoignable"},
        "deploiement": {"etat": "ok", "valeur": {}},
        "materiel": {"etat": "ok", "valeur": {}},
    }
    rendu = format_status_humain(etat)
    assert INDISPONIBLE in rendu
    assert "injoignable" in rendu


def test_g8_status_ne_relance_pas_kubectl_a_chaque_appel(live, monkeypatch):
    """CA2 : plusieurs GET /api/status ne déclenchent qu'UNE sonde cluster (kubectl).

    Détecteur de l'objection de revue : la story promet une lecture « à travers les caches TTL » pour
    ne pas offrir de levier d'amplification. Sans cache sur `cluster_status`, chaque requête
    relancerait un sous-processus `kubectl` — la promesse serait fausse.
    """
    server._hardware_cache_clear()
    compteur = {"n": 0}

    def _faux_cluster(_runner):
        compteur["n"] += 1
        return [{"name": "n1", "ready": True}]

    monkeypatch.setattr(server, "cluster_status", _faux_cluster)
    try:
        for _ in range(5):
            code, _corps = _get(live, "/api/status")
            assert code == 200
        assert compteur["n"] == 1, (
            f"{compteur['n']} sondes kubectl pour 5 requêtes — le cache TTL cluster est absent"
        )
    finally:
        server._hardware_cache_clear()


def test_g9_purge_couvre_le_cache_cluster():
    """CA2 : `_hardware_cache_clear` purge AUSSI le cache cluster (invalidation cohérente)."""
    server._cluster_cache = [{"name": "obsolete"}]
    server._cluster_cache_time = 1e12  # très récent → servirait le cache
    server._hardware_cache_clear()
    assert server._cluster_cache is None, "la purge doit couvrir le cache cluster"
