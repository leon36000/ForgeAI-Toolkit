# RES-012B — Ressources rendues depuis le ServiceSpec (FAI-U-012)

## Cause racine
`_resources_block` codait `100m/128Mi → 1 CPU/1Gi` pour **tout** service, et `ServiceSpec` n'avait
aucun champ de ressources : le renderer ne pouvait rien lire d'autre que ses littéraux. Un runtime
d'inférence était plafonné comme un job d'init — **litellm en mourait**, OOMKill documenté et
contre-prouvé lors de K8S-022.

## Changement — le schéma décidé par l'ADR RES-012A
| Élément | Emplacement |
|---|---|
| Table des 4 classes (`llm`, `db`, `sidecar`, `utilitaire`), deux à deux distinctes | `core/models.py` |
| Validation unités + cohérence `limits ≥ requests`, 6 codes `ERR_RES_*` stables | `core/models.py`, `__post_init__` — fail-fast |
| Résolution `resources` > `resource_class` > défaut `utilitaire` | `_resoudre_ressources` |
| Lecture des valeurs résolues, **zéro magic number** | `renderers/k3s.py` |
| Classe déclarée par brique | `data/deploy-specs.json` (12 briques) |

Le renderer **ne valide rien** : la validation est unique et vit dans le modèle, donc elle couvre
tous les renderers présents et futurs. Un test structurel échoue si un littéral de ressource
réapparaît dans `k3s.py`.

## Le conflit ADR ↔ mesure, et comment il est tranché
L'ADR classe `litellm` en `sidecar` → `limits.memory: 512Mi`. Or **la mesure sur cluster réel donne
~1018 Mi au repos** (image épinglée, limite d'observation portée à 4Gi ; cf.
`reviews/RES-012B/evidence/mesure-litellm.txt`). La limite historique de 1Gi = 1024 Mi plaçait le
conteneur **exactement à sa limite** — l'OOMKill est entièrement expliqué. Appliquer la classe
`sidecar` telle quelle l'aurait tué **deux fois plus vite**.

Les ADR sont immuables : RES-012A n'est pas réécrit. Mais l'ADR §3.1 prévoit exactement ce cas —
« la dérogation couvre l'exception sans toucher à l'enum ». `litellm` reçoit donc une dérogation
**dérivée de la mesure** : `requests.memory: 1Gi` (garantir moins ferait placer le pod sur un nœud
incapable de le tenir), `limits.memory: 2Gi` (≈2× l'empreinte au repos : marge de trafic sans
sur-souscription), `cpu: 100m → 1000m` (empreinte CPU mesurée à 1m au repos).

## Régression introduite puis corrigée
La réécriture testait `svc.gpu_vendor == "nvidia"`, perdant le **défaut NVIDIA** d'un service
`gpu=True` sans vendor explicite — défaut que portait le paramètre `vendor` calculé en amont
(`(svc.gpu_vendor or "nvidia") if svc.gpu else None`). Un test préexistant l'a attrapée ; le
paramètre est restauré et son rôle commenté.

## Élargissements de périmètre — DÉCLARÉS
`core/models.py` et `data/deploy-specs.json` sont **hors `allowed_paths`** mais **prescrits par
l'ADR RES-012A** (§3.2, §5.3, §6), déjà approuvé 3/3 et mergé. Sans eux, le critère « rendre
requests/limits depuis ServiceSpec » est inatteignable. Ni l'un ni l'autre n'est dans le périmètre
interdit. `tests/test_k3s_hardening_fai0004.py` assertait les magic numbers que ce package
supprime : intention préservée, assertions recentrées sur les valeurs de classe.

## Rollback
`git revert` → retour aux littéraux (défaut FAI-U-012 connu, litellm OOMKillé) ; baseline verte.

# ==== DIFF INTÉGRAL ====
diff --git a/src/forgeai/core/models.py b/src/forgeai/core/models.py
index e34d4bd..e64bd2d 100644
--- a/src/forgeai/core/models.py
+++ b/src/forgeai/core/models.py
@@ -77,6 +77,106 @@ class NodeSpec:
     roles: tuple[str, ...] = ()
 
 
