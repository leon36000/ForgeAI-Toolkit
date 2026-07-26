"""FAI-0014 (#120) — le serveur web re-lit et re-parse des fichiers de données STATIQUES
du paquet à CHAQUE requête (catalogue.json 1.15 MiB sur /api/bricks + /api/spheres,
moteurs/modèles/locales ailleurs). Baseline : ~18-20 ms/req pour re-parser le catalogue.

Spécification : ces loaders de données immuables du paquet doivent être MÉMOÏSÉS (une lecture par
process, pas par requête). Preuve par identité : deux appels renvoient le MÊME objet caché.
RED avant correctif : chaque appel re-parse → objets distincts.
"""
import forgeai.web.server as server
import pytest


@pytest.fixture(autouse=True)
def _purge_cache_materiel():
    """Le cache matériel est un état MODULE : le purger avant/après chaque test évite
    qu'un faux détecteur monkeypatché fuite vers les autres tests (pollution)."""
    server._hardware_cache_clear()
    yield
    server._hardware_cache_clear()


def test_catalogue_entries_memoise():
    # le PARSE est mémoïsé (le tuple caché est identique d'un appel à l'autre)
    assert server._catalogue_entries_cached() is server._catalogue_entries_cached(), \
        "catalogue re-parsé à chaque appel (aucun cache) — coût O(1.15 MiB)/requête"
    # mais chaque appelant reçoit une COPIE : muter la liste rendue ne corrompt PAS le cache partagé
    a = server._catalogue_entries()
    b = server._catalogue_entries()
    assert a == b and a is not b
    n = len(a)
    a.append({"id": "MUTATION-TEST"})
    assert len(server._catalogue_entries()) == n, "mutation d'un appelant a corrompu le cache"


def test_read_data_text_memoise():
    a = server._read_data_text("moteurs-inference.json")
    b = server._read_data_text("moteurs-inference.json")
    assert a is b, "fichier de données re-lu à chaque appel (aucun cache)"


def test_read_data_text_distingue_les_fichiers():
    """Le cache reste correct par NOM de fichier (pas de collision entre ressources)."""
    a = server._read_data_text("moteurs-inference.json")
    b = server._read_data_text("modeles-locaux.json")
    assert a != b


# ── OPT-001 (OBS-A060-1 / A061) — la DÉTECTION MATÉRIELLE est re-sondée à chaque requête ──
# `hardware_json()` lance des SOUS-PROCESSUS (lscpu/lspci/nvidia-smi/df) à CHAQUE appel.
# Mesuré sur machine rapide : /api/summary = 940→1583 ms (croissant), vs /api/stacks = 1 ms.
# Sur runner CI chargé, le timeout client de 10 s est dépassé -> échecs CI systématiques.
# Spécification : mémoïsation à TTL (le matériel ne change pas d'une requête à l'autre),
# avec invalidation explicite possible. RED avant correctif : chaque appel re-sonde.
import time as _time


def test_hardware_json_memoise_avec_ttl(monkeypatch):
    server._hardware_cache_clear()
    appels = {"n": 0}

    class _FauxProfil:
        def to_json(self):
            return '{"cpu_model":"faux"}'

    class _FauxDetecteur:
        def __init__(self, *a, **k):
            appels["n"] += 1          # compte les SONDES réelles (construction+full_report)

        def full_report(self):
            return _FauxProfil()

    monkeypatch.setattr(server, "HardwareDetector", _FauxDetecteur)
    a = server.hardware_json()
    b = server.hardware_json()
    c = server.hardware_json()
    assert a == b == c
    assert appels["n"] == 1, f"détection relancée {appels['n']}x (aucun cache) — 1 attendu"


def test_hardware_cache_expire_apres_ttl(monkeypatch):
    server._hardware_cache_clear()
    appels = {"n": 0}

    class _FauxProfil:
        def to_json(self):
            return '{"cpu_model":"faux"}'

    class _FauxDetecteur:
        def __init__(self, *a, **k):
            appels["n"] += 1

        def full_report(self):
            return _FauxProfil()

    monkeypatch.setattr(server, "HardwareDetector", _FauxDetecteur)
    faux_temps = {"t": 1000.0}
    monkeypatch.setattr(server.time, "monotonic", lambda: faux_temps["t"])
    server.hardware_json()
    faux_temps["t"] += server._HARDWARE_TTL_S + 1      # au-delà du TTL
    server.hardware_json()
    assert appels["n"] == 2, "le cache n'expire jamais (matériel jamais re-sondé)"


def test_hardware_cache_clear_force_une_nouvelle_sonde(monkeypatch):
    server._hardware_cache_clear()
    appels = {"n": 0}

    class _FauxProfil:
        def to_json(self):
            return '{"cpu_model":"faux"}'

    class _FauxDetecteur:
        def __init__(self, *a, **k):
            appels["n"] += 1

        def full_report(self):
            return _FauxProfil()

    monkeypatch.setattr(server, "HardwareDetector", _FauxDetecteur)
    server.hardware_json()
    server._hardware_cache_clear()      # invalidation EXPLICITE
    server.hardware_json()
    assert appels["n"] == 2, "l'invalidation explicite ne force pas une nouvelle sonde"


