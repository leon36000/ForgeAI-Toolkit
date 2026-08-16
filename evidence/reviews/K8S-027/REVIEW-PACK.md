# K8S-027 — Quotas de namespace dérivés du budget réel (FAI-U-027)

## Cause racine
Aucun `ResourceQuota` ni `LimitRange` n'était émis. Rien ne bornait la consommation d'un namespace,
et un plan dépassant la capacité du cluster était rendu sans broncher : ses pods restaient
`Pending`, sans cause lisible, **découverts en production**.

## Changement — le quota dérive du budget, il n'est pas arbitraire
Le budget est la **somme des `ressources_effectives`** de chaque service — donnée rendue explicite
par RES-012B. Les deux packages s'enchaînent : l'un attribue les ressources par service, l'autre
les agrège en quota de namespace.

| objet | contenu | rôle |
|---|---|---|
| `ResourceQuota` | `limits 5500m/10752Mi`, `requests 1350m/4736Mi` | borne exactement ce que le plan consomme |
| `LimitRange` | `default 250m/256Mi`, `defaultRequest 50m/64Mi` | encadre un conteneur qui ne déclare rien |

**Le quota vaut exactement le budget** : ni plus (gaspillage de capacité réservée), ni moins — un
quota sous-alloué bloquerait le déploiement qu'il est censé encadrer. C'est la garde contre la
sous-allocation exigée par le package.

Sans `LimitRange`, un conteneur ne déclarant aucune ressource **échapperait au quota** et pourrait
l'épuiser à lui seul : le quota ne compte que ce qui est déclaré.

## La garde contre le dépassement s'exécute AVANT tout rendu
```
cluster trop petit (2000m/4096Mi)  -> ERR_QUOTA_CPU_DEPASSE: le plan requiert 5500m CPU
                                      mais le cluster n'en déclare que 2000m.
cluster suffisant (16000m/32768Mi) -> accepté
sans capacité déclarée             -> accepté (rétro-compatibilité stricte)
```
La vérification est placée en tête de `render_k3s`, avant la moindre ligne de manifeste : rendre
puis échouer laisserait l'utilisateur appliquer un fichier voué au `Pending`. Le message **chiffre
le besoin ET la capacité**, pour être lisible sans recalcul.

## Objection de revue traitée (APPROVE 3/3, sceau d4d21dddf2ab)
**Gemini-3.1-Pro, sévérité mineure** : `_budget_du_plan` contenait deux `continue` défensifs qui
**sous-comptaient le budget en silence**.

**Vérification faite avant d'accepter** : l'état est **inatteignable** via `ServiceSpec` — la
validation fail-fast de RES-012B garantit les quatre valeurs. J'aurais pu classer l'objection en
« théorique ».

**Corrigée quand même**, parce que le principe tient : ce budget devient un `ResourceQuota`, et une
branche défensive qui **fausse un budget en silence est pire que pas de branche du tout**. Elle
convertit un état impossible en *quota faux* au lieu d'une *erreur visible*. Si cet état devenait
atteignable — nouveau renderer, désérialisation directe, refactor — le symptôme serait un
déploiement qui ne démarre pas, sans cause lisible : exactement le défaut que ce package corrige.

Les `continue` sont devenus des `ValueError` nommant le service, la catégorie et la clé manquante
(`ERR_QUOTA_RESSOURCES_ABSENTES`, `ERR_QUOTA_RESSOURCES_INCOMPLETES`). Test rouge écrit avant.

## Objections du tour 2 — triées par des tests rouges écrits AVANT correction
| objection | test | verdict |
|---|---|---|
| **Tencent** — `AttributeError` quand `res.get(cat, {})` rencontre une valeur `None` | **ROUGE** | **vrai défaut** |
| **DeepSeek** — `ERR_QUOTA_MEMOIRE_DEPASSEE` jamais atteint (cluster trop petit en CPU *et* mémoire) | vert | correct mais **non protégé** |
| **Tencent** — le test n'assertait que la *présence* de `requests.*`, pas les valeurs | vert | somme correcte, **assertion manquante** |

Le test rouge tranche ce que la lecture seule ne peut pas : **une objection sur trois** portait sur
un vrai bug ; les deux autres sur des lacunes de couverture. Les trois tests restent.