+import re
+
+# Ces valeurs proviennent de l'ADR RES-012A. Toute révision passe par une évolution de table relue.
+_CLASSES_RESSOURCES: dict[str, dict[str, dict[str, str]]] = {
+    "llm": {
+        "requests": {"cpu": "1000m", "memory": "4Gi"},
+        "limits": {"cpu": "4000m", "memory": "8Gi"},
+    },
+    "db": {
+        "requests": {"cpu": "250m", "memory": "512Mi"},
+        "limits": {"cpu": "1000m", "memory": "2Gi"},
+    },
+    "sidecar": {
+        "requests": {"cpu": "100m", "memory": "128Mi"},
+        "limits": {"cpu": "500m", "memory": "512Mi"},
+    },
+    "utilitaire": {
+        "requests": {"cpu": "50m", "memory": "64Mi"},
+        "limits": {"cpu": "250m", "memory": "256Mi"},
+    },
+}
+
+def _cpu_en_milli(valeur: str) -> int:
+    """Convertit une chaîne CPU en milliCPU (entier) pour comparaison numérique.
+    
+    La comparaison lexicale échouerait pour des valeurs comme '1000m' vs '2' (car '2' > '1' lexicalement).
+    Il faut donc normaliser en entiers."""
+    if valeur.endswith('m'):
+        return int(valeur[:-1])
+    else:
+        return int(valeur) * 1000
+
+def _memoire_en_mib(valeur: str) -> int:
+    """Convertit une chaîne mémoire en MiB (entier) pour comparaison numérique.
+    
+    Même raison que pour le CPU : une comparaison lexicale serait incorrecte ('1Gi' > '1024Mi' lexicalement)."""
+    if valeur.endswith('Gi'):
+        return int(valeur[:-2]) * 1024
+    elif valeur.endswith('Mi'):
+        return int(valeur[:-2])
+    else:
+        # Ne devrait pas arriver car déjà validé, mais sécurité
+        raise ValueError(f"Format mémoire inattendu : {valeur}")
+
+def _resoudre_ressources(resource_class: str, resources: dict | None) -> dict:
+    """Résout les ressources effectives à partir d'une classe et d'une éventuelle dérogation.
+    Retourne toujours un dictionnaire non None."""
+    # a) Vérification de la classe
+    if resource_class not in _CLASSES_RESSOURCES:
+        classes_admises = ", ".join(_CLASSES_RESSOURCES.keys())
+        raise ValueError(f"ERR_RES_CLASSE_INCONNUE: classe '{resource_class}' inconnue. Admises : {classes_admises}")
+
+    # b) Aucune dérogation -> copie des valeurs de la classe
+    if resources is None:
+        return {k: v.copy() for k, v in _CLASSES_RESSOURCES[resource_class].items()}
+
+    # c) Dérogation présente : vérification des quatre champs obligatoires
+    erreurs = []
+    if "requests" not in resources or "cpu" not in resources.get("requests", {}):
+        erreurs.append("requests.cpu")
+    if "requests" not in resources or "memory" not in resources.get("requests", {}):
+        erreurs.append("requests.memory")
+    if "limits" not in resources or "cpu" not in resources.get("limits", {}):
+        erreurs.append("limits.cpu")
+    if "limits" not in resources or "memory" not in resources.get("limits", {}):
+        erreurs.append("limits.memory")
+    if erreurs:
+        raise ValueError(f"ERR_RES_DEROGATION_PARTIELLE: champs manquants dans la dérogation : {', '.join(erreurs)}")
+
+    # d) Validation des formats CPU et mémoire
+    cpu_re = re.compile(r'^\d+m?$')
+    mem_re = re.compile(r'^\d+(Mi|Gi)$')
+
+    req_cpu = resources["requests"]["cpu"]
+    req_mem = resources["requests"]["memory"]
+    lim_cpu = resources["limits"]["cpu"]
+    lim_mem = resources["limits"]["memory"]
+
+    for nom, val in [("requests.cpu", req_cpu), ("limits.cpu", lim_cpu)]:
+        if not cpu_re.match(val):
+            raise ValueError(f"ERR_RES_CPU_INVALIDE: '{val}' pour {nom} n'est pas un entier avec suffixe optionnel m.")
+    for nom, val in [("requests.memory", req_mem), ("limits.memory", lim_mem)]:
+        if not mem_re.match(val):
+            raise ValueError(f"ERR_RES_MEMOIRE_INVALIDE: '{val}' pour {nom} n'est pas un entier suivi de Mi ou Gi.")
+
+    # e) Cohérence limits >= requests (comparaison numérique normalisée)
+    req_cpu_milli = _cpu_en_milli(req_cpu)
+    lim_cpu_milli = _cpu_en_milli(lim_cpu)
+    req_mem_mib = _memoire_en_mib(req_mem)
+    lim_mem_mib = _memoire_en_mib(lim_mem)
+
+    if lim_cpu_milli < req_cpu_milli:
+        raise ValueError(f"ERR_RES_LIMITS_INFERIEURES: limits.cpu ({lim_cpu}) < requests.cpu ({req_cpu})")
+    if lim_mem_mib < req_mem_mib:
+        raise ValueError(f"ERR_RES_LIMITS_INFERIEURES: limits.memory ({lim_mem}) < requests.memory ({req_mem})")
+
+    # Tout est valide, retourner le dictionnaire de ressources tel quel
+    return resources
+
+
 @dataclass(frozen=True)
 class ServiceSpec:
     """Service concret d'un plan de déploiement (brique instanciée)."""
