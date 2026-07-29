"""Corrective (finding Sentinelle) : le health-check K3s du wizard dérive les chemins de
probe DU PLAN, jamais d'un dict codé en dur — plus de KeyError sur un service inconnu."""
from forgeai.core.models import DeploymentPlan, ServiceSpec, RenderTarget
import yaml
from forgeai.cli import _k3s_probe_paths
import json

class _FauxRun:
    """Faux retour de subprocess.run : _etats_docker lit .returncode puis .stdout."""

    def __init__(self, returncode, stdout=""):
        self.returncode = returncode
        self.stdout = stdout


from urllib.error import URLError
from forgeai.deploy import compose as compose_mod
from forgeai.deploy.compose import DeployError
from forgeai.renderers import compose as compose_renderer
from forgeai.renderers import k3s as k3s_renderer


def _plan(services):
    return DeploymentPlan(plan_id="t", profile="minimal-cpu", target=RenderTarget.COMPOSE,
                          services=tuple(services), model="m", embed_model="e")


def test_probe_paths_derive_du_plan_sans_keyerror():
    services = [
        ServiceSpec("ollama", "img", 21434, 11434,
                    healthcheck_url="http://127.0.0.1:21434/api/tags"),
        ServiceSpec("vector-store", "img", 26333, 6333,
                    healthcheck_url="http://127.0.0.1:26333/readyz"),
        # service supplémentaire SANS healthcheck : plantait `probes[name]` (KeyError) avant
        ServiceSpec("orchestrator", "img", 28080, 8080),
    ]
    paths = _k3s_probe_paths(_plan(services))
    assert paths == {"ollama": "/api/tags", "vector-store": "/readyz"}
    assert "orchestrator" not in paths


def test_probe_paths_service_avec_healthcheck_inclus():
    services = [ServiceSpec("brique-x", "img", 29000, 9000,
                            healthcheck_url="http://127.0.0.1:29000/health")]
    assert _k3s_probe_paths(_plan(services)) == {"brique-x": "/health"}


def test_probe_paths_filtre_services_hors_rag_ports():
    """Garde défensive : un service avec healthcheck mais absent de rag_ports est filtré,
    donc l'accès rag_ports[name] dans la boucle ne peut jamais lever de KeyError."""
    services = [
        ServiceSpec("ollama", "img", 21434, 11434,
                    healthcheck_url="http://127.0.0.1:21434/api/tags"),
        ServiceSpec("absent", "img", 29999, 9999,
                    healthcheck_url="http://127.0.0.1:29999/health"),
    ]
    paths = _k3s_probe_paths(_plan(services), rag_ports={"ollama": 30001})
    assert paths == {"ollama": "/api/tags"}
    assert "absent" not in paths


# ---------------------------------------------------------------------------
# HEALTH-028B / FAI-U-028 — contrat de santé mappé vers Compose et K3s (ADR HEALTH-028A).
# Défaut central reproduit : `all()` sur une collection VIDE renvoie True, donc un plan
# sans aucun service sondé était déclaré healthy IMMÉDIATEMENT, sans preuve de santé.
# ---------------------------------------------------------------------------
import pytest

from forgeai.core.models import HealthState, ProbeType, ServiceSpec


def _plan_sante(services) -> DeploymentPlan:
    """Plan portant exactement les services fournis, pour les cas de santé ciblés."""
    return DeploymentPlan(plan_id="health028b", profile="minimal-cpu",
                          target=RenderTarget.K3S, services=tuple(services),
                          model="m", embed_model="e")


def test_aucun_service_sonde_donne_unknown_jamais_ready():
    """Règle ANTI-VACUITÉ de l'ADR §2.3, non contournable : `all(...)` sur une collection vide
    renvoie True. Un déploiement de zéro service sondé doit être UNKNOWN, JAMAIS READY —
    sinon le déploiement enchaîne sur des services dont rien ne prouve qu'ils fonctionnent."""
    from forgeai.deploy.compose import agreger_verdicts
    assert agreger_verdicts({}) is HealthState.UNKNOWN
    assert agreger_verdicts({}) is not HealthState.FUNCTIONALLY_READY


def test_service_requis_sans_sonde_donne_failed():
    """ADR §2.3 : une liste de probes vide s'évalue en FAILED pour un service
    `health_required=True`. Exiger la santé puis n'en avoir aucune preuve est une violation
    de contrat, pas une absence d'information."""
    from forgeai.deploy.compose import evaluer_service
    svc = ServiceSpec(name="db", image="postgres:15", host_port=5432, container_port=5432,
                      health_required=True)
    assert evaluer_service(svc, sonde_reussie=None) is HealthState.FAILED


