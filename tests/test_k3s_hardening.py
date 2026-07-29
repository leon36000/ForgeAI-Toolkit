"""Durcissement du renderer k3s/k8s — findings Sentinelle (majeures) sur render_k3s.

Traite 3 trous de robustesse latents (le renderer les portait avant K-CHOICE) :
  1. node_port_for : plage NodePort saturée -> erreur claire, JAMAIS de boucle infinie (DoS) ;
  2. volume mal formé (sans ':') -> ValueError explicite, pas d'IndexError ;
  3. valeurs interpolées au manifeste (name/image/node/volume) : refus des caractères qui
     casseraient/injecteraient le YAML (newline, contrôle) — défense en profondeur.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from forgeai.core.models import DeploymentPlan, RenderTarget, ServiceSpec
from forgeai.renderers.k3s import node_port_for, render_k3s


def _svc(**kw):
    d = dict(name="ollama", image="ollama/ollama:latest", host_port=21434, container_port=11434)
    d.update(kw)
    return ServiceSpec(**d)


def _plan(services):
    return DeploymentPlan(plan_id="t", profile="minimal-cpu", target=RenderTarget.K3S,
                          services=tuple(services), model="m", embed_model="e")


# 1) saturation de la plage NodePort -> erreur bornée, pas de boucle infinie
def test_node_port_for_plage_saturee_leve_erreur():
    used = set(range(30000, 32768))  # les 2768 ports occupés
    with pytest.raises(RuntimeError):
        node_port_for(_svc(), used)


def test_node_port_for_normal_ok():
    used: set = set()
    p1 = node_port_for(_svc(host_port=21434), used)
    p2 = node_port_for(_svc(host_port=24202), used)  # collision de modulo -> réassigné
    assert p1 != p2 and 30000 <= p1 <= 32767 and 30000 <= p2 <= 32767


# 2) volume mal formé -> ValueError claire (pas d'IndexError)
def test_volume_sans_deux_points_leve_valueerror():
    with pytest.raises(ValueError):
        render_k3s(_plan([_svc(volumes=("volume-sans-chemin",))]))


def test_volume_bien_forme_ok():
    out = render_k3s(_plan([_svc(volumes=("data:/root/.ollama",))]))
    assert "name: data" in out and "mountPath: /root/.ollama" in out


# 3) injection YAML : une valeur avec newline/contrôle est refusée
@pytest.mark.parametrize("champ", ["name", "image"])
def test_valeur_avec_newline_refusee(champ):
    with pytest.raises(ValueError):
        render_k3s(_plan([_svc(**{champ: "ok\n      hostPID: true"})]))


def test_node_avec_newline_refuse():
    with pytest.raises(ValueError):
        render_k3s(_plan([_svc()]), node="node\nmalicious: true")


# 4) service_type : le renderer ne fait pas confiance à son appelant -> allowlist stricte
def test_service_type_invalide_refuse():
    with pytest.raises(ValueError):
        render_k3s(_plan([_svc()]), service_type="NodePort\n  hostNetwork: true")
    with pytest.raises(ValueError):
        render_k3s(_plan([_svc()]), service_type="Bidon")


def test_service_types_valides_ok():
    for st in ("NodePort", "LoadBalancer"):
        out = render_k3s(_plan([_svc()]), service_type=st)
        assert f"type: {st}" in out


# ---------------------------------------------------------------------------
# K8S-022 / FAI-U-022 — le profil Pod Security Standards « restricted » est le DÉFAUT.
# Validateur réel des règles PSS restricted (k8s >= 1.25) appliqué aux manifests rendus,
# et non une simple recherche de sous-chaîne : chaque conteneur de chaque Deployment est vérifié.
# ---------------------------------------------------------------------------
import yaml

# Volumes autorisés par PSS restricted (les autres, dont hostPath, sont refusés).
_PSS_VOLUMES_OK = frozenset({
    "configMap", "csi", "downwardAPI", "emptyDir", "ephemeral",
    "persistentVolumeClaim", "projected", "secret",
})


def _deployments(manifest: str) -> list[dict]:
    return [d for d in yaml.safe_load_all(manifest) if d and d.get("kind") == "Deployment"]


def violations_pss_restricted(manifest: str) -> list[str]:
    """Retourne la liste des écarts au profil PSS `restricted`. Vide = conforme."""
    out: list[str] = []
    for dep in _deployments(manifest):
        pod = dep["spec"]["template"]["spec"]
        psc = pod.get("securityContext") or {}
        who = dep["metadata"]["name"]
        for champ in ("hostNetwork", "hostPID", "hostIPC"):
            if pod.get(champ):
                out.append(f"{who}: {champ} activé")
        for vol in pod.get("volumes") or []:
            kinds = [k for k in vol if k != "name"]
            for kind in kinds:
                if kind not in _PSS_VOLUMES_OK:
                    out.append(f"{who}: type de volume interdit par restricted : {kind}")
        for cont in pod.get("containers") or []:
            csc = cont.get("securityContext") or {}
            cible = f"{who}/{cont['name']}"
            if csc.get("privileged"):
                out.append(f"{cible}: privileged")
            if csc.get("allowPrivilegeEscalation") is not False:
                out.append(f"{cible}: allowPrivilegeEscalation != false")
            drop = ((csc.get("capabilities") or {}).get("drop")) or []
            if "ALL" not in drop:
                out.append(f"{cible}: capabilities.drop ne contient pas ALL")
            add = ((csc.get("capabilities") or {}).get("add")) or []
            if [c for c in add if c != "NET_BIND_SERVICE"]:
                out.append(f"{cible}: capabilities.add interdites : {add}")
            if not (csc.get("runAsNonRoot") or psc.get("runAsNonRoot")):
                out.append(f"{cible}: runAsNonRoot absent (ni pod ni conteneur)")
            seccomp = (csc.get("seccompProfile") or psc.get("seccompProfile") or {}).get("type")
            if seccomp not in ("RuntimeDefault", "Localhost"):
                out.append(f"{cible}: seccompProfile.type = {seccomp!r}")
    return out


def test_profil_restricted_est_le_defaut():
    """Un service ordinaire (sans exception déclarée) est rendu conforme PSS restricted."""
    out = render_k3s(_plan([_svc(name="service-quelconque", image="exemple/app:1.0")]))
    assert violations_pss_restricted(out) == []


def test_root_filesystem_en_lecture_seule_par_defaut():
    out = render_k3s(_plan([_svc(name="service-quelconque", image="exemple/app:1.0")]))
    dep = _deployments(out)[0]
    cont = dep["spec"]["template"]["spec"]["containers"][0]
    assert cont["securityContext"]["readOnlyRootFilesystem"] is True
    # readOnlyRootFilesystem sans /tmp inscriptible casse la plupart des runtimes -> emptyDir explicite
    montages = {m["mountPath"] for m in cont.get("volumeMounts") or []}
    assert "/tmp" in montages


# ---------------------------------------------------------------------------
# K8S-024 / FAI-U-024 — Pod Security Admission : le Namespace rendu doit PORTER le niveau
# d'enforcement, sinon le profil restricted de K8S-022 n'est jamais APPLIQUÉ par le cluster.
# Le niveau enforce doit correspondre à ce que les manifests respectent réellement.
# ---------------------------------------------------------------------------
_PSA_PREFIXE = "pod-security.kubernetes.io/"


def _namespace(manifest: str) -> dict:
    for doc in yaml.safe_load_all(manifest):
        if doc and doc.get("kind") == "Namespace":
            return doc
    raise AssertionError("aucun Namespace dans le manifeste rendu")


def test_namespace_porte_l_admission_pod_security():
    """Sans ces étiquettes, le cluster n'applique RIEN : le durcissement reste déclaratif."""
    ns = _namespace(render_k3s(_plan([_svc(name="service-quelconque")])))
    labels = ns["metadata"].get("labels") or {}
    assert labels.get(_PSA_PREFIXE + "enforce") == "restricted"
    assert labels.get(_PSA_PREFIXE + "audit") == "restricted"
    assert labels.get(_PSA_PREFIXE + "warn") == "restricted"