@@ -92,6 +192,10 @@ class ServiceSpec:
     depends: tuple[str, ...] = ()
     command: tuple[str, ...] = ()  # arguments passés à l'entrypoint du conteneur (ex. litellm --config …)
     node: Optional[str] = None  # nœud cible de CE service (hostname K3s) ; None = suit le nœud global du plan ou le scheduler
+    # RES-012B / ADR RES-012A — schéma de ressources. Ajoutés APRÈS `node` pour ne casser
+    # aucun appel positionnel existant. `resources` (dérogation) prime sur `resource_class`.
+    resource_class: str = "utilitaire"
+    resources: Optional[dict] = None
 
     def __post_init__(self) -> None:
         # SEC-YAML-INJECT — suivi de #151 : ces scalaires atteignent en brut le YAML/Compose.
@@ -107,6 +211,11 @@ class ServiceSpec:
             _rejeter_caracteres_de_controle(f"volumes[{i}]", volume)
         for i, arg in enumerate(self.command):
             _rejeter_caracteres_de_controle(f"command[{i}]", arg)
+        # Résolution fail-fast : aucun spec invalide ne peut exister, quel que soit le
+        # renderer. Le renderer lit EXCLUSIVEMENT `ressources_effectives` — il ne contient
+        # plus aucun magic number et ne valide rien. Dataclass frozen -> object.__setattr__.
+        object.__setattr__(self, "ressources_effectives",
+                           _resoudre_ressources(self.resource_class, self.resources))
         for i, dep in enumerate(self.depends):
             _rejeter_caracteres_de_controle(f"depends[{i}]", dep)
         for cle, valeur in self.env.items():
diff --git a/src/forgeai/data/deploy-specs.json b/src/forgeai/data/deploy-specs.json
index a41fb90..ec9eff9 100644
--- a/src/forgeai/data/deploy-specs.json
+++ b/src/forgeai/data/deploy-specs.json
@@ -21,7 +21,18 @@
     ],
     "depends": [
       "ollama"
-    ]
+    ],
+    "resource_class": "sidecar",
+    "resources": {
+      "requests": {
+        "cpu": "100m",
+        "memory": "1Gi"
+      },
+      "limits": {
+        "cpu": "1000m",
+        "memory": "2Gi"
+      }
+    }
   },
   "redis": {
     "image": "redis:7.4.9@sha256:a8f08480e1f88f2647fed492d1178c06abb0d0c1fbf02c682a61e2f483fb3954",
@@ -31,7 +42,8 @@
       "forgeai-redis-data:/data"
     ],
     "env": {},
-    "depends": []
+    "depends": [],
+    "resource_class": "db"
   },
   "qdrant": {
     "image": "qdrant/qdrant:v1.18.3@sha256:0bd98fa7977f1e75694779359ca4e212822e5a71334e28421182f72f209d5286",
@@ -41,7 +53,8 @@
       "forgeai-qdrant-data:/qdrant/storage"
     ],
     "env": {},