def test_port_ouvert_ne_vaut_pas_pret_si_une_sonde_fonctionnelle_existe():
    """Critère 1 — un port TCP ouvert prouve que le transport répond, pas que la base accepte
    des requêtes. Les deux états doivent être DISTINCTS."""
    from forgeai.deploy.compose import evaluer_service
    svc = ServiceSpec(name="postgres", image="postgres:15", host_port=5432, container_port=5432,
                      probe_type=ProbeType.EXEC, probe_target=("pg_isready", "-U", "forgeai"))
    assert evaluer_service(svc, sonde_reussie=False, transport_ouvert=True) is HealthState.TRANSPORT_READY
    assert evaluer_service(svc, sonde_reussie=True) is HealthState.FUNCTIONALLY_READY


def test_k3s_emet_trois_probes_aux_roles_distincts():
    """Critère 2 — startup, readiness et liveness ont des rôles distincts : startup protège un
    démarrage lent, readiness retire du service, liveness redémarre. Les confondre fait
    redémarrer en boucle un service qui démarre simplement lentement."""
    import yaml
    from forgeai.renderers.k3s import render_k3s
    svc = ServiceSpec(name="api", image="api:1", host_port=8080, container_port=8080,
                      probe_type=ProbeType.HTTP, probe_target="/healthz", health_required=True)
    out = render_k3s(_plan_sante([svc]))
    conteneur = next(d for d in yaml.safe_load_all(out)
                     if d and d.get("kind") == "Deployment")["spec"]["template"]["spec"]["containers"][0]
    for sonde in ("startupProbe", "readinessProbe", "livenessProbe"):
        assert sonde in conteneur, f"{sonde} manquante"
    assert conteneur["startupProbe"]["failureThreshold"] > conteneur["livenessProbe"]["failureThreshold"], \
        "startupProbe doit tolérer plus d'échecs que livenessProbe (démarrage lent ≠ panne)"


def test_compose_emet_un_healthcheck_fonctionnel():
    """Critère 1 (Compose) — une sonde EXEC doit produire un `healthcheck.test` exécutant la
    commande fonctionnelle, pas un simple test de port."""
    from forgeai.renderers.compose import render_compose
    svc = ServiceSpec(name="postgres", image="postgres:15", host_port=5432, container_port=5432,
                      probe_type=ProbeType.EXEC, probe_target=("pg_isready", "-U", "forgeai"),
                      health_required=True)
    out = render_compose(_plan_sante([svc]))
    assert "healthcheck:" in out and "pg_isready" in out


def test_wait_healthy_refuse_l_absence_de_contrat_requis():
    """Critère 3 — `wait_healthy` doit REFUSER quand un service `health_required=True` n'a aucun
    contrat de sonde exploitable, au lieu de conclure au succès par défaut."""
    from forgeai.deploy.compose import wait_healthy, HealthContractError
    svc = ServiceSpec(name="db", image="postgres:15", host_port=5432, container_port=5432,
                      health_required=True)   # aucun probe_type, aucun healthcheck_url
    with pytest.raises(HealthContractError, match="ERR_HEALTH"):
        wait_healthy(_plan_sante([svc]), timeout_s=1.0)


# --- Objections de la revue scellée (REJECT 3/3, sceau b527901d005d) -------------------
# Les trois vendors convergent : `evaluer_service` et `agreger_verdicts` sont testées mais
# `wait_healthy` NE LES APPELLE PAS — il reconstruit sa logique à la main. Mes tests
# validaient donc des fonctions que le chemin de production n'emprunte pas : exactement le
# piège du test-sur-chemin-inventé déjà rencontré sur RAG-005.
def test_probe_type_none_est_un_contrat_absent():
    """`ProbeType.NONE` n'est PAS `None` : `svc.probe_type is not None` l'accepte comme sonde
    valide. Un service exigeant la santé tout en déclarant explicitement « aucune sonde » est
    une violation de contrat, pas un service sondé."""
    from forgeai.deploy.compose import wait_healthy, HealthContractError
    svc = ServiceSpec(name="db", image="postgres:15", host_port=5432, container_port=5432,
                      health_required=True, probe_type=ProbeType.NONE)
    with pytest.raises(HealthContractError, match="ERR_HEALTH_CONTRAT_ABSENT"):
        wait_healthy(_plan_sante([svc]), timeout_s=1.0)