def test_versions_d_admission_epinglees():
    """`latest` ferait dériver la politique au gré des montées de version du cluster : versions
    ÉPINGLÉES, comme les images le sont déjà (FAI-0011)."""
    ns = _namespace(render_k3s(_plan([_svc(name="service-quelconque")])))
    labels = ns["metadata"].get("labels") or {}
    for mode in ("enforce", "audit", "warn"):
        version = labels.get(f"{_PSA_PREFIXE}{mode}-version")
        assert version and version != "latest", f"{mode}-version doit être épinglée, vu : {version!r}"
        assert version.startswith("v1."), f"version k8s attendue (vX.Y), vu : {version!r}"


def test_enforce_correspond_aux_manifests_rendus():
    """Le niveau annoncé doit être TENU : un plan sans GPU est conforme restricted, donc enforce
    reste `restricted`. C'est le lien entre l'étiquette et la réalité du rendu."""
    out = render_k3s(_plan([_svc(name="service-quelconque")]))
    assert violations_pss_restricted(out) == []
    labels = _namespace(out)["metadata"].get("labels") or {}
    assert labels.get(_PSA_PREFIXE + "enforce") == "restricted"


def test_exception_gpu_degrade_enforce_et_reste_visible():
    """Un service GPU DÉROGE au profil restricted (mesure K8S-022 : non-root = 0/4 devices).
    Annoncer `enforce: restricted` sur un tel plan serait un mensonge : le cluster REFUSERAIT les
    pods au déploiement. Niveau réellement tenu, MESURÉ sur cluster k3s v1.35.5 avec le pod GPU réel :
      enforce=restricted -> REFUSÉ (« restricted volume type hostPath », « runAsNonRoot »)
      enforce=baseline    -> REFUSÉ (« hostPath volumes (volume "dri") »)
      enforce=privileged  -> ACCEPTÉ
    `baseline` interdit lui aussi hostPath : seul `privileged` admet le passthrough de devices.
    L'exception doit donc être VISIBLE : enforce descendu au seul niveau qui tient, audit ET warn
    MAINTENUS à restricted pour que l'API server continue de signaler chaque écart."""
    out = render_k3s(_plan([_svc(name="ollama", gpu=True, gpu_vendor="amd")]))
    labels = _namespace(out)["metadata"].get("labels") or {}
    assert labels.get(_PSA_PREFIXE + "enforce") == "privileged"
    assert labels.get(_PSA_PREFIXE + "audit") == "restricted"
    assert labels.get(_PSA_PREFIXE + "warn") == "restricted"
    assert "# forgeai:" in out.split("kind: Namespace")[1].split("---")[0]


