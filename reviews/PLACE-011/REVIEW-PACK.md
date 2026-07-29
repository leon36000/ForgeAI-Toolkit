# PLACE-011 — Placement validé contre l'inventaire réel avant rendu (FAI-U-011)

## Cause racine
Aucun inventaire n'était consulté au rendu. Un workload NVIDIA épinglé sur un nœud CPU-only
produisait un manifeste **syntaxiquement parfait**, envoyé à `kubectl`, qui échouait au scheduling :
le pod restait `Pending`, sans message causal. **L'utilisateur découvrait l'incompatibilité en
production.**

## Changement — un contrat d'inventaire et une validation en amont
| Élément | Rôle |
|---|---|
| `NodeInventaire(hostname, gpu_vendor, vram_mib)` | contrat minimal décrivant ce qu'un nœud peut réellement honorer |
| `PlacementError` | refus AVANT rendu, jamais un manifeste voué à l'échec |
| `valider_placement(svc, inventaire, node_demande)` | valide un nœud imposé, ou sélectionne le premier nœud qualifié en mode auto |
| `ServiceSpec.vram_min_mib` | VRAM minimale exigée, confrontée à l'inventaire |

Le renderer appelle la validation dans sa boucle de services. **Sans inventaire fourni, rien ne
change** : la validation est une capacité ajoutée, pas une rupture.

## Comportement prouvé (exécution réelle, `reviews/PLACE-011/evidence/COMPORTEMENT.txt`)
| demande | verdict |
|---|---|
| NVIDIA sur nœud CPU-only | `ERR_PLACE_CPU_ONLY` |
| AMD sur nœud NVIDIA | `ERR_PLACE_VENDOR_INCOMPATIBLE` — un GPU n'est pas un GPU générique |
| 12288 Mio exigés, nœud à 8192 | `ERR_PLACE_VRAM_INSUFFISANTE` — **les deux chiffres** dans le message |
| Intel, mode auto | `ERR_PLACE_AUCUN_NOEUD_QUALIFIE` — avec la raison de rejet de **chaque** nœud examiné |
| nœud absent de l'inventaire | `ERR_PLACE_NOEUD_INCONNU` — avec la liste des hostnames connus |
| AMD, mode auto | → `n-amd`, le seul qualifié |
| sans inventaire | → inchangé (rétro-compatibilité) |
| service CPU | → jamais contraint par le vendor d'un nœud |

Chaque message est **causal** : ce qui a été demandé, ce qui a été trouvé, pourquoi c'est
incompatible — lisible sans consulter l'inventaire.

## Piège de crew rencontré
Le modèle a rendu un contrat dont la **docstring d'ouverture n'était jamais fermée** (une seule
`"""` dans tout le fichier). Tout le code suivant devenait une chaîne, et l'erreur de syntaxe se
manifestait 90 lignes plus loin, dans une docstring saine de `ServiceSpec` — j'ai d'abord soupçonné
mon indentation à tort. Diagnostic par comptage (nombre impair de `"""`), réparation, et surtout :
un `ast.parse()` **avant écriture** a été ajouté à la procédure d'intégration, pour que du code
non compilable ne corrompe plus un fichier sain.

## Objections de la revue scellée — toutes traitées (tour 1 : APPROVE 3/3)
**Convergence à trois, sur le même point.** Gemini, Grok et DeepSeek ont relevé
INDÉPENDAMMENT que `NodeInventaire` levait `ERR_PLACE_VENDOR_INCONNU` pour un hostname vide et une
VRAM négative — deux cas étrangers au vendor. Ironie utile : ce package existe pour produire des
erreurs causales, et son propre contrat en portait une trompeuse. Trois codes distincts désormais :
`ERR_PLACE_HOSTNAME_INVALIDE`, `ERR_PLACE_VRAM_INVALIDE`, `ERR_PLACE_VENDOR_INCONNU`.