def test_service_exec_requis_nest_pas_ignore_du_verdict():
    """Défaut CRITIQUE : `wait_healthy` ne sonde que les services ayant `healthcheck_url`.
    Un postgres `health_required=True` avec une sonde EXEC passait le contrôle de contrat
    PUIS était absent des verdicts — le déploiement se déclarait prêt en l'ignorant."""
    from forgeai.deploy.compose import wait_healthy
    pg = ServiceSpec(name="postgres", image="postgres:15", host_port=5432, container_port=5432,
                     health_required=True, probe_type=ProbeType.EXEC,
                     probe_target=("pg_isready", "-U", "forgeai"))
    web = ServiceSpec(name="web", image="web:1", host_port=8080, container_port=8080,
                      healthcheck_url="http://127.0.0.1:8080/health")
    from forgeai.deploy.compose import DeployError
    with pytest.raises((DeployError, Exception)) as exc:
        wait_healthy(_plan_sante([pg, web]), timeout_s=1.0, probe=lambda url: True)
    assert "postgres" in str(exc.value), \
        f"un service requis non sondable doit apparaître dans l'échec : {exc.value}"


def test_wait_healthy_utilise_bien_agreger_verdicts(monkeypatch):
    """Défaut de cohérence : `agreger_verdicts` porte la règle anti-vacuité, mais si
    `wait_healthy` ne l'appelle pas, cette règle ne protège RIEN en production. On vérifie le
    branchement réel, pas l'existence de la fonction."""
    from forgeai.deploy import compose as mod
    appels = []
    vrai = mod.agreger_verdicts
    monkeypatch.setattr(mod, "agreger_verdicts", lambda v: (appels.append(v), vrai(v))[1])
    svc = ServiceSpec(name="web", image="web:1", host_port=8080, container_port=8080,
                      healthcheck_url="http://127.0.0.1:8080/health")
    mod.wait_healthy(_plan_sante([svc]), timeout_s=2.0, probe=lambda url: True)
    assert appels, "wait_healthy doit passer par agreger_verdicts, pas reconstruire sa logique"


def test_arguments_exec_sont_echappes():
    """Objection de Gemini : un argument contenant un guillemet double casse le tableau YAML
    émis. Un contenu de configuration ne doit jamais pouvoir corrompre le manifeste."""
    from forgeai.renderers.compose import render_compose
    svc = ServiceSpec(name="x", image="x:1", host_port=1, container_port=1,
                      probe_type=ProbeType.EXEC, probe_target=('echo', 'a"b'))
    import yaml
    rendu = render_compose(_plan_sante([svc]))
    yaml.safe_load(rendu)   # doit rester parsable


def test_arguments_exec_k3s_sont_echappes():
    """Objection de Gemini (tour 2) : `compose.py` échappe via `json.dumps`, `k3s.py` non.
    Mesuré : `a: b` devient un dictionnaire, ` #c` devient None, `*ref` corrompt le document.
    La sonde exécuterait alors autre chose que demandé, SANS erreur — une altération
    silencieuse est pire qu'un échec bruyant."""
    import yaml
    from forgeai.renderers.k3s import render_k3s
    for arg in ("a: b", "[x]", "*ref", " #c", "{a}"):
        svc = ServiceSpec(name="x", image="x:1", host_port=1, container_port=1,
                          probe_type=ProbeType.EXEC, probe_target=("echo", arg))
        docs = list(yaml.safe_load_all(render_k3s(_plan_sante([svc]))))
        dep = next(d for d in docs if d and d.get("kind") == "Deployment")
        cmd = dep["spec"]["template"]["spec"]["containers"][0]["livenessProbe"]["exec"]["command"]
        assert cmd == ["echo", arg], f"argument {arg!r} altéré en {cmd!r}"


def test_sonde_interne_est_lue_depuis_docker_pas_bloquante(monkeypatch):
    """Objection CRITIQUE de Gemini (tour 3), REPRODUITE : tout plan contenant un service à
    sonde INTERNE (EXEC/TCP, ou HTTP sans `healthcheck_url`) échouait systématiquement par
    timeout — le produit devenait inutilisable dès qu'un postgres ou un redis était présent.

    La sonde interne est exécutée par l'orchestrateur, pas depuis l'hôte : sa preuve existe,
    mais dans Docker. `wait_healthy` doit la LIRE (`docker compose ps`) plutôt que de conclure
    à l'aveugle. C'est la seule preuve fonctionnelle disponible pour ces services."""
    from forgeai.deploy import compose as mod
    pg = ServiceSpec(name="postgres", image="postgres:15", host_port=5432, container_port=5432,
                     probe_type=ProbeType.EXEC, probe_target=("pg_isready",),
                     health_required=True)
    monkeypatch.setattr(mod, "_etats_docker", lambda plan: {"postgres": "healthy"})
    res = mod.wait_healthy(_plan_sante([pg]), timeout_s=3.0, probe=lambda url: True)
    assert res == {"postgres": "healthy"}