def test_service_sans_volume_declare_garde_un_chemin_de_donnees_inscriptible():
    """Régression K8S-022 attrapée par l'E2E de K8S-024 : avec readOnlyRootFilesystem, un service
    dont le répertoire de données n'est PAS déclaré en volume ne peut plus le créer. Mesuré sur
    cluster réel : qdrant sans volume -> « Service internal error: Read-only file system (os error
    30) ». Le profil doit donc fournir un emptyDir de repli sur ce chemin."""
    out = render_k3s(_plan([_svc(name="qdrant", image="qdrant/qdrant:v1.12.5")]))
    cont = _deployments(out)[0]["spec"]["template"]["spec"]["containers"][0]
    montages = {m["mountPath"] for m in cont.get("volumeMounts") or []}
    assert "/qdrant/storage" in montages


def test_le_pvc_prime_sur_l_emptydir_de_repli():
    """Le repli ne doit JAMAIS masquer les données : quand un volume persistant est déclaré sur le
    même chemin, il est monté seul (un mountPath dupliqué rendrait d'ailleurs le pod invalide)."""
    out = render_k3s(_plan([_svc(name="qdrant", image="qdrant/qdrant:v1.12.5",
                                volumes=("forgeai-qdrant-data:/qdrant/storage",))]))
    pod = _deployments(out)[0]["spec"]["template"]["spec"]
    montages = [m["mountPath"] for m in pod["containers"][0].get("volumeMounts") or []]
    assert montages.count("/qdrant/storage") == 1
    volume = next(v for v in pod["volumes"] if v["name"] == "forgeai-qdrant-data")
    assert "persistentVolumeClaim" in volume and "emptyDir" not in volume