**Le vrai défaut** : `dict.get(cle, {})` ne renvoie `{}` que si la clé est **absente**. Si elle
existe avec la valeur `None`, l'expression rend `None` et le `.get()` suivant lève
`AttributeError` — une trace technique opaque au lieu du `ValueError` explicite prévu deux lignes
plus bas. Un défaut de données doit **nommer sa cause**. Corrigé par `(res.get(categorie) or {})`.

Fait notable : **Tencent-Hy3 a trouvé le seul vrai bug** que ni Gemini ni DeepSeek n'avaient vu —
et c'est le vendor recruté en remplacement d'une route tombée. La diversité du trio n'est pas
décorative.

## Rollback
`git revert` → retour sans quota (défaut FAI-U-027 connu) ; baseline verte.

# ==== DIFF INTÉGRAL ====
diff --git a/src/forgeai/core/models.py b/src/forgeai/core/models.py
index 1223f27..283cd0c 100644
--- a/src/forgeai/core/models.py
+++ b/src/forgeai/core/models.py
@@ -287,6 +287,40 @@ def valider_placement(svc, inventaire, node_demande):
         f"{'; '.join(candidats_examines) or 'aucun'}")
 
 
+class QuotaError(ValueError):
+    """Le plan dépasse la capacité déclarée du cluster.
+
+    Levée AVANT rendu du manifeste pour éviter qu'un déploiement trop gros
+    ne se traduise par des pods ``Pending`` sans cause lisible côté kubectl.
+    Le message chiffre systématiquement le besoin du plan et la capacité
+    offerte par le cluster afin qu'un opérateur corrige l'un ou l'autre
+    sans avoir à recalculer.
+    """
+
+
+@dataclass(frozen=True)
+class CapaciteCluster:
+    """Capacité totale (CPU + mémoire) qu'un cluster déclare pouvoir servir.
+
+    Les valeurs sont normalisées en milliCPU et en MiB pour permettre une
+    comparaison arithmétique directe avec le budget d'un ``DeploymentPlan``.
+    Une capacité nulle ou négative n'a aucun sens physique : elle est refusée
+    à l'instanciation pour ne pas produire plus tard une division par zéro
+    ou un faux positif de dépassement.
+    """
+
+    cpu_millicores: int
+    memoire_mib: int
+
+    def __post_init__(self) -> None:
+        if self.cpu_millicores <= 0 or self.memoire_mib <= 0:
+            raise ValueError(
+                "ERR_QUOTA_CAPACITE_INVALIDE: la capacité du cluster doit être "
+                f"strictement positive (reçu cpu={self.cpu_millicores}, "
+                f"memoire={self.memoire_mib} Mi)."
+            )
+
+
 @dataclass(frozen=True)
 class ServiceSpec:
     """Service concret d'un plan de déploiement (brique instanciée)."""
diff --git a/src/forgeai/renderers/k3s.py b/src/forgeai/renderers/k3s.py
index b9f5bee..43e33de 100644
--- a/src/forgeai/renderers/k3s.py
+++ b/src/forgeai/renderers/k3s.py
@@ -12,7 +12,7 @@ import textwrap
 from typing import NamedTuple
 from urllib.parse import urlsplit
 
-from forgeai.core.models import DeploymentPlan, ServiceSpec, NodeInventaire, valider_placement
+from forgeai.core.models import DeploymentPlan, ServiceSpec, NodeInventaire, valider_placement, CapaciteCluster, QuotaError
 from forgeai.renderers._openbao import UNSEAL_SCRIPT as _UNSEAL_SCRIPT
 
 NAMESPACE = "forgeai-minimal"
@@ -733,15 +733,190 @@ def _network_policies(plan: DeploymentPlan) -> str:
     return "".join(parts)
 
 