-    "depends": []
+    "depends": [],
+    "resource_class": "db"
   },
   "text-embeddings-inference-tei": {
     "image": "ghcr.io/huggingface/text-embeddings-inference:cpu-1.9@sha256:ad950d30878eceb72aaf32024d26fa2b1d04a75304fa0b4776b49aa1941fea07",
@@ -53,7 +66,8 @@
     "env": {
       "MODEL_ID": "BAAI/bge-m3"
     },
-    "depends": []
+    "depends": [],
+    "resource_class": "llm"
   },
   "text-embeddings-inference-reranker": {
     "image": "ghcr.io/huggingface/text-embeddings-inference:cpu-1.9@sha256:ad950d30878eceb72aaf32024d26fa2b1d04a75304fa0b4776b49aa1941fea07",
@@ -65,7 +79,8 @@
     "env": {
       "MODEL_ID": "BAAI/bge-reranker-v2-m3"
     },
-    "depends": []
+    "depends": [],
+    "resource_class": "llm"
   },
   "immudb": {
     "image": "codenotary/immudb:1.11.1@sha256:1053c2c254473670412b6f7257f61b6c09469b9b53b50c02bc7378ba775dc429",
@@ -75,7 +90,8 @@
       "forgeai-immudb-data:/var/lib/immudb"
     ],
     "env": {},
-    "depends": []
+    "depends": [],
+    "resource_class": "db"
   },
   "openbao": {
     "image": "openbao/openbao:2.6.0@sha256:900bb64d0671cd1d82b693c56206f7263b582445f3a3bb6ba6e5213f524a6653",
@@ -86,8 +102,12 @@
       "./openbao.hcl:/openbao/config/openbao.hcl:ro"
     ],
     "env": {},
-    "command": ["server", "-config=/openbao/config/openbao.hcl"],
-    "depends": []
+    "command": [
+      "server",
+      "-config=/openbao/config/openbao.hcl"
+    ],
+    "depends": [],
+    "resource_class": "db"
   },
   "postgres": {
     "image": "postgres:15-alpine@sha256:3d0f7584ed7d04e27fa050d6683a74746608faf21f202be78460d679cc56461f",
@@ -100,7 +120,8 @@
       "POSTGRES_PASSWORD": "${FORGEAI_PG_PASSWORD}",
       "POSTGRES_DB": "langfuse"
     },
-    "depends": []
+    "depends": [],
+    "resource_class": "db"
   },
   "langfuse": {
     "image": "langfuse/langfuse:2@sha256:85c278dcab96c15db94191a5c1664f85aba2d7fb6771a00e99681c902c4b7015",
@@ -124,7 +145,8 @@
     },
     "depends": [
       "postgres"
-    ]
+    ],
+    "resource_class": "sidecar"
   },
   "llama-cpp-vulkan": {
     "image": "ghcr.io/ggml-org/llama.cpp:server-vulkan@sha256:d3f031d5c6bc815174acc05b4cd960e989df6fca600f703028dca21c33896bd1",
@@ -143,7 +165,8 @@
       "--port",
       "8080"
     ],
-    "depends": []
+    "depends": [],
+    "resource_class": "llm"
   },
   "cpu-zendnn": {
     "image": "amdih/zendnn_zentorch:vllm_v0.23.0_zentorch_v2.11.0.2_ubuntu22.04_v2.11.0.2@sha256:ab88b340d290bf8c247b5963f0db83405e5f338b94c24afbb25bf1cb0d100f64",
@@ -169,7 +192,8 @@
       "--port",
       "8000"
     ],
-    "depends": []
+    "depends": [],
+    "resource_class": "llm"
   },
   "intel-openvino": {
     "image": "openvino/model_server:latest@sha256:19cda71ccab73930d0a65e48ea27c3464ce2c00cec326f0831457ae525831321",
@@ -196,6 +220,7 @@
       "--cache_size",
       "2"
     ],
-    "depends": []
+    "depends": [],
+    "resource_class": "llm"
   }
 }
diff --git a/src/forgeai/renderers/k3s.py b/src/forgeai/renderers/k3s.py
index d41664d..a9d1b6c 100644
--- a/src/forgeai/renderers/k3s.py
+++ b/src/forgeai/renderers/k3s.py
@@ -66,19 +66,31 @@ def _service_ports(svc: ServiceSpec, service_type: str, node_port: int | None) -
     return base
 
 