# ---------------------------------------------------------------------------
# K8S-023 / FAI-U-023 — NetworkPolicy : default-deny + allowlists par dépendance.
# L'unique politique rendue jusqu'ici ne portait que `Ingress` (egress TOTALEMENT libre)
# et autorisait `from: podSelector: {}` — un accès intra-namespace UNIVERSEL, que le
# package interdit explicitement.
# ---------------------------------------------------------------------------
def _policies(manifest: str) -> list[dict]:
    return [d for d in yaml.safe_load_all(manifest) if d and d.get("kind") == "NetworkPolicy"]


def _plan_dependant():
    """litellm dépend de redis : une dépendance DÉCLARÉE dont doit dériver l'allowlist."""
    redis = _svc(name="redis", image="redis:7-alpine", host_port=26379, container_port=6379)
    litellm = _svc(name="litellm", image="litellm:x", host_port=24000, container_port=4000,
                   depends=("redis",))
    return _plan([redis, litellm])


def test_default_deny_porte_ingress_ET_egress():
    """Sans `Egress` dans policyTypes, un pod compromis sort librement : exfiltration ouverte."""
    politiques = _policies(render_k3s(_plan_dependant()))
    deny = [p for p in politiques if p["spec"].get("podSelector") == {}]
    assert deny, "une politique par défaut s'appliquant à TOUS les pods est requise"
    types = set(deny[0]["spec"].get("policyTypes") or [])
    assert types == {"Ingress", "Egress"}, f"default-deny incomplet : {types}"
    assert not deny[0]["spec"].get("ingress"), "la politique par défaut ne doit rien autoriser"
    assert not deny[0]["spec"].get("egress"), "la politique par défaut ne doit rien autoriser"


def test_aucun_acces_intra_namespace_universel():
    """`from: [{podSelector: {}}]` autorise TOUT pod du namespace à joindre TOUT autre :
    c'est exactement ce que le package proscrit."""
    for politique in _policies(render_k3s(_plan_dependant())):
        for regle in politique["spec"].get("ingress") or []:
            for origine in regle.get("from") or []:
                assert origine.get("podSelector") != {}, \
                    f"accès intra-namespace universel dans {politique['metadata']['name']}"


def test_dns_autorise_sans_ouvrir_internet():
    """Egress refusé par défaut casse la résolution de noms : DNS doit être rouvert
    explicitement — vers kube-system, sur le port 53, et RIEN d'autre."""
    politiques = _policies(render_k3s(_plan_dependant()))
    dns = [p for p in politiques if "dns" in p["metadata"]["name"]]
    assert dns, "une politique DNS explicite est requise"
    regles = dns[0]["spec"].get("egress") or []
    ports = {(pt.get("protocol"), pt.get("port")) for r in regles for pt in (r.get("ports") or [])}
    assert ports and all(p == 53 for _, p in ports), f"DNS doit se limiter au port 53 : {ports}"
    for regle in regles:
        for dest in regle.get("to") or []:
            assert "ipBlock" not in dest or not dest["ipBlock"].get("cidr", "").endswith("/0"), \
                "le DNS ne doit pas ouvrir Internet"