+# Conversions CPU/mémoire : la somme du budget doit être NUMÉRIQUE. Additionner
+# des chaînes comme "4000m" et "1" n'a aucun sens — Kubernetes accepte ces deux
+# notations pour 4000 milliCPU, mais une addition Python donnerait "4000m1".
+# On normalise donc tout en entiers (milliCPU, MiB) avant de sommer.
+_MIB_PER_GIB = 1024
+
+
+def _cpu_en_millicores(valeur: str) -> int:
+    """Convertit une valeur CPU Kubernetes (``"250m"`` ou ``"2"``) en milliCPU."""
+    valeur = valeur.strip()
+    if valeur.endswith("m"):
+        return int(valeur[:-1])
+    # Forme décimale : "1" = 1 CPU = 1000 milliCPU.
+    return int(float(valeur) * 1000)
+
+
+def _memoire_en_mib(valeur: str) -> int:
+    """Convertit une valeur mémoire Kubernetes (``"256Mi"`` ou ``"1Gi"``) en MiB."""
+    valeur = valeur.strip()
+    if valeur.endswith("Mi"):
+        return int(valeur[:-2])
+    if valeur.endswith("Gi"):
+        return int(valeur[:-2]) * _MIB_PER_GIB
+    raise ValueError(
+        f"ERR_QUOTA_MEMOIRE_INVALIDE: unité mémoire non supportée: {valeur!r}"
+    )
+
+
+def _budget_du_plan(plan: DeploymentPlan) -> dict:
+    """Somme, pour chaque service du plan, ses ``requests`` et ``limits`` effectifs.
+
+    Retourne un dictionnaire imbriqué compatible avec la sérialisation YAML :
+    ``{"requests": {"cpu_m": int, "mem_mib": int},
+       "limits":   {"cpu_m": int, "mem_mib": int}}``.
+
+    Un budget faux en silence est PIRE qu'une erreur bruyante : ce budget devient un
+    ``ResourceQuota``, et sous-compté il produirait un quota trop petit qui bloquerait le
+    déploiement qu'il est censé encadrer. Toute ressource absente ou incomplète lève donc,
+    plutôt que d'être ignorée (objection de revue scellée, Gemini-3.1-Pro).
+    """
+    budget = {
+        "requests": {"cpu_m": 0, "mem_mib": 0},
+        "limits": {"cpu_m": 0, "mem_mib": 0},
+    }
+    for svc in plan.services:
+        res = getattr(svc, "ressources_effectives", None)
+        if res is None:
+            # On lève une erreur plutôt que de fausser le budget en silence
+            raise ValueError(
+                "ERR_QUOTA_RESSOURCES_ABSENTES: le service {} n'a pas de ressources_effectives".format(svc.name)
+            )
+        for categorie in ("requests", "limits"):
+            # `dict.get(cle, {})` ne protège que de l'absence de clé, pas d'une valeur
+            # None explicite : sans le `or {}`, le .get() suivant lèverait AttributeError
+            # — une trace technique opaque au lieu du ValueError qui nomme la cause.
+            cpu = (res.get(categorie) or {}).get("cpu")
+            memoire = (res.get(categorie) or {}).get("memory")
+            if cpu is None or memoire is None:
+                # On lève une erreur plutôt que de fausser le budget en silence
+                raise ValueError(
+                    "ERR_QUOTA_RESSOURCES_INCOMPLETES: le service {} n'a pas {} dans sa catégorie {}".format(
+                        svc.name,
+                        "cpu" if cpu is None else "memory",
+                        categorie
+                    )
+                )
+            budget[categorie]["cpu_m"] += _cpu_en_millicores(cpu)
+            budget[categorie]["mem_mib"] += _memoire_en_mib(memoire)
+    return budget
+
+
+# Valeurs utilitaires de la LimitRange : volontairement modestes. Elles ne
+# décrivent pas le profil "LLM lourd" (qui a ses propres ressources_effectives)
+# mais le conteneur "moyen" qui ne déclare rien. Sans LimitRange, ce conteneur
+# silencieux échapperait au quota et pourrait, à lui seul, épuiser la capacité
+# allouée au namespace.
+_LIMITE_DEFAUT_CPU = "250m"
+_LIMITE_DEFAUT_MEMOIRE = "256Mi"
+_REQUETE_DEFAUT_CPU = "50m"
+_REQUETE_DEFAUT_MEMOIRE = "64Mi"
+
+
+def _quota_et_limites(plan: DeploymentPlan) -> str:
+    """Émet un ``ResourceQuota`` et un ``LimitRange`` pour le namespace du plan.
+
+    Le ``ResourceQuota`` vaut **exactement** le budget cumulé du plan :
+    - ni plus (on ne gèlerait pas de la capacité inutilisée),
+    - ni moins (un quota sous-alloué bloquerait le déploiement qu'il encadre
+      en refusant la création des pods au-delà du quota).
+    La ``LimitRange`` applique des défauts raisonnables à tout conteneur qui
+    n'aurait pas déclaré ses propres ressources.
+    """
+    budget = _budget_du_plan(plan)
+
+    cpu_req_m = budget["requests"]["cpu_m"]
+    mem_req_mib = budget["requests"]["mem_mib"]
+    cpu_lim_m = budget["limits"]["cpu_m"]
+    mem_lim_mib = budget["limits"]["mem_mib"]
+
+    parts: list[str] = []
+    # ResourceQuota : couvre simultanément requests et limits pour CPU et mémoire.
+    parts.append("---\n")
+    parts.append("apiVersion: v1\n")
+    parts.append("kind: ResourceQuota\n")
+    parts.append("metadata:\n")
+    parts.append("  name: forgeai-quota\n")
+    parts.append(f"  namespace: {NAMESPACE}\n")
+    parts.append("spec:\n")
+    parts.append("  hard:\n")
+    parts.append(f'    requests.cpu: "{cpu_req_m}m"\n')
+    parts.append(f'    requests.memory: "{mem_req_mib}Mi"\n')
+    parts.append(f'    limits.cpu: "{cpu_lim_m}m"\n')
+    parts.append(f'    limits.memory: "{mem_lim_mib}Mi"\n')
+
+    # LimitRange : un seul entrée de type Container, défauts requests/limits.
+    # Sans elle, un pod sans resources serait accepté tel quel et pourrait
+    # consommer à lui seul tout le quota du namespace.
+    parts.append("---\n")
+    parts.append("apiVersion: v1\n")
+    parts.append("kind: LimitRange\n")
+    parts.append("metadata:\n")
+    parts.append("  name: forgeai-limits\n")
+    parts.append(f"  namespace: {NAMESPACE}\n")
+    parts.append("spec:\n")
+    parts.append("  limits:\n")
+    parts.append("    - type: Container\n")
+    parts.append("      default:\n")
+    parts.append(f'        cpu: "{_LIMITE_DEFAUT_CPU}"\n')
+    parts.append(f'        memory: "{_LIMITE_DEFAUT_MEMOIRE}"\n')
+    parts.append("      defaultRequest:\n")
+    parts.append(f'        cpu: "{_REQUETE_DEFAUT_CPU}"\n')
+    parts.append(f'        memory: "{_REQUETE_DEFAUT_MEMOIRE}"\n')
+
+    return "".join(parts)
+
+
+def _verifier_capacite(plan: DeploymentPlan, capacite: "CapaciteCluster | None") -> None:
+    """Vérifie que le budget agrégé du plan tient dans la capacité déclarée.
+
+    Rétro-compatibilité stricte : si ``capacite`` vaut ``None``, on ne peut
+    rien vérifier (l'appelant n'a pas déclaré de cluster cible) et la fonction
+    retourne silencieusement. Sinon, on compare les **limits** (et non les
+    requests) car c'est le plafond absolu que Kubernetes appliquera au pod :
+    si les limits dépassent la capacité, le pod sera de toute façon throttlé
+    ou OOMKill, indépendamment du quota du namespace.
+
+    Les deux contrôles (CPU, mémoire) sont indépendants : un dépassement
+    uniquement mémoire reste un dépassement et doit être signalé.
+    """
+    if capacite is None:
+        return
+
+    budget = _budget_du_plan(plan)
+    cpu_requis = budget["limits"]["cpu_m"]
+    memoire_requise = budget["limits"]["mem_mib"]
+
+    if cpu_requis > capacite.cpu_millicores:
+        raise QuotaError(
+            "ERR_QUOTA_CPU_DEPASSE: le plan requiert "
+            f"{cpu_requis}m CPU mais le cluster n'en déclare que "
+            f"{capacite.cpu_millicores}m."
+        )
+    if memoire_requise > capacite.memoire_mib:
+        raise QuotaError(
+            "ERR_QUOTA_MEMOIRE_DEPASSEE: le plan requiert "
+            f"{memoire_requise} MiB de mémoire mais le cluster n'en déclare "
+            f"que {capacite.memoire_mib} MiB."
+        )
+
+
 def render_k3s(plan: DeploymentPlan, node: str | None = None,
                service_type: str = "NodePort",
                config_files: dict[str, str] | None = None,
-               inventaire: tuple[NodeInventaire, ...] | None = None) -> str:
+               inventaire: tuple[NodeInventaire, ...] | None = None,
+               capacite: CapaciteCluster | None = None) -> str:
     """Manifestes Kubernetes STANDARD (valables k3s ET k8s — même API). `node` épingle les pods
     sur un hôte (profil Minimal = single-node) ; `svc.node == "auto"` laisse le scheduler décider.
     `service_type` : NodePort (défaut, portable partout, k3s/edge) ou LoadBalancer (cloud/k8s).
     `config_files` : mapping {basename: contenu} pour les bind-mounts de fichiers de config
     (ex. litellm-config.yaml) émis comme ConfigMap et montés via subPath."""