**DeepSeek** : un tuple vide passait pour une absence d'inventaire. `None` = « je ne sais pas » ;
`()` = « je sais, et il n'y a rien ». Le correctif du contrat ne suffisait pas — mon propre câblage
du renderer testait `if inventaire:` et court-circuitait la validation avant de l'appeler ; corrigé
en `is not None`. Sans le test rouge, je l'aurais manqué.

**Grok** : `ERR_PLACE_NOEUD_INCONNU` était démontré dans les preuves d'exécution mais aucun test ne
le couvrait. Le test ajouté passe du premier coup — la fonctionnalité était là, mais **un
comportement prouvé une fois n'est pas un comportement protégé**. Même famille d'erreur que le
test-sur-chemin-inventé de RAG-005, vue par l'autre bout : là un test sans comportement, ici un
comportement sans test.

## Rollback
`git revert` → retour au rendu sans validation (défaut FAI-U-011 connu) ; baseline verte.

# ==== DIFF INTÉGRAL ====
diff --git a/src/forgeai/core/models.py b/src/forgeai/core/models.py
index e64bd2d..1223f27 100644
--- a/src/forgeai/core/models.py
+++ b/src/forgeai/core/models.py
@@ -177,6 +177,116 @@ def _resoudre_ressources(resource_class: str, resources: dict | None) -> dict:
     return resources
 
 