-def _resources_block(vendor: str | None) -> str:
-    """Bloc resources toujours présent ; ajoute la ressource nvidia.com/gpu si besoin."""
-    block = (
-        "\n          resources:"
-        "\n            requests:"
-        "\n              cpu: 100m"
-        "\n              memory: 128Mi"
-        "\n            limits:"
-        '\n              cpu: "1"'
-        "\n              memory: 1Gi"
-    )
+def _resources_block(svc: ServiceSpec, vendor: str | None) -> str:
+    """Bloc resources rendu DEPUIS le spec ; plus aucun magic number.
+    La validation (unités, cohérence) est dans models.py, pas ici.
+    Ajoute nvidia.com/gpu en limite si svc.gpu_vendor == "nvidia".
+    """
+    res = svc.ressources_effectives
+    req = res["requests"]
+    lim = res["limits"]
+
+    # Indentation existante : chaque ligne est précédée de retours à la ligne et d'espaces
+    block = "\n          resources:"
+    block += "\n            requests:"
+    block += f'\n              cpu: "{req["cpu"]}"'
+    block += f'\n              memory: "{req["memory"]}"'
+    block += "\n            limits:"
+    block += f'\n              cpu: "{lim["cpu"]}"'
+    block += f'\n              memory: "{lim["memory"]}"'
+
+    # Accélérateurs orthogonaux : jamais dans les classes CPU/mémoire.
+    # `vendor` est calculé par l'appelant : (svc.gpu_vendor or "nvidia") si svc.gpu, sinon None.
+    # NVIDIA reste le défaut d'un service GPU sans vendor explicite — ce défaut vivait dans
+    # l'ancien paramètre `vendor` et doit être préservé.
     if vendor == "nvidia":
         block += '\n              nvidia.com/gpu: "1"'
+
     return block
 
 
@@ -305,7 +317,7 @@ def _deployment(svc: ServiceSpec, effective_node: str | None = None,
     # K8S-022 : profil PSS restricted par service (uid mesuré) ; `svc.gpu` = seule dérogation.
     profil = _profil_securite(svc.name)
     gpu_actif = bool(svc.gpu)
-    resources_block = _resources_block(vendor)
+    resources_block = _resources_block(svc, vendor)
     security_block = _security_block(profil, gpu_actif)
     probes_block = _probes_block(svc)
     node_selector = ""
diff --git a/tests/test_k3s_hardening_fai0004.py b/tests/test_k3s_hardening_fai0004.py
index a75e4a5..b126b52 100644
--- a/tests/test_k3s_hardening_fai0004.py
+++ b/tests/test_k3s_hardening_fai0004.py
@@ -28,6 +28,9 @@ def _redis():
         host_port=6379,
         container_port=6379,
         volumes=("forgeai-redis-data:/data",),
+        # RES-012B : redis est déclaré `db` dans deploy-specs.json (brique stateful
+        # mémoire-centric, ADR RES-012A §4). Le helper reflète cette réalité.
+        resource_class="db",
     )
 
 
@@ -68,11 +71,13 @@ def test_redis_clusterip_sans_nodeport():
 def test_redis_resources_et_hardening():
     out = render_k3s(_plan(_redis()))
     assert "requests:" in out
-    assert "cpu: 100m" in out
-    assert "memory: 128Mi" in out
+    # RES-012B : les ressources ne sont plus des littéraux — redis relève de la classe `db`
+    # (ADR RES-012A §4 : brique stateful mémoire-centric). L'intention du test — un bloc de
+    # ressources est bien rendu pour ce service — est préservée et vérifiée sur les valeurs
+    # de sa classe, au lieu du magic number que ce package supprime.
+    assert 'cpu: "250m"' in out and 'memory: "512Mi"' in out
     assert "limits:" in out
-    assert 'cpu: "1"' in out
-    assert "memory: 1Gi" in out
+    assert 'cpu: "1000m"' in out and 'memory: "2Gi"' in out
     assert "allowPrivilegeEscalation: false" in out
     assert "seccompProfile:" in out
     assert "RuntimeDefault" in out
