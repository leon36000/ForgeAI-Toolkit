"""Corrective (finding Sentinelle) : le health-check K3s du wizard dérive les chemins de
probe DU PLAN, jamais d'un dict codé en dur — plus de KeyError sur un service inconnu."""
from forgeai.core.models import DeploymentPlan, ServiceSpec, RenderTarget
from forgeai.cli import _k3s_probe_paths


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