def test_chaque_dependance_declaree_produit_une_allowlist():
    """`litellm.depends = ('redis',)` doit produire un flux PERMIS litellm -> redis:6379,
    et lui seul : chaque flux ouvert correspond à une dépendance du plan."""
    politiques = _policies(render_k3s(_plan_dependant()))
    vers_redis = [p for p in politiques
                  if p["spec"].get("podSelector", {}).get("matchLabels", {}).get("app") == "redis"
                  and p["spec"].get("ingress")]
    assert vers_redis, "redis doit porter une politique d'ingress dérivée de la dépendance"
    origines = [o for p in vers_redis for r in p["spec"]["ingress"] for o in (r.get("from") or [])]
    apps = {o.get("podSelector", {}).get("matchLabels", {}).get("app") for o in origines}
    assert apps == {"litellm"}, f"seul le dépendant déclaré doit être autorisé : {apps}"
    ports = {pt.get("port") for p in vers_redis for r in p["spec"]["ingress"]
             for pt in (r.get("ports") or [])}
    assert ports == {6379}, f"le flux doit être borné au port du service cible : {ports}"


def test_service_sans_dependant_ne_recoit_aucune_allowlist():
    """Contrôle négatif : un service dont personne ne dépend ne doit ouvrir aucun flux entrant."""
    seul = _svc(name="isole", image="x:1", host_port=29999, container_port=9999)
    politiques = _policies(render_k3s(_plan([seul])))
    pour_isole = [p for p in politiques
                  if p["spec"].get("podSelector", {}).get("matchLabels", {}).get("app") == "isole"]
    assert not any(p["spec"].get("ingress") for p in pour_isole), \
        "aucun dépendant déclaré : aucun flux entrant ne doit être ouvert"


def test_le_dependant_recoit_aussi_une_autorisation_de_sortie():
    """Défaut MESURÉ sur cluster k3s réel : le flux `litellm -> redis:6379`, pourtant justifié par
    `litellm.depends = ('redis',)`, était BLOQUÉ. En Kubernetes un flux n'est permis que si
    l'egress est autorisé À LA SOURCE **et** l'ingress à la destination ; n'ouvrir que la
    destination laisse le default-deny refuser la sortie du dépendant. La symétrie n'est pas un
    détail de style, c'est une exigence du modèle réseau."""
    politiques = _policies(render_k3s(_plan_dependant()))
    egress_litellm = [p for p in politiques
                      if p["spec"].get("podSelector", {}).get("matchLabels", {}).get("app") == "litellm"
                      and "Egress" in (p["spec"].get("policyTypes") or [])
                      and p["spec"].get("egress")]
    assert egress_litellm, "le dépendant doit recevoir une autorisation de SORTIE vers sa cible"
    regles = egress_litellm[0]["spec"]["egress"]
    cibles = {d.get("podSelector", {}).get("matchLabels", {}).get("app")
              for r in regles for d in (r.get("to") or [])}
    assert cibles == {"redis"}, f"la sortie doit être bornée aux cibles déclarées : {cibles}"
    ports = {pt.get("port") for r in regles for pt in (r.get("ports") or [])}
    assert ports == {6379}, f"la sortie doit être bornée au port de la cible : {ports}"


def test_service_sans_dependance_ne_recoit_aucune_sortie():
    """Contrôle négatif symétrique : sans dépendance déclarée, aucun egress n'est ouvert et le
    default-deny continue de confiner le service."""
    seul = _svc(name="isole", image="x:1", host_port=29999, container_port=9999)
    politiques = _policies(render_k3s(_plan([seul])))
    pour_isole = [p for p in politiques
                  if p["spec"].get("podSelector", {}).get("matchLabels", {}).get("app") == "isole"]
    assert not any(p["spec"].get("egress") for p in pour_isole), \
        "aucune dépendance déclarée : aucune sortie ne doit être ouverte"


# ---------------------------------------------------------------------------
# K8S-027 / FAI-U-027 — quotas et limites par namespace, dérivés du budget réel du plan.
# Aucun ResourceQuota ni LimitRange n'était émis : rien ne bornait ce qu'un namespace
# pouvait consommer, et rien ne refusait un plan dépassant la capacité du cluster AVANT
# application. Le budget est calculable depuis RES-012B (ressources par service).
# ---------------------------------------------------------------------------
from forgeai.core.models import CapaciteCluster, QuotaError