+class PlacementError(ValueError):
+    """Levée lorsqu'un placement est refusé AVANT rendu : aucun nœud de
+    l'inventaire ne peut honorer les contraintes du service. Refuser ici
+    évite l'émission d'un manifeste voué à l'échec silencieux au scheduling
+    k3s : la validation sort de l'inventaire, pas du cluster.
+    """
+
+
+@dataclass(frozen=True)
+class NodeInventaire:
+    hostname: str
+    gpu_vendor: Optional[str] = None
+    vram_mib: int = 0
+
+    def __post_init__(self) -> None:
+        if not self.hostname or not self.hostname.strip():
+            raise ValueError(
+                "ERR_PLACE_HOSTNAME_INVALIDE : hostname vide ou uniquement des espaces")
+        _rejeter_caracteres_de_controle("hostname", self.hostname)
+        if self.vram_mib < 0:
+            raise ValueError(
+                f"ERR_PLACE_VRAM_INVALIDE : vram_mib négatif ({self.vram_mib}), "
+                f"attendu entier >= 0")
+        vendors_autorises = {"nvidia", "amd", "intel", None}
+        if self.gpu_vendor not in vendors_autorises:
+            raise ValueError(
+                f"ERR_PLACE_VENDOR_INCONNU : vendor '{self.gpu_vendor}' "
+                f"inconnu (autorisés : nvidia, amd, intel, None)")
+
+
+def valider_placement(svc, inventaire, node_demande):
+    # Pas d'inventaire : on ne peut rien valider, on laisse passer pour ne
+    # pas casser la rétro-compatibilité — c'est une absence d'information,
+    # pas une rupture de contrat. Le scheduling k3s tranchera.
+    # Distinction sémantique entre absence d'inventaire et inventaire vide :
+    #   - None  = « je ne sais pas » (aucune info fournie, rétro-compatibilité : on laisse passer)
+    #   - ()    = « je sais, et il n'y a rien » (l'appelant AFFIRME qu'aucun nœud n'est dispo)
+    if inventaire is None:
+        return node_demande
+
+    if not inventaire:
+        # Inventaire explicite mais vide : on ne peut honorer un service GPU,
+        # mais un service CPU n'a pas besoin d'un nœud particulier.
+        if getattr(svc, "gpu", False):
+            raise PlacementError(
+                "ERR_PLACE_AUCUN_NOEUD_QUALIFIE : l'inventaire fourni ne contient "
+                "aucun nœud, placement d'un service GPU impossible")
+        return node_demande
+
+    # Service CPU : le vendor d'un nœud ne le concerne jamais. Aucune raison
+    # de contraindre un service sans GPU sur un hôte GPU-only.
+    if not svc.gpu:
+        return node_demande
+
+    hostnames = tuple(n.hostname for n in inventaire)
+
+    if node_demande is not None and node_demande != "auto":
+        # Nœud explicitement demandé : on l'audite point par point.
+        noeud = next(
+            (n for n in inventaire if n.hostname == node_demande), None)
+        if noeud is None:
+            raise PlacementError(
+                f"ERR_PLACE_NOEUD_INCONNU : nœud '{node_demande}' absent de "
+                f"l'inventaire (connus : {', '.join(hostnames) or 'aucun'})")
+        if noeud.gpu_vendor is None:
+            raise PlacementError(
+                f"ERR_PLACE_CPU_ONLY : le service '{svc.name}' exige un GPU "
+                f"(vendor demandé : {svc.gpu_vendor}) mais le nœud "
+                f"'{noeud.hostname}' est CPU-only")
+        if svc.gpu_vendor is not None and noeud.gpu_vendor != svc.gpu_vendor:
+            raise PlacementError(
+                f"ERR_PLACE_VENDOR_INCOMPATIBLE : service '{svc.name}' "
+                f"demande le vendor '{svc.gpu_vendor}' mais le nœud "
+                f"'{noeud.hostname}' expose '{noeud.gpu_vendor}'")
+        if (svc.vram_min_mib is not None
+                and svc.vram_min_mib > noeud.vram_mib):
+            raise PlacementError(
+                f"ERR_PLACE_VRAM_INSUFFISANTE : service '{svc.name}' exige "
+                f"{svc.vram_min_mib} Mio de VRAM mais le nœud "
+                f"'{noeud.hostname}' n'en expose que {noeud.vram_mib} Mio")
+        return node_demande
+
+    # Mode auto : parcours déterministe, on retient le PREMIER nœud dont le
+    # vendor correspond ET dont la VRAM suffit. L'ordre de l'inventaire est
+    # l'ordre de préférence : c'est l'auteur du manifeste qui le fixe.
+    candidats_examines = []
+    for noeud in inventaire:
+        raison = None
+        if noeud.gpu_vendor is None:
+            raison = "CPU-only"
+        elif (svc.gpu_vendor is not None
+              and noeud.gpu_vendor != svc.gpu_vendor):
+            raison = f"vendor '{noeud.gpu_vendor}' ≠ demandé '{svc.gpu_vendor}'"
+        elif (svc.vram_min_mib is not None
+              and svc.vram_min_mib > noeud.vram_mib):
+            raison = (f"VRAM {noeud.vram_mib} Mio < requise "
+                      f"{svc.vram_min_mib} Mio")
+        if raison is None:
+            return noeud.hostname
+        candidats_examines.append(f"{noeud.hostname} ({raison})")
+
+    vram_requise = (f", VRAM requise {svc.vram_min_mib} Mio"
+                    if svc.vram_min_mib is not None else "")
+    raise PlacementError(
+        f"ERR_PLACE_AUCUN_NOEUD_QUALIFIE : aucun nœud ne convient pour le "
+        f"service '{svc.name}' (vendor recherché : {svc.gpu_vendor}"
+        f"{vram_requise}). Nœuds examinés : "
+        f"{'; '.join(candidats_examines) or 'aucun'}")
+
+
 @dataclass(frozen=True)
 class ServiceSpec:
     """Service concret d'un plan de déploiement (brique instanciée)."""
@@ -196,6 +306,7 @@ class ServiceSpec:
     # aucun appel positionnel existant. `resources` (dérogation) prime sur `resource_class`.
     resource_class: str = "utilitaire"
     resources: Optional[dict] = None
+    vram_min_mib: Optional[int] = None  # VRAM minimale exigée par ce service, validée contre l'inventaire au rendu.
 
     def __post_init__(self) -> None:
         # SEC-YAML-INJECT — suivi de #151 : ces scalaires atteignent en brut le YAML/Compose.