def test_sonde_interne_non_saine_est_rapportee(monkeypatch):
    """Contrôle négatif : Docker rapporte `unhealthy` -> le déploiement échoue en nommant le
    service. Lire la preuve ne doit pas revenir à l'accepter aveuglément."""
    from forgeai.deploy import compose as mod
    pg = ServiceSpec(name="postgres", image="postgres:15", host_port=5432, container_port=5432,
                     probe_type=ProbeType.EXEC, probe_target=("pg_isready",),
                     health_required=True)
    monkeypatch.setattr(mod, "_etats_docker", lambda plan: {"postgres": "unhealthy"})
    with pytest.raises(mod.DeployError, match="postgres"):
        mod.wait_healthy(_plan_sante([pg]), timeout_s=2.0, probe=lambda url: True)


def test_chemin_http_k3s_est_echappe():
    """Objection majeure de Gemini : `probe_target` HTTP n'était pas échappé dans le manifeste
    K3s — même classe de défaut que les arguments EXEC, sur le chemin."""
    import yaml
    from forgeai.renderers.k3s import render_k3s
    svc = ServiceSpec(name="x", image="x:1", host_port=1, container_port=1,
                      probe_type=ProbeType.HTTP, probe_target="/a: b#c")
    docs = list(yaml.safe_load_all(render_k3s(_plan_sante([svc]))))
    dep = next(d for d in docs if d and d.get("kind") == "Deployment")
    chemin = dep["spec"]["template"]["spec"]["containers"][0]["livenessProbe"]["httpGet"]["path"]
    assert chemin == "/a: b#c", f"chemin altéré : {chemin!r}"


def test_argument_exec_vide_est_legitime():
    """Objection mineure de Gemini : `--password ""` est un argv valide. Rejeter une chaîne
    vide interdit un usage réel ; seul un tuple VIDE est un contrat absent."""
    ServiceSpec(name="x", image="x:1", host_port=1, container_port=1,
                probe_type=ProbeType.EXEC, probe_target=("psql", "--password", ""))
    with pytest.raises(ValueError, match="ERR_HEALTH_CIBLE_EXEC_INVALIDE"):
        ServiceSpec(name="y", image="y:1", host_port=2, container_port=2,
                    probe_type=ProbeType.EXEC, probe_target=())


def test_chemin_derive_de_healthcheck_url_est_echappe():
    """Objection de DeepSeek (tour 4) : j'avais échappé le chemin de `ProbeType.HTTP` mais PAS
    celui dérivé de `healthcheck_url`. TROISIÈME occurrence du même motif sur ce package —
    corriger une branche et oublier sa jumelle. Chaque chemin atteignant le YAML doit être
    échappé, sans exception."""
    import yaml
    from forgeai.renderers.k3s import render_k3s
    # `#` est un FRAGMENT d'URL, retiré à juste titre par urlsplit (il n'est jamais envoyé au
    # serveur) : le cas de test utilise donc des caractères structurants YAML qui, eux, font
    # bien partie du chemin.
    svc = ServiceSpec(name="x", image="x:1", host_port=1, container_port=1,
                      healthcheck_url="http://127.0.0.1:1/a: b")
    docs = list(yaml.safe_load_all(render_k3s(_plan_sante([svc]))))
    dep = next(d for d in docs if d and d.get("kind") == "Deployment")
    chemin = dep["spec"]["template"]["spec"]["containers"][0]["livenessProbe"]["httpGet"]["path"]
    assert chemin == "/a: b", f"chemin dérivé altéré : {chemin!r}"


# Imports supplémentaires nécessaires (à ajouter en tête de fichier, fusionner avec les
# imports existants ; ne pas dupliquer) :
#   import json
#   import yaml
#   from urllib.error import URLError
#   from forgeai.core.models import ProbeType, ServiceSpec, HealthState
#   from forgeai.deploy import compose as compose_mod
#   from forgeai.renderers import compose as compose_renderer
#   from forgeai.renderers import k3s as k3s_renderer
#
# Tests à coller à la fin de tests/test_wizard_health.py :