+    # K8S-027 : refuser AVANT de produire quoi que ce soit. Rendre puis échouer laisserait
+    # l'utilisateur appliquer un manifeste dont les pods resteront Pending sans cause lisible.
+    _verifier_capacite(plan, capacite)
+
     if service_type not in _SERVICE_TYPES:
         raise ValueError(
             f"service_type invalide : {service_type!r} (attendu {sorted(_SERVICE_TYPES)})")
@@ -757,6 +932,10 @@ automountServiceAccountToken: false
     # K8S-023 : refus par défaut Ingress ET Egress + allowlists dérivées des dépendances
     # DÉCLARÉES du plan. Remplace l'unique politique `forgeai-default`, qui laissait l'egress
     # totalement libre et autorisait un accès intra-namespace universel.
+    # K8S-027 : quota et LimitRange dérivés du budget RÉEL du plan (somme des
+    # ressources_effectives, RES-012B). Sans LimitRange, un conteneur ne déclarant aucune
+    # ressource échapperait au quota et pourrait l'épuiser à lui seul.
+    parts.append(_quota_et_limites(plan))
     parts.append(_network_policies(plan))
     used: set[int] = set()
     for svc in plan.services:
diff --git a/tests/test_k3s_hardening.py b/tests/test_k3s_hardening.py
index ea40b80..bd18320 100644
--- a/tests/test_k3s_hardening.py
+++ b/tests/test_k3s_hardening.py
@@ -343,3 +343,143 @@ def test_service_sans_dependance_ne_recoit_aucune_sortie():
                   if p["spec"].get("podSelector", {}).get("matchLabels", {}).get("app") == "isole"]
     assert not any(p["spec"].get("egress") for p in pour_isole), \
         "aucune dépendance déclarée : aucune sortie ne doit être ouverte"