def _plan_trois_services():
    """llm 4000m/8Gi + db 1000m/2Gi + sidecar 500m/512Mi = 5500m / 10752Mi de limites."""
    return _plan([
        _svc(name="ollama", image="o:1", host_port=1, container_port=1, resource_class="llm"),
        _svc(name="qdrant", image="q:1", host_port=2, container_port=2, resource_class="db"),
        _svc(name="litellm", image="l:1", host_port=3, container_port=3, resource_class="sidecar"),
    ])


def _quota(manifeste: str) -> dict:
    for d in yaml.safe_load_all(manifeste):
        if d and d.get("kind") == "ResourceQuota":
            return d
    raise AssertionError("aucun ResourceQuota dans le manifeste")


def _limitrange(manifeste: str) -> dict:
    for d in yaml.safe_load_all(manifeste):
        if d and d.get("kind") == "LimitRange":
            return d
    raise AssertionError("aucun LimitRange dans le manifeste")


def test_quota_derive_du_budget_reel_du_plan():
    """Critère 1 — le quota doit refléter ce que le plan consomme VRAIMENT, pas un chiffre
    arbitraire. Il est donc dérivé de la somme des `ressources_effectives` (RES-012B)."""
    out = render_k3s(_plan_trois_services())
    spec = _quota(out)["spec"]["hard"]
    assert spec["limits.cpu"] == "5500m", f"somme des limites CPU : {spec['limits.cpu']}"
    assert spec["limits.memory"] == "10752Mi", f"somme des limites mémoire : {spec['limits.memory']}"
    assert "requests.cpu" in spec and "requests.memory" in spec


def test_limitrange_present_et_coherent():
    """Critère 1 (suite) — le LimitRange borne un conteneur qui n'aurait déclaré aucune
    ressource ; sans lui, un pod sans limites échappe au quota et l'épuise."""
    lr = _limitrange(render_k3s(_plan_trois_services()))
    limites = lr["spec"]["limits"][0]
    assert limites["type"] == "Container"
    assert "default" in limites and "defaultRequest" in limites


def test_le_quota_n_empeche_pas_un_bundle_valide():
    """Critère 2 — GARDE CONTRE LA SOUS-ALLOCATION. Un quota calculé au plus juste bloquerait
    le déploiement qu'il est censé encadrer : le quota doit être >= au besoin du plan."""
    out = render_k3s(_plan_trois_services())
    spec = _quota(out)["spec"]["hard"]
    cpu_quota = int(spec["limits.cpu"].rstrip("m"))
    mem_quota = int(spec["limits.memory"].rstrip("Mi"))
    assert cpu_quota >= 5500, "le quota CPU doit couvrir le besoin du plan"
    assert mem_quota >= 10752, "le quota mémoire doit couvrir le besoin du plan"


def test_plan_depassant_la_capacite_est_refuse_avant_application():
    """Critère 3 — un plan qui dépasse la capacité du cluster doit être refusé AVANT kubectl,
    avec sa cause chiffrée. Sinon les pods restent Pending sans explication."""
    petite = CapaciteCluster(cpu_millicores=2000, memoire_mib=4096)
    with pytest.raises(QuotaError) as exc:
        render_k3s(_plan_trois_services(), capacite=petite)
    message = str(exc.value)
    assert "5500" in message and "2000" in message, \
        f"l'erreur doit chiffrer le besoin ET la capacité : {message}"


def test_plan_tenant_dans_la_capacite_est_accepte():
    """Contrôle positif : une capacité suffisante laisse passer le plan."""
    large = CapaciteCluster(cpu_millicores=16000, memoire_mib=32768)
    out = render_k3s(_plan_trois_services(), capacite=large)
    assert _quota(out)["spec"]["hard"]["limits.cpu"] == "5500m"


def test_sans_capacite_declaree_aucun_refus():
    """Rétro-compatibilité : sans capacité fournie, on ne peut rien vérifier — le rendu
    reste celui d'avant. La vérification est une capacité ajoutée, pas une rupture."""
    out = render_k3s(_plan_trois_services())
    assert _quota(out)["spec"]["hard"]["limits.cpu"] == "5500m"