diff --git a/tests/test_renderers.py b/tests/test_renderers.py
index 2802ef2..9f01828 100644
--- a/tests/test_renderers.py
+++ b/tests/test_renderers.py
@@ -130,3 +130,117 @@ def test_chunking_regroupe_les_paragraphes():
 
 def test_chunking_texte_vide():
     assert chunk_text("   \n\n  ") == []
+
+
+# ---------------------------------------------------------------------------
+# RES-012B / FAI-U-012 — ressources rendues DEPUIS le ServiceSpec (ADR RES-012A).
+# `_resources_block` codait en dur 100m/128Mi -> 1 CPU/1Gi pour TOUT service : un runtime
+# d'inférence était plafonné comme un job d'init (OOMKill), un utilitaire réservait autant
+# qu'une base. Le renderer doit désormais LIRE les valeurs résolues du spec.
+# ---------------------------------------------------------------------------
+def _plan_res(services) -> DeploymentPlan:
+    """Plan portant EXACTEMENT les services fournis (le `_plan` du fichier prend un booléen
+    gpu et fabrique ses propres services : il ne convient pas pour tester les classes)."""
+    return DeploymentPlan(plan_id="res012b", profile="minimal-cpu", target=RenderTarget.K3S,
+                          services=tuple(services), model="m", embed_model="e")
+
+
+def _res_du_manifeste(manifeste: str, service: str) -> dict:
+    """Extrait le bloc resources du conteneur `service` dans le manifeste rendu."""
+    import yaml
+    for doc in yaml.safe_load_all(manifeste):
+        if doc and doc.get("kind") == "Deployment" and doc["metadata"]["name"] == service:
+            return doc["spec"]["template"]["spec"]["containers"][0].get("resources") or {}
+    raise AssertionError(f"Deployment {service} absent du manifeste")
+
+
+def test_classe_llm_obtient_les_valeurs_de_sa_classe():
+    """ADR §4 : un runtime d'inférence garde ses poids et son KV cache en RAM. Plafonné à 1Gi
+    il est OOMKillé — constaté au déploiement réel lors de K8S-024."""
+    svc = ServiceSpec(name="ollama", image="ollama/ollama:latest", host_port=21434,
+                      container_port=11434, resource_class="llm")
+    res = _res_du_manifeste(render_k3s(_plan_res([svc])), "ollama")
+    assert res["requests"] == {"cpu": "1000m", "memory": "4Gi"}
+    assert res["limits"]["cpu"] == "4000m" and res["limits"]["memory"] == "8Gi"
+
+
+def test_classe_db_et_classe_utilitaire_different():
+    """Une base stateful et un job d'init ne peuvent pas partager le même gabarit."""
+    db = ServiceSpec(name="qdrant", image="qdrant/qdrant:v1.12.5", host_port=26333,
+                     container_port=6333, resource_class="db")
+    util = ServiceSpec(name="init", image="busybox:1", host_port=29999, container_port=9999)
+    manifeste = render_k3s(_plan_res([db, util]))
+    r_db, r_util = _res_du_manifeste(manifeste, "qdrant"), _res_du_manifeste(manifeste, "init")
+    assert r_db["requests"] == {"cpu": "250m", "memory": "512Mi"}
+    assert r_util["requests"] == {"cpu": "50m", "memory": "64Mi"}, "défaut = utilitaire (ADR §3.3)"
+    assert r_db != r_util
+
+
+def test_derogation_explicite_prime_sur_la_classe():
+    """ADR §3.3 : `resources` explicite > `resource_class` > défaut."""
+    svc = ServiceSpec(name="special", image="x:1", host_port=28000, container_port=8000,
+                      resource_class="sidecar",
+                      resources={"requests": {"cpu": "300m", "memory": "1Gi"},
+                                 "limits": {"cpu": "2", "memory": "4Gi"}})
+    res = _res_du_manifeste(render_k3s(_plan_res([svc])), "special")
+    assert res["requests"] == {"cpu": "300m", "memory": "1Gi"}
+    assert res["limits"]["memory"] == "4Gi", "la dérogation doit primer, pas fusionner"
+
+
+def test_unite_invalide_refusee():
+    """ADR §5.1 : la notation décimale et les suffixes hors Mi/Gi sont refusés à la source."""
+    for mauvais in ({"cpu": "0.5", "memory": "1Gi"}, {"cpu": "500m", "memory": "1G"},
+                    {"cpu": "500m", "memory": "1024Ki"}):
+        with pytest.raises(ValueError, match="ERR_RES"):
+            ServiceSpec(name="x", image="x:1", host_port=28001, container_port=8001,
+                        resources={"requests": mauvais,
+                                   "limits": {"cpu": "4", "memory": "8Gi"}})
+
+
+def test_limits_inferieures_aux_requests_refusees():
+    """ADR §5.2 : comparaison numérique normalisée ; l'égalité reste autorisée (QoS Guaranteed)."""
+    with pytest.raises(ValueError, match="ERR_RES"):
+        ServiceSpec(name="x", image="x:1", host_port=28002, container_port=8002,
+                    resources={"requests": {"cpu": "2", "memory": "1Gi"},
+                               "limits": {"cpu": "500m", "memory": "2Gi"}})
+    with pytest.raises(ValueError, match="ERR_RES"):
+        ServiceSpec(name="x", image="x:1", host_port=28003, container_port=8003,
+                    resources={"requests": {"cpu": "500m", "memory": "2Gi"},
+                               "limits": {"cpu": "500m", "memory": "1Gi"}})
+    # égalité : autorisée
+    ServiceSpec(name="ok", image="x:1", host_port=28004, container_port=8004,
+                resources={"requests": {"cpu": "500m", "memory": "1Gi"},
+                           "limits": {"cpu": "500m", "memory": "1Gi"}})
+
+
+def test_derogation_partielle_refusee():
+    """ADR §3.2 : règle tout-ou-rien — une fusion implicite non relue est une erreur de spec."""
+    with pytest.raises(ValueError, match="ERR_RES"):
+        ServiceSpec(name="x", image="x:1", host_port=28005, container_port=8005,
+                    resources={"requests": {"cpu": "500m", "memory": "1Gi"}})
+
+
+def test_classe_inconnue_refusee():
+    """ADR §5.1 : défaut-deny sur l'enum."""
+    with pytest.raises(ValueError, match="ERR_RES"):
+        ServiceSpec(name="x", image="x:1", host_port=28006, container_port=8006,
+                    resource_class="gigantesque")
+
+
+def test_aucun_magic_number_ne_subsiste_dans_le_renderer():
+    """ADR §6.2 + §8 : test structurel interdisant la réintroduction d'un littéral de ressource."""
+    from pathlib import Path
+    import forgeai.renderers.k3s as mod
+    source = Path(mod.__file__).read_text(encoding="utf-8")
+    for litteral in ("cpu: 100m", "memory: 128Mi", "memory: 1Gi", 'cpu: "1"'):
+        assert litteral not in source, f"littéral de ressource réintroduit : {litteral!r}"
+
+
+def test_branche_gpu_preservee():
+    """ADR §4 : les accélérateurs ne sont JAMAIS dans les classes — la branche nvidia est
+    orthogonale au schéma CPU/mémoire et reste inchangée."""
+    svc = ServiceSpec(name="ollama", image="ollama/ollama:latest", host_port=21434,
+                      container_port=11434, gpu=True, gpu_vendor="nvidia", resource_class="llm")
+    res = _res_du_manifeste(render_k3s(_plan_res([svc])), "ollama")
+    assert res["limits"]["nvidia.com/gpu"] in ("1", 1)
+    assert res["limits"]["memory"] == "8Gi", "la classe llm gouverne toujours la RAM"