+
+
+# ---------------------------------------------------------------------------
+# K8S-027 / FAI-U-027 — quotas et limites par namespace, dérivés du budget réel du plan.
+# Aucun ResourceQuota ni LimitRange n'était émis : rien ne bornait ce qu'un namespace
+# pouvait consommer, et rien ne refusait un plan dépassant la capacité du cluster AVANT
+# application. Le budget est calculable depuis RES-012B (ressources par service).
+# ---------------------------------------------------------------------------
+from forgeai.core.models import CapaciteCluster, QuotaError
+
+
+def _plan_trois_services():
+    """llm 4000m/8Gi + db 1000m/2Gi + sidecar 500m/512Mi = 5500m / 10752Mi de limites."""
+    return _plan([
+        _svc(name="ollama", image="o:1", host_port=1, container_port=1, resource_class="llm"),
+        _svc(name="qdrant", image="q:1", host_port=2, container_port=2, resource_class="db"),
+        _svc(name="litellm", image="l:1", host_port=3, container_port=3, resource_class="sidecar"),
+    ])
+
+
+def _quota(manifeste: str) -> dict:
+    for d in yaml.safe_load_all(manifeste):
+        if d and d.get("kind") == "ResourceQuota":
+            return d
+    raise AssertionError("aucun ResourceQuota dans le manifeste")
+
+
+def _limitrange(manifeste: str) -> dict:
+    for d in yaml.safe_load_all(manifeste):
+        if d and d.get("kind") == "LimitRange":
+            return d
+    raise AssertionError("aucun LimitRange dans le manifeste")
+
+
+def test_quota_derive_du_budget_reel_du_plan():
+    """Critère 1 — le quota doit refléter ce que le plan consomme VRAIMENT, pas un chiffre
+    arbitraire. Il est donc dérivé de la somme des `ressources_effectives` (RES-012B)."""
+    out = render_k3s(_plan_trois_services())
+    spec = _quota(out)["spec"]["hard"]
+    assert spec["limits.cpu"] == "5500m", f"somme des limites CPU : {spec['limits.cpu']}"
+    assert spec["limits.memory"] == "10752Mi", f"somme des limites mémoire : {spec['limits.memory']}"
+    assert "requests.cpu" in spec and "requests.memory" in spec
+
+
+def test_limitrange_present_et_coherent():
+    """Critère 1 (suite) — le LimitRange borne un conteneur qui n'aurait déclaré aucune
+    ressource ; sans lui, un pod sans limites échappe au quota et l'épuise."""
+    lr = _limitrange(render_k3s(_plan_trois_services()))
+    limites = lr["spec"]["limits"][0]
+    assert limites["type"] == "Container"
+    assert "default" in limites and "defaultRequest" in limites
+
+
+def test_le_quota_n_empeche_pas_un_bundle_valide():
+    """Critère 2 — GARDE CONTRE LA SOUS-ALLOCATION. Un quota calculé au plus juste bloquerait
+    le déploiement qu'il est censé encadrer : le quota doit être >= au besoin du plan."""
+    out = render_k3s(_plan_trois_services())
+    spec = _quota(out)["spec"]["hard"]
+    cpu_quota = int(spec["limits.cpu"].rstrip("m"))
+    mem_quota = int(spec["limits.memory"].rstrip("Mi"))
+    assert cpu_quota >= 5500, "le quota CPU doit couvrir le besoin du plan"
+    assert mem_quota >= 10752, "le quota mémoire doit couvrir le besoin du plan"
+
+
+def test_plan_depassant_la_capacite_est_refuse_avant_application():
+    """Critère 3 — un plan qui dépasse la capacité du cluster doit être refusé AVANT kubectl,
+    avec sa cause chiffrée. Sinon les pods restent Pending sans explication."""
+    petite = CapaciteCluster(cpu_millicores=2000, memoire_mib=4096)
+    with pytest.raises(QuotaError) as exc:
+        render_k3s(_plan_trois_services(), capacite=petite)
+    message = str(exc.value)
+    assert "5500" in message and "2000" in message, \
+        f"l'erreur doit chiffrer le besoin ET la capacité : {message}"
+
+
+def test_plan_tenant_dans_la_capacite_est_accepte():
+    """Contrôle positif : une capacité suffisante laisse passer le plan."""
+    large = CapaciteCluster(cpu_millicores=16000, memoire_mib=32768)
+    out = render_k3s(_plan_trois_services(), capacite=large)
+    assert _quota(out)["spec"]["hard"]["limits.cpu"] == "5500m"
+
+
+def test_sans_capacite_declaree_aucun_refus():
+    """Rétro-compatibilité : sans capacité fournie, on ne peut rien vérifier — le rendu
+    reste celui d'avant. La vérification est une capacité ajoutée, pas une rupture."""
+    out = render_k3s(_plan_trois_services())
+    assert _quota(out)["spec"]["hard"]["limits.cpu"] == "5500m"
+
+
+def test_budget_incomplet_leve_au_lieu_de_sous_compter():
+    """Objection de revue (Gemini) : `_budget_du_plan` ignorait SILENCIEUSEMENT une catégorie
+    dont une seule des deux ressources manquait. Un budget sous-compté produit un quota trop
+    petit — exactement la sous-allocation que le critère 2 interdit, et qui bloquerait le
+    déploiement que le quota est censé encadrer.
+
+    L'état est inatteignable via `ServiceSpec` (RES-012B valide en fail-fast), mais une branche
+    défensive qui fausse un budget en silence est PIRE que pas de branche du tout : elle
+    convertit un état impossible en quota faux plutôt qu'en erreur visible."""
+    from forgeai.renderers.k3s import _budget_du_plan
+    svc = _svc(name="casse", image="c:1", host_port=1, container_port=1)
+    object.__setattr__(svc, "ressources_effectives",
+                       {"requests": {"cpu": "100m"},          # `memory` absent
+                        "limits": {"cpu": "1000m", "memory": "1Gi"}})
+    plan = _plan([svc])
+    with pytest.raises(ValueError, match="ERR_QUOTA_RESSOURCES_INCOMPLETES"):
+        _budget_du_plan(plan)
+
+
+def test_depassement_memoire_seul_est_exerce():
+    """Objection de DeepSeek : le test de dépassement utilisait un cluster trop petit en CPU ET
+    en mémoire — seule la première branche s'exécutait, `ERR_QUOTA_MEMOIRE_DEPASSEE` n'était
+    jamais atteinte. Ici le CPU suffit largement, seule la mémoire manque."""
+    cap = CapaciteCluster(cpu_millicores=16000, memoire_mib=4096)   # CPU OK, mémoire non
+    with pytest.raises(QuotaError) as exc:
+        render_k3s(_plan_trois_services(), capacite=cap)
+    message = str(exc.value)
+    assert "ERR_QUOTA_MEMOIRE_DEPASSEE" in message
+    assert "10752" in message and "4096" in message, \
+        f"le message doit chiffrer le besoin ET la capacité mémoire : {message}"
+
+
+def test_categorie_a_none_leve_proprement():
+    """Objection de Tencent : `res.get(categorie, {})` renvoie `None` si la clé EXISTE avec la
+    valeur `None` — le `.get("cpu")` qui suit lève alors `AttributeError`, une erreur technique
+    opaque, au lieu du `ValueError` explicite prévu. Un défaut de données doit produire un
+    message qui nomme sa cause, pas une trace d'attribut manquant."""
+    from forgeai.renderers.k3s import _budget_du_plan
+    svc = _svc(name="nul", image="n:1", host_port=1, container_port=1)
+    object.__setattr__(svc, "ressources_effectives", {"requests": None, "limits": None})
+    with pytest.raises(ValueError, match="ERR_QUOTA_RESSOURCES_INCOMPLETES"):
+        _budget_du_plan(_plan([svc]))
+
+
+def test_quota_affirme_les_valeurs_exactes_des_requests():
+    """Objection de Tencent : le test n'affirmait que la PRÉSENCE de `requests.*`, pas leurs
+    valeurs — une somme fausse serait passée inaperçue. llm 1000m/4Gi + db 250m/512Mi +
+    sidecar 100m/128Mi = 1350m / 4736Mi."""
+    spec = _quota(render_k3s(_plan_trois_services()))["spec"]["hard"]
+    assert spec["requests.cpu"] == "1350m"
+    assert spec["requests.memory"] == "4736Mi"