diff --git a/src/forgeai/renderers/k3s.py b/src/forgeai/renderers/k3s.py
index a9d1b6c..b9f5bee 100644
--- a/src/forgeai/renderers/k3s.py
+++ b/src/forgeai/renderers/k3s.py
@@ -12,7 +12,7 @@ import textwrap
 from typing import NamedTuple
 from urllib.parse import urlsplit
 
-from forgeai.core.models import DeploymentPlan, ServiceSpec
+from forgeai.core.models import DeploymentPlan, ServiceSpec, NodeInventaire, valider_placement
 from forgeai.renderers._openbao import UNSEAL_SCRIPT as _UNSEAL_SCRIPT
 
 NAMESPACE = "forgeai-minimal"
@@ -735,7 +735,8 @@ def _network_policies(plan: DeploymentPlan) -> str:
 
 def render_k3s(plan: DeploymentPlan, node: str | None = None,
                service_type: str = "NodePort",
-               config_files: dict[str, str] | None = None) -> str:
+               config_files: dict[str, str] | None = None,
+               inventaire: tuple[NodeInventaire, ...] | None = None) -> str:
     """Manifestes Kubernetes STANDARD (valables k3s ET k8s — même API). `node` épingle les pods
     sur un hôte (profil Minimal = single-node) ; `svc.node == "auto"` laisse le scheduler décider.
     `service_type` : NodePort (défaut, portable partout, k3s/edge) ou LoadBalancer (cloud/k8s).
@@ -760,6 +761,15 @@ automountServiceAccountToken: false
     used: set[int] = set()
     for svc in plan.services:
         effective_node = svc.node if svc.node is not None else node
+        # PLACE-011 : valider le placement contre l'inventaire AVANT d'émettre le manifeste.
+        # Sans inventaire, aucune validation n'est possible et le comportement reste inchangé
+        # (rétro-compatibilité). Avec inventaire, un placement incompatible lève PlacementError
+        # ici plutôt que de produire un manifeste qui échouera au scheduling, en production.
+        # `is not None` et non `if inventaire` : un inventaire explicitement VIDE doit atteindre
+        # la validation, qui saura dire qu'aucun nœud n'est disponible. `None` = « je ne sais
+        # pas » ; `()` = « je sais, et il n'y a rien » (objection de revue, DeepSeek-V4-Pro).
+        if inventaire is not None:
+            effective_node = valider_placement(svc, inventaire, effective_node)
         parts.append(_deployment(svc, effective_node, node_port_for(svc, used), service_type,
                                  config_files))
     return "".join(parts)
diff --git a/tests/test_placement_noeud.py b/tests/test_placement_noeud.py
index 3958d82..e7f1dc2 100644
--- a/tests/test_placement_noeud.py
+++ b/tests/test_placement_noeud.py
@@ -147,3 +147,138 @@ def test_plan_sans_placement_reste_documente():
     plan = _plan_minimal()
     assert all(s.node is None for s in plan.services)
     assert not getattr(plan, "placement_reasons", {})
+
+
+# ---------------------------------------------------------------------------
+# PLACE-011 / FAI-U-011 — le placement est validé contre un INVENTAIRE réel avant rendu.
+# Jusqu'ici aucun inventaire n'était consulté : un workload NVIDIA épinglé sur un nœud
+# CPU-only produisait un manifeste parfaitement valide, envoyé à kubectl, qui échouait au
+# scheduling. L'utilisateur découvrait l'incompatibilité en production.
+# ---------------------------------------------------------------------------
+import pytest
+
+from forgeai.core.models import NodeInventaire, PlacementError
+
+
+def _plan(services) -> DeploymentPlan:
+    """Plan portant exactement les services fournis (le fichier n'a que `_plan_minimal`,
+    qui assemble depuis un overlay et ne convient pas pour ces cas ciblés)."""
+    return DeploymentPlan(plan_id="place011", profile="minimal-gpu-cuda",
+                          target=RenderTarget.K3S, services=tuple(services),
+                          model="m", embed_model="e")
+
+
+def _inventaire():
+    """Inventaire de référence : un nœud NVIDIA 8 Go, un nœud AMD 16 Go, un nœud CPU-only."""
+    return (
+        NodeInventaire(hostname="n-nvidia", gpu_vendor="nvidia", vram_mib=8192),
+        NodeInventaire(hostname="n-amd", gpu_vendor="amd", vram_mib=16384),
+        NodeInventaire(hostname="n-cpu", gpu_vendor=None, vram_mib=0),
+    )
+
+
+def _svc_gpu(vendor="nvidia", node=None, vram_requise=None):
+    return ServiceSpec(name="ollama", image="ollama/ollama:latest", host_port=21434,
+                       container_port=11434, gpu=True, gpu_vendor=vendor, node=node,
+                       vram_min_mib=vram_requise)
+
+
+def test_nvidia_ne_peut_pas_etre_epingle_sur_un_noeud_cpu_only():
+    """Critère 1. Le manifeste serait syntaxiquement valide et échouerait au scheduling :
+    l'erreur doit survenir AVANT kubectl, avec sa cause."""
+    with pytest.raises(PlacementError) as exc:
+        render_k3s(_plan([_svc_gpu(node="n-cpu")]), inventaire=_inventaire())
+    message = str(exc.value)
+    assert "n-cpu" in message and "nvidia" in message.lower(), \
+        f"l'erreur doit nommer le nœud ET le vendor attendu : {message}"
+
+
+def test_vendor_incompatible_refuse():
+    """Critère 2. AMD/Intel portent une contrainte vérifiable : un workload AMD sur un nœud
+    NVIDIA est refusé — un GPU n'est pas un GPU générique."""
+    with pytest.raises(PlacementError) as exc:
+        render_k3s(_plan([_svc_gpu(vendor="amd", node="n-nvidia")]), inventaire=_inventaire())
+    assert "amd" in str(exc.value).lower() and "nvidia" in str(exc.value).lower()
+
+
+def test_vram_insuffisante_produit_une_erreur_causale():
+    """Critère 3. Le nœud a bien un GPU du bon vendor, mais pas assez de VRAM : l'échec ne
+    doit pas se manifester par un OOM au chargement du modèle, en production."""
+    with pytest.raises(PlacementError) as exc:
+        render_k3s(_plan([_svc_gpu(node="n-nvidia", vram_requise=12288)]), inventaire=_inventaire())
+    message = str(exc.value)
+    assert "12288" in message and "8192" in message, \
+        f"l'erreur doit donner la VRAM demandée ET la VRAM disponible : {message}"
+
+
+def test_placement_compatible_accepte():
+    """Contrôle positif : un placement valide passe et épingle bien le nœud demandé."""
+    out = render_k3s(_plan([_svc_gpu(node="n-nvidia", vram_requise=4096)]), inventaire=_inventaire())
+    assert "kubernetes.io/hostname: n-nvidia" in out
+
+
+def test_mode_auto_choisit_uniquement_un_noeud_qualifie():
+    """Critère 4. Sans nœud imposé, la sélection automatique ne doit retenir qu'un nœud
+    qualifié — jamais le nœud CPU-only, jamais un vendor incompatible."""
+    out = render_k3s(_plan([_svc_gpu(vendor="amd", node=None)]), inventaire=_inventaire())
+    assert "kubernetes.io/hostname: n-amd" in out
+    assert "n-cpu" not in out and "n-nvidia" not in out
+
+
+def test_mode_auto_sans_noeud_qualifie_refuse():
+    """Contrôle négatif du mode auto : aucun nœud ne convient -> refus explicite, jamais un
+    placement au hasard ni un manifeste voué à l'échec."""
+    inventaire_sans_intel = _inventaire()
+    with pytest.raises(PlacementError) as exc:
+        render_k3s(_plan([_svc_gpu(vendor="intel", node=None)]), inventaire=inventaire_sans_intel)
+    assert "intel" in str(exc.value).lower()
+
+
+def test_sans_inventaire_le_comportement_reste_inchange():
+    """Rétro-compatibilité : sans inventaire fourni, aucune validation n'est possible et le
+    rendu reste celui d'avant — la validation est une capacité ajoutée, pas une rupture."""
+    out = render_k3s(_plan([_svc_gpu(node="n-cpu")]))
+    assert "kubernetes.io/hostname: n-cpu" in out
+
+
+def test_service_cpu_ignore_l_inventaire_gpu():
+    """Contrôle négatif : un service sans GPU n'est jamais contraint par le vendor d'un nœud."""
+    cpu_only = ServiceSpec(name="redis", image="redis:7", host_port=26379, container_port=6379,
+                           node="n-cpu", resource_class="db")
+    out = render_k3s(_plan([cpu_only]), inventaire=_inventaire())
+    assert "kubernetes.io/hostname: n-cpu" in out
+
+
+# --- Objections de la revue scellée (3/3 APPROVE, sceau 258d2f6d1de2) -----------------
+def test_codes_d_erreur_de_l_inventaire_sont_specifiques():
+    """Les TROIS vendors ont relevé indépendamment le même défaut : `NodeInventaire` utilisait
+    `ERR_PLACE_VENDOR_INCONNU` pour signaler un hostname vide ou une VRAM négative — des cas qui
+    n'ont rien à voir avec un vendor. Un code d'erreur trompeur envoie l'utilisateur chercher au
+    mauvais endroit ; c'est exactement ce que les codes stables sont censés éviter."""
+    with pytest.raises(ValueError, match="ERR_PLACE_HOSTNAME_INVALIDE"):
+        NodeInventaire(hostname="")
+    with pytest.raises(ValueError, match="ERR_PLACE_VRAM_INVALIDE"):
+        NodeInventaire(hostname="n1", gpu_vendor="nvidia", vram_mib=-1)
+    with pytest.raises(ValueError, match="ERR_PLACE_VENDOR_INCONNU"):
+        NodeInventaire(hostname="n1", gpu_vendor="matrox")
+
+
+def test_noeud_absent_de_l_inventaire_est_refuse():
+    """Objection de Grok : ce cas était prouvé dans COMPORTEMENT.txt mais aucun test ne le
+    couvrait. Un comportement démontré une fois n'est pas un comportement protégé."""
+    with pytest.raises(PlacementError) as exc:
+        render_k3s(_plan([_svc_gpu(node="n-fantome")]), inventaire=_inventaire())
+    message = str(exc.value)
+    assert "ERR_PLACE_NOEUD_INCONNU" in message
+    assert "n-fantome" in message and "n-nvidia" in message, \
+        "l'erreur doit nommer le nœud demandé ET lister les hostnames connus"
+
+
+def test_inventaire_vide_explicite_n_est_pas_une_absence_d_inventaire():
+    """Objection de DeepSeek : un tuple vide passait pour « pas d'inventaire » et court-circuitait
+    toute validation. Or fournir un inventaire SANS AUCUN nœud n'est pas la même chose que ne pas
+    en fournir : c'est affirmer qu'aucun nœud n'est disponible. Un service GPU ne peut donc y être
+    placé, et le dire vaut mieux que de rendre un manifeste."""
+    with pytest.raises(PlacementError) as exc:
+        render_k3s(_plan([_svc_gpu(node=None)]), inventaire=())
+    assert "ERR_PLACE_AUCUN_NOEUD_QUALIFIE" in str(exc.value)