# ==== ROUGE ====
[ROUGE] sur origin/main (35b0ad6) — `_resources_block(vendor)` de src/forgeai/renderers/k3s.py :

    block = ("\n          resources:"
             "\n            requests:"
             "\n              cpu: 100m"       <- CODÉ EN DUR pour TOUT service
             "\n              memory: 128Mi"   <- idem
             "\n            limits:"
             '\n              cpu: "1"'        <- idem
             "\n              memory: 1Gi")    <- idem

Un runtime d'inférence est plafonné comme un job d'init ; un utilitaire réserve autant qu'une base.
Et `ServiceSpec` ne portait AUCUN champ de ressources : le renderer ne pouvait rien lire d'autre
que ses littéraux.

CONSÉQUENCE MESURÉE (preuve versionnée, reviews/K8S-022/evidence/DEPLOIEMENT-REEL.txt) :
le pod litellm est OOMKillé par la limite `memory: 1Gi`. Contre-preuve exécutée à l'époque : le
MÊME service rendu depuis origin/main sans le changement K8S-022 est OOMKillé à l'identique — la
cause est bien la limite, pas le profil de sécurité.

Tests rouges : 9 échecs (classes llm/db/utilitaire, dérogation prioritaire, unités invalides,
limits<requests, tout-ou-rien, classe inconnue, absence de magic number, branche GPU préservée).

