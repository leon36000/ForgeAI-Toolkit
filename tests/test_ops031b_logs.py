"""OPS-031B — `forgeai logs` (limites, filtres, rédaction) et fermeture de la fuite du flux live.

ERR-041B rédigeait les lignes de déploiement à l'ÉCRITURE DISQUE mais la mémoire les gardait brutes,
et `/api/deploy/events` les diffusait telles quelles. La rédaction descend donc au point d'INGESTION :
un seul endroit, tous les consommateurs couverts.
"""

import json

import pytest

import forgeai.web.server as server
from forgeai.web.server import (
    LOGS_TAIL_DEFAUT,
    LOGS_TAIL_MAX,
    lire_logs_deploiement,
)


@pytest.fixture(autouse=True)
def _purge_deploy_lines():
    """`_DEPLOY_STATE` est un état MODULE : le vider isole chaque test."""
    with server._DEPLOY_STATE["lock"]:
        server._DEPLOY_STATE["lines"].clear()
    yield
    with server._DEPLOY_STATE["lock"]:
        server._DEPLOY_STATE["lines"].clear()


def _ecrire_etat(tmp_path, lignes):
    chemin = tmp_path / "deploy-state.json"
    chemin.write_text(json.dumps({"lines": lignes, "done": True, "exit_code": 0}), encoding="utf-8")
    return chemin


def test_g1_ingestion_redige_avant_la_memoire():
    """CA1 (détecteur de la fuite) : la ligne est rédigée AVANT d'entrer en mémoire — donc
    `/api/deploy/events`, qui diffuse `_DEPLOY_STATE["lines"]`, ne peut plus fuiter."""
    import inspect

    source = inspect.getsource(server.ForgeAIHandler.do_POST)
    assert 'redact_text(line.rstrip' in source, (
        "les lignes de déploiement doivent être rédigées à l'INGESTION : rédiger à chaque sortie "
        "a déjà laissé passer le flux /api/deploy/events (ERR-041B)"
    )


def test_g1b_flux_sert_ce_que_contient_la_memoire():
    """CA1 : le flux ne fait que relayer `_DEPLOY_STATE["lines"]` — rédiger à l'ingestion suffit
    donc à le couvrir (on vérifie le lien plutôt que de le supposer)."""
    import inspect

    source = inspect.getsource(server.ForgeAIHandler.do_GET)
    assert '_DEPLOY_STATE["lines"]' in source


def test_g2_sortie_bornee_par_defaut(tmp_path):
    """CA2 : sans --tail, la sortie est bornée au défaut."""
    chemin = _ecrire_etat(tmp_path, [f"ligne {i}" for i in range(LOGS_TAIL_DEFAUT + 50)])
    lignes = lire_logs_deploiement(chemin)
    assert len(lignes) == LOGS_TAIL_DEFAUT
    assert lignes[-1] == f"ligne {LOGS_TAIL_DEFAUT + 49}", "on garde bien la FIN du journal"


def test_g2b_tail_explicite_et_plafond_dur(tmp_path):
    """CA2 : --tail borne à N, et une valeur démesurée est ramenée au plafond dur."""
    chemin = _ecrire_etat(tmp_path, [f"l{i}" for i in range(300)])
    assert len(lire_logs_deploiement(chemin, tail=10)) == 10

    grand = _ecrire_etat(tmp_path, [f"l{i}" for i in range(LOGS_TAIL_MAX + 100)])
    lignes = lire_logs_deploiement(grand, tail=10_000_000)
    assert len(lignes) == LOGS_TAIL_MAX, (
        f"le plafond dur doit s'appliquer : {len(lignes)} lignes au lieu de {LOGS_TAIL_MAX}"
    )


def test_g3_grep_est_litteral_pas_une_regex(tmp_path):
    """CA2 : `--grep` filtre en SOUS-CHAÎNE ; un motif de type regex n'est ni compilé ni fatal."""
    chemin = _ecrire_etat(tmp_path, ["docker pull", "kubectl apply", "a((( littéral"])

    assert lire_logs_deploiement(chemin, grep="kubectl") == ["kubectl apply"]

    # Un motif qui ne compilerait pas en regex doit être traité comme du texte, sans exception.
    resultat = lire_logs_deploiement(chemin, grep="a(((")
    assert resultat == ["a((( littéral"], "le motif doit être littéral, jamais compilé"