# ---------------------------------------------------------------------------
# HEALTH-028B — bloc 1 : _etats_docker (lignes 129-148)
# ---------------------------------------------------------------------------

def test_etats_docker_parse_tableau_json(monkeypatch):
    """stdout = liste JSON [{"Service":..., "Health":...}, ...] -> dict correct."""
    def fake_run(*a, **k):
        return _FauxRun(
            returncode=0,
            stdout=json.dumps([
                {"Service": "redis", "Health": "healthy"},
                {"Service": "postgres", "Health": "unhealthy"},
            ]),
        )
    monkeypatch.setattr(compose_mod.subprocess, "run", fake_run)
    plan = type("P", (), {"plan_id": "p1"})()
    result = compose_mod._etats_docker(plan)
    assert result == {"redis": "healthy", "postgres": "unhealthy"}


def test_etats_docker_parse_json_lines_avec_lignes_vides(monkeypatch):
    """stdout = JSON-lines (un objet par ligne, lignes vides intercalées) -> dict correct."""
    def fake_run(*a, **k):
        return _FauxRun(
            returncode=0,
            stdout=(
                '{"Service":"redis","Health":"healthy"}\n'
                '\n'
                '{"Service":"qdrant","State":"running"}\n'
                '   \n'
            ),
        )
    monkeypatch.setattr(compose_mod.subprocess, "run", fake_run)
    plan = type("P", (), {"plan_id": "p1"})()
    result = compose_mod._etats_docker(plan)
    assert result == {"redis": "healthy", "qdrant": "running"}


def test_etats_docker_utilise_cle_name_si_service_absent(monkeypatch):
    """Objet sans 'Service' mais avec 'Name' -> la clé 'Name' est utilisée."""
    def fake_run(*a, **k):
        return _FauxRun(
            returncode=0,
            stdout=json.dumps({"Name": "immudb", "Health": "healthy"}),
        )
    monkeypatch.setattr(compose_mod.subprocess, "run", fake_run)
    plan = type("P", (), {"plan_id": "p1"})()
    result = compose_mod._etats_docker(plan)
    assert result == {"immudb": "healthy"}


def test_etats_docker_utilise_state_si_health_absent(monkeypatch):
    """Objet sans 'Health' mais avec 'State' -> la valeur 'State' est utilisée."""
    def fake_run(*a, **k):
        return _FauxRun(
            returncode=0,
            stdout=json.dumps({"Service": "redis", "State": "exited"}),
        )
    monkeypatch.setattr(compose_mod.subprocess, "run", fake_run)
    plan = type("P", (), {"plan_id": "p1"})()
    result = compose_mod._etats_docker(plan)
    assert result == {"redis": "exited"}


def test_etats_docker_stdout_illisible_retourne_vide_sans_lever(monkeypatch):
    """JSON tronqué -> {} SANS lever (appel direct, pas de pytest.raises)."""
    def fake_run(*a, **k):
        class R:
            stdout = '{"Service":"redis","Health":'  # JSON cassé
            returncode = 0
        return R()
    monkeypatch.setattr(compose_mod.subprocess, "run", fake_run)
    plan = type("P", (), {"plan_id": "p1"})()
    result = compose_mod._etats_docker(plan)
    assert result == {}


def test_etats_docker_subprocess_qui_leve_retourne_vide_sans_lever(monkeypatch):
    """La commande lève -> {} SANS lever (appel direct)."""
    def fake_run(*a, **k):
        raise RuntimeError("docker not available")
    monkeypatch.setattr(compose_mod.subprocess, "run", fake_run)
    plan = type("P", (), {"plan_id": "p1"})()
    result = compose_mod._etats_docker(plan)
    assert result == {}


# ---------------------------------------------------------------------------
# HEALTH-028B — bloc 2 : _sonde_http (lignes 174-178)
# ---------------------------------------------------------------------------





# ---------------------------------------------------------------------------
# HEALTH-028B — bloc 3 : agreger_verdicts + evaluer_service
# ---------------------------------------------------------------------------

def test_agreger_verdicts_unknown_present_sans_failed():
    """UN verdict UNKNOWN dans la liste (sans FAILED) -> agrégat UNKNOWN."""
    verdicts = {
        "redis": HealthState.TRANSPORT_READY,
        "postgres": HealthState.UNKNOWN,
    }
    assert compose_mod.agreger_verdicts(verdicts) == HealthState.UNKNOWN