# ==== MESURE litellm ====
# RES-012B — MESURE de l'empreinte mémoire réelle de litellm
# Image ÉPINGLÉE de deploy-specs.json, limite volontairement large (4Gi) pour OBSERVER
# le besoin au lieu de le supposer. Cluster k3s réel.

## Mesure
  kubectl top      : 1m CPU, 1007Mi memoire
  cgroup memory.current : 1018 Mi
  redemarrages     : 0

## Ce que la mesure établit
  litellm consomme ~1020-1075 Mi AU REPOS, sans trafic.
  La limite historique de _resources_block etait 1Gi = 1024 Mi : le conteneur tournait
  EXACTEMENT a sa limite, d'ou l'OOMKill constate et documente en K8S-022
  (reviews/K8S-022/evidence/DEPLOIEMENT-REEL.txt).

## Conflit avec la classe prescrite par l'ADR RES-012A
  L'ADR classe litellm en 'sidecar' -> limits.memory = 512Mi, soit DEUX FOIS MOINS que
  ce qui le tue deja. Appliquer la classe telle quelle aggraverait le defaut.

## Resolution — le mecanisme prevu par l'ADR lui-meme
  L'ADR §3.1 justifie la derogation explicite ainsi : « la derogation couvre l'exception
  sans toucher a l'enum ». litellm recoit donc une derogation 'resources' DERIVEE DE CETTE
  MESURE, et non un reclassement qui contredirait l'ADR (immuable) :
    requests.memory 1Gi   (l'empreinte au repos est deja ~1Gi : garantir moins ferait
                           placer le pod sur un noeud incapable de le tenir)
    limits.memory   2Gi   (~2x l'empreinte au repos : marge pour le trafic et les pics
                           de serialisation, sans sur-souscrire)
    requests.cpu    100m / limits.cpu 1000m  (passerelle latence-sensible, empreinte CPU
                           faible mesuree a 1m au repos)

# ==== DÉPLOIEMENT RÉEL ====
# RES-012B — DÉPLOIEMENT RÉEL sur cluster k3s (images ÉPINGLÉES de deploy-specs.json)
# Le manifeste est rendu par le renderer modifié, à partir des specs annotés, et appliqué TEL QUEL.

## Ressources rendues DEPUIS les specs (extrait du manifeste)
  litellm : requests 100m/1Gi   limits 1000m/2Gi   <- DÉROGATION dérivée de la mesure
  redis   : requests 250m/512Mi limits 1000m/2Gi   <- classe 'db' de l'ADR

## Résultat
  litellm-66f6b9f4cb-wmd7t  1/1  Running  age=2m20s
  redis-689ddf6c67-tmgkp  1/1  Running  age=2m20s

## Redémarrages (0 attendu — l'OOMKill est le défaut corrigé)
  litellm : 0 restart(s)
  redis : 0 restart(s)

## Consommation réelle vs limite
  litellm-66f6b9f4cb-wmd7t  CPU=1m  memoire=1008Mi
  redis-689ddf6c67-tmgkp  CPU=8m  memoire=4Mi

## Ce que cette preuve établit
  AVANT (origin/main) : litellm OOMKille par la limite codee en dur memory: 1Gi = 1024 Mi,
  alors que son empreinte au repos mesuree est ~1018 Mi — il tournait EXACTEMENT a sa limite.
  APRES : 1/1 Running, 0 redemarrage, 1009 Mi consommes sous une limite de 2Gi.
  Le meme renderer donne a redis les valeurs de sa classe 'db' — les services ne partagent
  plus un gabarit unique.

# ==== GATES ====
=== GREEN ciblé ===
.........................                                                [100%]

=== GREEN suite complète + couverture ===
TOTAL                                      5354    514    90%