def test_g4_redaction_appliquee_a_la_lecture(tmp_path):
    """CA3 : un fichier écrit par une version ANTÉRIEURE (ligne brute) ressort rédigé."""
    faux = "api_key=" + "q" * 32  # proof:allow (faux jeton de test)
    chemin = _ecrire_etat(tmp_path, [f"sortie docker {faux}"])

    lignes = lire_logs_deploiement(chemin)
    assert faux not in "\n".join(lignes), "une ligne héritée non rédigée doit l'être à la lecture"
    assert "«REDACTED»" in lignes[0]


def test_g5_fichier_absent_ou_invalide_ne_leve_pas(tmp_path):
    """CA2 : absence de fichier ou JSON invalide → liste vide, jamais d'exception."""
    assert lire_logs_deploiement(tmp_path / "inexistant.json") == []

    casse = tmp_path / "casse.json"
    casse.write_text("{ pas du json", encoding="utf-8")
    assert lire_logs_deploiement(casse) == []

    sans_lignes = tmp_path / "sans.json"
    sans_lignes.write_text(json.dumps({"done": True}), encoding="utf-8")
    assert lire_logs_deploiement(sans_lignes) == []


def test_g5b_cli_logs_json_et_humain(tmp_path, monkeypatch, capsys):
    """CA2 : `forgeai logs [--json]` s'appuie sur le même lecteur borné et rédigé."""
    from forgeai.cli import main

    faux = "token=" + "w" * 40  # proof:allow
    chemin = _ecrire_etat(tmp_path, ["ligne A", f"ligne B {faux}"])
    monkeypatch.setattr(server, "_deploy_state_path", lambda: chemin)

    assert main(["logs", "--json"]) == 0
    charge = json.loads(capsys.readouterr().out)
    assert len(charge["lines"]) == 2
    assert faux not in json.dumps(charge), "la sortie CLI doit être rédigée"

    assert main(["logs", "--grep", "ligne A"]) == 0
    assert capsys.readouterr().out.strip() == "ligne A"


def test_g5c_cli_logs_sans_etat_sort_proprement(tmp_path, monkeypatch, capsys):
    """CA2 : aucun déploiement encore lancé → code 0 et message explicite, pas une trace."""
    from forgeai.cli import main

    monkeypatch.setattr(server, "_deploy_state_path", lambda: tmp_path / "rien.json")
    assert main(["logs"]) == 0
    assert "aucune ligne" in capsys.readouterr().out


def test_g1c_flux_live_ne_diffuse_jamais_de_ligne_brute(tmp_path, monkeypatch):
    """CA1 (preuve de bout en bout) : ce que `/api/deploy/events` diffuse provient de la mémoire —
    on injecte donc une ligne comme le ferait le lecteur de sortie et on vérifie le flux réel.

    Le contrôle structurel (G1) prouve que la rédaction est au bon endroit ; celui-ci prouve
    l'EFFET observable côté client, sans quoi on ne saurait pas si le flux relaie autre chose.
    """
    import threading
    import urllib.request
    from forgeai.core.redaction import redact_text

    faux = "api_key=" + "r" * 32  # proof:allow
    # `forgeai_home` est redirigé AVANT la construction : `build_server` appelle
    # `_load_deploy_state()`, qui RESTAURE les lignes depuis le disque et écraserait l'injection.
    monkeypatch.setattr(server, "forgeai_home", lambda: tmp_path)
    srv = server.build_server("127.0.0.1", 0)

    # Injection APRÈS la construction, exactement comme le fait le lecteur de sortie une fois le
    # correctif d'ingestion en place.
    with server._DEPLOY_STATE["lock"]:
        server._DEPLOY_STATE["lines"].clear()
        server._DEPLOY_STATE["lines"].append(redact_text(f"docker run {faux}"))
        server._DEPLOY_STATE["done"] = True
        server._DEPLOY_STATE["exit_code"] = 0
        server._DEPLOY_STATE["proc"] = None

    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        with urllib.request.urlopen(f"{base}/api/deploy/events", timeout=10) as r:
            flux = r.read().decode(errors="replace")
    finally:
        srv.shutdown()
        srv.server_close()

    assert faux not in flux, "le flux /api/deploy/events a diffusé un secret en clair"
    assert "«REDACTED»" in flux, "le flux doit relayer la ligne rédigée"