def test_agreger_verdicts_tous_transport_ready():
    """Tous verdicts TRANSPORT_READY -> agrégat TRANSPORT_READY."""
    verdicts = {
        "a": HealthState.TRANSPORT_READY,
        "b": HealthState.TRANSPORT_READY,
    }
    assert compose_mod.agreger_verdicts(verdicts) == HealthState.TRANSPORT_READY


def test_evaluer_service_retourne_unknown_quand_health_required_faux():
    """sonde_reussie=None + health_required=False -> UNKNOWN."""
    svc = ServiceSpec(
        host_port=18080, container_port=8080, name="svc",
        image="redis:7",
        health_required=False,
    )
    assert compose_mod.evaluer_service(svc, sonde_reussie=None, transport_ouvert=False) \
        == HealthState.UNKNOWN


def test_evaluer_service_retourne_functionally_ready_quand_sonde_ok():
    """sonde_reussie=True -> FUNCTIONALLY_READY (sanity check, documente le contrat)."""
    svc = ServiceSpec(host_port=18080, container_port=8080, name="svc", image="redis:7", health_required=True)
    assert compose_mod.evaluer_service(svc, sonde_reussie=True, transport_ouvert=False) \
        == HealthState.FUNCTIONALLY_READY


# ---------------------------------------------------------------------------
# HEALTH-028B — bloc 4 : wait_healthy — branches continue (216) et probeable sans
# sonde exécutable (235-236)
# ---------------------------------------------------------------------------

class _FakePlan:
    """Plan minimal consommé par wait_healthy."""
    def __init__(self, services):
        self.id = "p1"
        self.services = services


def test_wait_healthy_service_non_requis_non_sondable_est_ignore(monkeypatch):
    """Ligne 216 : service NI requis NI sondable -> continue, n'apparaît pas dans le verdict."""
    # Service non requis, sans healthcheck_url, probe_type=None -> ignoré.
    svc = ServiceSpec(host_port=18080, container_port=8080, name="decoy", image="alpine:3", health_required=False)
    plan = _FakePlan([svc])

    # On fige la boucle via un probe qui lève toujours après la 1re itération.
    import time as _time
    real_monotonic = _time.monotonic
    calls = {"n": 0}

    def fake_monotonic():
        calls["n"] += 1
        # Après la première lecture, on saute très loin après la deadline pour
        # forcer la sortie par timeout — mais que le service ait été ignoré.
        if calls["n"] == 1:
            return real_monotonic()
        return real_monotonic() + 10**6

    monkeypatch.setattr(compose_mod.time, "monotonic", fake_monotonic)
    monkeypatch.setattr(compose_mod, "_etats_docker", lambda p: {})

    with pytest.raises(compose_mod.DeployError):
        compose_mod.wait_healthy(plan, timeout_s=0.001, probe=lambda u: True)


def test_wait_healthy_service_probeable_sans_sonde_executable_declenche_contrat(monkeypatch):
    """Lignes 235-236 : service probeable SANS healthcheck_url NI probe_type exécutable
    déclenche HealthContractError."""
    # Service requis, avec un probe_type mais sans healthcheck_url, et probe_type=None
    # → la condition `exploitable` est fausse → contrat absent.
    svc = ServiceSpec(
        host_port=18080, container_port=8080, name="needs-health",
        image="redis:7",
        health_required=True,
        healthcheck_url=None,
    )
    # Forcer probe_type à None pour être dans la branche "ni url ni type exécutable".
    object.__setattr__(svc, "probe_type", None)
    plan = _FakePlan([svc])

    monkeypatch.setattr(compose_mod, "_etats_docker", lambda p: {})

    with pytest.raises(compose_mod.HealthContractError) as exc_info:
        compose_mod.wait_healthy(plan, timeout_s=1.0, probe=lambda u: True)
    assert "needs-health" in str(exc_info.value)


# ---------------------------------------------------------------------------
# HEALTH-028B — bloc 5 : src/forgeai/renderers/compose.py (37, 38, 41)
# ---------------------------------------------------------------------------

def test_renderer_compose_probe_http_genere_test_curl_echappe():
    """probe_type=HTTP -> test: ["CMD","curl","-fsS","http://127.0.0.1:<port><path>"]
    (forme échappée par json.dumps — vérification via _healthcheck_lines)."""
    svc = ServiceSpec(
        host_port=18080, name="svc",
        image="nginx:1",
        container_port=8080,
        probe_type=ProbeType.HTTP,
        probe_target="/health",
    )
    lines = compose_renderer._healthcheck_lines(svc)
    # Le renderer compose émet ces lignes par gabarit indenté. On extrait la ligne
    # 'test:' et on la compare, forme échappée json.dumps.
    test_lines = [l for l in lines if l.strip().startswith("test:")]
    assert len(test_lines) == 1, f"Une seule ligne 'test:' attendue, obtenu: {test_lines!r}"
    expected_test = json.dumps(["CMD", "curl", "-fsS", "http://127.0.0.1:8080/health"], ensure_ascii=False)
    assert test_lines[0].strip() == f"test: {expected_test}"