# ==== ROUGE ====
[ROUGE] sur origin/main (6d7e62c) — aucun inventaire n'est consulté au rendu.

Reproduction exécutée : un workload NVIDIA épinglé sur un nœud CPU-only.

    svc = ServiceSpec(name="ollama", gpu=True, gpu_vendor="nvidia", node="pc-sans-gpu")
    render_k3s(plan)   ->  manifeste RENDU sans broncher, contenant nvidia.com/gpu: "1"

Le manifeste est syntaxiquement PARFAIT. Il part vers kubectl et échoue au scheduling : le
nœud n'a pas de GPU. L'utilisateur découvre l'incompatibilité EN PRODUCTION, sans message
causal — le pod reste simplement Pending.

Tests rouges : 8 échecs (ImportError — ni NodeInventaire, ni PlacementError, ni
valider_placement n'existaient).

# ==== COMPORTEMENT (exécution réelle, APRÈS correctifs) ====
# PLACE-011 — comportement du contrat d'inventaire (exécution réelle, APRÈS revue)

Inventaire : n-nvidia (nvidia, 8192 Mio) | n-amd (amd, 16384 Mio) | n-cpu (CPU-only)

## Placements refusés — chaque message dit demandé / trouvé / pourquoi
  NVIDIA epingle sur n-cpu           -> REFUSE
      ERR_PLACE_CPU_ONLY : le service 'ollama' exige un GPU (vendor demandé : nvidia) mais le nœud 'n-cpu' est CPU-only
  AMD epingle sur n-nvidia           -> REFUSE
      ERR_PLACE_VENDOR_INCOMPATIBLE : service 'ollama' demande le vendor 'amd' mais le nœud 'n-nvidia' expose 'nvidia'
  VRAM 12288 exigee, noeud a 8192    -> REFUSE
      ERR_PLACE_VRAM_INSUFFISANTE : service 'ollama' exige 12288 Mio de VRAM mais le nœud 'n-nvidia' n'en expose que 8192 Mio
  Intel en mode auto                 -> REFUSE
      ERR_PLACE_AUCUN_NOEUD_QUALIFIE : aucun nœud ne convient pour le service 'ollama' (vendor recherché : intel). Nœuds examinés : n-nvidia (vendor 'nvidia' ≠ demandé 'intel'); n-amd (vendor 'amd' ≠ demandé 'intel'); n-cpu (CPU-only)
  noeud absent de l inventaire       -> REFUSE
      ERR_PLACE_NOEUD_INCONNU : nœud 'n-fantome' absent de l'inventaire (connus : n-nvidia, n-amd, n-cpu)
  inventaire explicitement VIDE      -> REFUSE
      ERR_PLACE_AUCUN_NOEUD_QUALIFIE : l'inventaire fourni ne contient aucun nœud, placement d'un service GPU impossible

## Placements acceptés
  AMD en mode auto                   -> n-amd  (seul noeud qualifie)
  NVIDIA + VRAM 4096 sur n-nvidia    -> n-nvidia
  inventaire None (retro-compat)     -> n-cpu
  service CPU sur n-cpu              -> n-cpu  (jamais contraint)
  service CPU, inventaire vide       -> 'n-cpu'

## Codes d'erreur du contrat d'inventaire (objection de revue : chacun son cas)
  hostname vide    -> ERR_PLACE_HOSTNAME_INVALIDE : hostname vide ou uniquement des espaces
  VRAM negative    -> ERR_PLACE_VRAM_INVALIDE : vram_mib négatif (-1), attendu entier >= 0
  vendor inconnu   -> ERR_PLACE_VENDOR_INCONNU : vendor 'matrox' inconnu (autorisés : nvidia, amd, intel, None

# ==== GATES ====
=== GREEN ciblé ===
.......................................                                  [100%]

=== GREEN suite complète ===
............................s........................................... [ 94%]
............................................................             [100%]

=== gates ===
NO-STUB-SCAN : OK (265 fichiers scannés, zéro violation)
[90m8:55PM[0m [32mINF[0m [1mno leaks found[0m