def test_available_backends_memoise(monkeypatch):
    """OPT-001 (2e chemin chaud) : `_available_backends` sonde docker/k3s à CHAQUE appel
    (mesuré 801 ms) et relance en plus une détection matérielle. Doit être mémoïsé au même TTL."""
    server._hardware_cache_clear()
    appels = {"n": 0}

    def _faux_run_checks(*a, **k):
        appels["n"] += 1
        return {}

    monkeypatch.setattr(server, "run_checks", _faux_run_checks)
    monkeypatch.setattr(server, "available_backends", lambda checks: ["compose"])
    a = server._available_backends()
    b = server._available_backends()
    assert a == b == ["compose"]
    assert appels["n"] == 1, f"sondes backends relancées {appels['n']}x (aucun cache) — 1 attendu"


def test_backends_et_hardware_sans_interblocage(monkeypatch):
    """Garde anti-régression : `_available_backends` réutilise `_hardware_report()` alors qu'il
    détient déjà le verrou du cache. Avec un `Lock` non réentrant -> INTERBLOCAGE (prouvé).
    Le verrou doit être RÉENTRANT (RLock). Le test échoue par TIMEOUT si la régression revient."""
    import threading as _th
    server._hardware_cache_clear()
    # Le faux run_checks DOIT appeler full_report() sur le détecteur : c'est CE chemin qui reprend
    # le verrou (réentrance). Sans cet appel, le test réussirait même avec un Lock simple
    # (faux positif — constaté en revue et corrigé ici).
    def _faux_run_checks(runner, detector, http_ok):
        detector.full_report()   # -> _hardware_report() alors que le verrou est DÉJÀ tenu
        return {}

    monkeypatch.setattr(server, "run_checks", _faux_run_checks)
    monkeypatch.setattr(server, "available_backends", lambda checks: ["compose"])

    fini = _th.Event()

    def _appel():
        server._available_backends()
        fini.set()

    t = _th.Thread(target=_appel, daemon=True)
    t.start()
    assert fini.wait(timeout=10), "INTERBLOCAGE : _available_backends bloqué sur le verrou du cache"


# ── OPT-002 — les sondes du CHEMIN WEB doivent être BORNÉES court ─────────────
# `SubprocessRunner` a un timeout par défaut de 20 s/commande (core/runner.py). Le PREMIER appel
# (non caché) de /api/summary enchaîne lscpu, lspci, nvidia-smi, df, docker, kubectl : une seule
# sonde lente dépasse le budget d'une requête HTTP (test client à 10 s) -> échec CI systématique.
# Spécification : les sondes déclenchées par une REQUÊTE HTTP utilisent un timeout court et borné.
def test_sondes_du_chemin_web_ont_un_timeout_court():
    """Constante dédiée, nettement inférieure au défaut 20 s du runner."""
    from forgeai.core.runner import SubprocessRunner
    assert hasattr(server, "_PROBE_TIMEOUT_S"), "aucune borne dédiée aux sondes du chemin web"
    assert 0 < server._PROBE_TIMEOUT_S <= 5.0, server._PROBE_TIMEOUT_S
    assert server._PROBE_TIMEOUT_S < SubprocessRunner().timeout_s


def test_hardware_report_utilise_un_runner_borne(monkeypatch):
    """La détection matérielle du serveur borne son runner (pas le défaut 20 s)."""
    server._hardware_cache_clear()
    vus = {}

    class _FauxDetecteur:
        def __init__(self, runner, *a, **k):
            vus["timeout"] = getattr(runner, "timeout_s", None)

        def full_report(self):
            class _P:
                def to_json(self_inner):
                    return "{}"
            return _P()

    monkeypatch.setattr(server, "HardwareDetector", _FauxDetecteur)
    server._hardware_report()
    assert vus["timeout"] == server._PROBE_TIMEOUT_S, vus


def test_available_backends_utilise_un_runner_borne(monkeypatch):
    """Les sondes docker/k3s du serveur bornent aussi leur runner."""
    server._hardware_cache_clear()
    vus = {}

    def _faux_run_checks(runner, detector, http_ok):
        vus["timeout"] = getattr(runner, "timeout_s", None)
        return {}

    monkeypatch.setattr(server, "run_checks", _faux_run_checks)
    monkeypatch.setattr(server, "available_backends", lambda checks: ["compose"])
    server._available_backends()
    assert vus["timeout"] == server._PROBE_TIMEOUT_S, vus


def test_cluster_status_utilise_un_runner_borne(monkeypatch):
    """3e sonde du chemin web (relevé en revue : elle n'était pas testée) — cluster_status
    doit aussi recevoir un runner borné, pas le défaut 20 s."""
    server._hardware_cache_clear()
    vus = {}

    def _faux_cluster_status(runner):
        vus["timeout"] = getattr(runner, "timeout_s", None)
        return [{"name": "node-a"}]

    monkeypatch.setattr(server, "cluster_status", _faux_cluster_status)
    monkeypatch.setattr(server, "_hardware_report", lambda: type("P", (), {})())
    monkeypatch.setattr(server, "_available_backends", lambda: ["compose"])
    server._summary_payload("agentique")
    assert vus["timeout"] == server._PROBE_TIMEOUT_S, vus