def test_renderer_compose_probe_tcp_genere_test_nc():
    """probe_type=TCP -> test: ["CMD","nc","-z","127.0.0.1","<port>"] (forme échappée)."""
    svc = ServiceSpec(
        host_port=18080, name="svc",
        image="redis:7",
        container_port=6379,
        probe_type=ProbeType.TCP,
        probe_target="ignored-for-tcp",
    )
    lines = compose_renderer._healthcheck_lines(svc)
    test_lines = [l for l in lines if l.strip().startswith("test:")]
    assert len(test_lines) == 1, f"Une seule ligne 'test:' attendue, obtenu: {test_lines!r}"
    expected_test = json.dumps(["CMD", "nc", "-z", "127.0.0.1", "6379"], ensure_ascii=False)
    assert test_lines[0].strip() == f"test: {expected_test}"


# ---------------------------------------------------------------------------
# HEALTH-028B — bloc 6 : src/forgeai/renderers/k3s.py (263, 295, 296)
# ---------------------------------------------------------------------------

def test_renderer_k3s_probes_block_vide_pour_probe_type_none():
    """probe_type == ProbeType.NONE -> _probes_block retourne la chaîne vide."""
    svc = ServiceSpec(host_port=18080, container_port=8080, name="svc", image="nginx:1", probe_type=ProbeType.NONE)
    assert k3s_renderer._probes_block(svc) == ""




# ---------------------------------------------------------------------------
# HEALTH-028B — bloc 7 : src/forgeai/core/models.py — 6 codes ERR_HEALTH_*
# ---------------------------------------------------------------------------

def test_models_health_timeout_s_invalide_leve_value_error():
    """ERR_HEALTH_DUREE_INVALIDE sur health_timeout_s <= 0."""
    with pytest.raises(ValueError, match="ERR_HEALTH_DUREE_INVALIDE"):
        ServiceSpec(host_port=18080, container_port=8080, name="svc", image="redis:7", health_timeout_s=0)


def test_models_health_interval_s_invalide_leve_value_error():
    """ERR_HEALTH_DUREE_INVALIDE sur health_interval_s <= 0."""
    with pytest.raises(ValueError, match="ERR_HEALTH_DUREE_INVALIDE"):
        ServiceSpec(host_port=18080, container_port=8080, name="svc", image="redis:7", health_interval_s=0)


def test_models_health_retries_invalide_leve_value_error():
    """ERR_HEALTH_RETRIES_INVALIDE sur health_retries <= 0."""
    with pytest.raises(ValueError, match="ERR_HEALTH_RETRIES_INVALIDE"):
        ServiceSpec(host_port=18080, container_port=8080, name="svc", image="redis:7", health_retries=0)


def test_models_http_success_codes_vide_leve_value_error():
    """ERR_HEALTH_CODE_INVALIDE quand http_success_codes est vide."""
    with pytest.raises(ValueError, match="ERR_HEALTH_CODE_INVALIDE"):
        ServiceSpec(host_port=18080, container_port=8080, name="svc", image="redis:7", http_success_codes=())


def test_models_http_success_code_hors_plage_leve_value_error():
    """ERR_HEALTH_CODE_INVALIDE quand un code est hors [100, 599]."""
    with pytest.raises(ValueError, match="ERR_HEALTH_CODE_INVALIDE"):
        ServiceSpec(host_port=18080, container_port=8080, name="svc", image="redis:7", http_success_codes=(200, 700))


def test_models_probe_target_exec_vide_leve_value_error():
    """ERR_HEALTH_CIBLE_EXEC_INVALIDE : probe_type=EXEC avec probe_target=tuple vide."""
    with pytest.raises(ValueError, match="ERR_HEALTH_CIBLE_EXEC_INVALIDE"):
        ServiceSpec(
            host_port=18080, container_port=8080, name="svc",
            image="redis:7",
            probe_type=ProbeType.EXEC,
            probe_target=(),
        )