# ==== ROUGE ====
[ROUGE] sur origin/main (ba18ef0) — reproduction exécutée.

  objets rendus : Namespace x1, ServiceAccount x1, NetworkPolicy x2, Deployment x3, Service x3
  ResourceQuota : ABSENT
  LimitRange    : ABSENT

Conséquences :
  - rien ne borne ce qu'un namespace peut consommer ;
  - un conteneur ne déclarant aucune ressource n'est encadré par rien ;
  - un plan dépassant la capacité du cluster est rendu SANS broncher, appliqué, puis ses pods
    restent Pending sans cause lisible — l'utilisateur découvre le problème en production.

Le budget était pourtant DÉJÀ calculable grâce à RES-012B (ressources par service) :
  ollama  llm      limits 4000m /   8Gi
  qdrant  db       limits 1000m /   2Gi
  litellm sidecar  limits  500m / 512Mi
  TOTAL                   5500m / 10752Mi

Tests rouges : ImportError — ni CapaciteCluster ni QuotaError n'existaient.

# ==== COMPORTEMENT ====
# K8S-027 — quotas derives du budget REEL du plan (execution reelle)

## Budget du plan (somme des ressources_effectives, RES-012B)
  ollama   llm        limits   4000m /    8Gi
  qdrant   db         limits   1000m /    2Gi
  litellm  sidecar    limits    500m /  512Mi

## ResourceQuota emis
    limits.cpu: 5500m
    limits.memory: 10752Mi
    requests.cpu: 1350m
    requests.memory: 4736Mi

## LimitRange emis (type: Container )
    default       : {'cpu': '250m', 'memory': '256Mi'}
    defaultRequest: {'cpu': '50m', 'memory': '64Mi'}
    => sans lui, un conteneur sans ressources declarees echapperait au quota

## Garde contre le depassement de capacite
  cluster trop petit (2000m/4096Mi)    -> REFUSE
      ERR_QUOTA_CPU_DEPASSE: le plan requiert 5500m CPU mais le cluster n'en déclare que 2000m.
  cluster suffisant (16000m/32768Mi)   -> ACCEPTE
  sans capacite declaree               -> ACCEPTE (retro-compat)

# ==== GATES ====
=== GREEN ciblé ===
.......................................                                  [100%]

=== GREEN suite complète ===
........................................................................ [ 99%]
...                                                                      [100%]

=== gates ===
NO-STUB-SCAN : OK (265 fichiers scannés, zéro violation)
[90m9:53PM[0m [32mINF[0m [1mno leaks found[0m