def test_models_probe_target_http_vide_leve_value_error():
    """ERR_HEALTH_CIBLE_INVALIDE : probe_type=HTTP avec probe_target=""."""
    with pytest.raises(ValueError, match="ERR_HEALTH_CIBLE_INVALIDE"):
        ServiceSpec(
            host_port=18080, container_port=8080, name="svc",
            image="redis:7",
            probe_type=ProbeType.HTTP,
            probe_target="",
        )



def _plan(services):
    return DeploymentPlan(
        plan_id="t",
        profile="minimal-cpu",
        target=RenderTarget.COMPOSE,
        services=tuple(services),
        model="m",
        embed_model="e",
    )

def _svc(name="redis", container_port=6379, host_port=18080,
         healthcheck_url=None, health_required=True, probe_type=None):
    return ServiceSpec(
        name=name,
        image="redis:7",
        container_port=container_port,
        host_port=host_port,
        healthcheck_url=healthcheck_url,
        health_required=health_required,
        probe_type=probe_type,
    )

def test_sonde_par_defaut_urlopen_ok(monkeypatch):
    """urlopen réussit -> _default_probe renvoie True -> service marqué sain."""
    calls = []

    def faux_urlopen(url, timeout=2):
        calls.append((url, timeout))
        class _R:
            status = 200
            def read(self, *a, **k):
                return b""
        return _R()

    monkeypatch.setattr("urllib.request.urlopen", faux_urlopen)

    plan = _plan([_svc(healthcheck_url="http://127.0.0.1:18080/health")])

    result = compose_mod.wait_healthy(plan, timeout_s=3.0)
    # wait_healthy rend {service: étiquette} — forme imposée par cli.py:410 qui
    # compare à "healthy". La sonde par défaut a donc bien été exercée et a réussi.
    assert result == {"redis": "healthy"}
    assert len(calls) >= 1
    assert calls[0][0] == "http://127.0.0.1:18080/health"

def test_sonde_par_defaut_urlopen_leve_ne_propage_pas(monkeypatch):
    """urlopen lève -> _default_probe attrape et renvoie False -> pas d'exception qui remonte,
    on obtient un DeployError de timeout, JAMAIS l'URLError d'origine."""
    from urllib.error import URLError

    def faux_urlopen(url, timeout=2):
        raise URLError(f"refused: {url}")

    monkeypatch.setattr("urllib.request.urlopen", faux_urlopen)

    plan = _plan([_svc(healthcheck_url="http://127.0.0.1:18080/health")])

    with pytest.raises(DeployError) as ei:
        compose_mod.wait_healthy(plan, timeout_s=0.5)
    # On doit avoir un timeout/attente, pas l'URLError brute propagée.
    assert "URLError" not in str(ei.value)

def test_render_k3s_fallback_tcp_socket_sans_sonde(monkeypatch):
    """Aucun contrat de sonde -> _probes_block dégrade en tcpSocket sur container_port,
    avec startupProbe.failureThreshold strictement supérieur à livenessProbe.failureThreshold."""
    import yaml
    from forgeai.renderers.k3s import render_k3s

    # _verifier_capacite exige un CapaciteCluster cohérent avec le plan : on la shunte.
    monkeypatch.setattr(
        "forgeai.renderers.k3s._verifier_capacite",
        lambda plan, capacite: None,
    )

    svc = _svc(name="redis", container_port=6379, host_port=18080,
               healthcheck_url=None, health_required=True,
               probe_type=None)
    plan = _plan([svc])

    out = render_k3s(plan)
    docs = list(yaml.safe_load_all(out))

    deployment = None
    for d in docs:
        if d and d.get("kind") == "Deployment" and d.get("metadata", {}).get("name") == "redis":
            deployment = d
            break
    assert deployment is not None, "Deployment 'redis' introuvable dans le manifeste rendu"

    container = deployment["spec"]["template"]["spec"]["containers"][0]
    probes = container.get("startupProbe"), container.get("readinessProbe"), container.get("livenessProbe")
    assert all(p is not None for p in probes), "les trois sondes doivent être présentes"

    for probe in probes:
        assert probe["tcpSocket"]["port"] == 6379, (
            f"fallback tcpSocket doit viser container_port=6379, got {probe}"
        )

    assert container["startupProbe"]["failureThreshold"] > container["livenessProbe"]["failureThreshold"], (
        "startupProbe.failureThreshold doit être strictement supérieur à "
        "livenessProbe.failureThreshold (démarrage lent vs panne)"
    )
    assert container["startupProbe"]["failureThreshold"] == 12
    assert container["livenessProbe"]["failureThreshold"] == 3
