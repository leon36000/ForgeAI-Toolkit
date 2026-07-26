# K8S-023 — NetworkPolicy : refus par défaut + allowlists par dépendance (FAI-U-023)

## Cause racine
Le renderer n'émettait qu'une politique, et elle était doublement défaillante :

```yaml
spec:
  podSelector: {}
  policyTypes: [Ingress]        # egress TOTALEMENT libre
  ingress:
    - from: [{podSelector: {}}] # accès intra-namespace UNIVERSEL
```

Un pod compromis exfiltrait sans entrave, et tout pod du namespace joignait tout autre pod.

## Changement
`_network_policies(plan)` émet trois familles, dans un ordre déterministe :

| Politique | Portée | Effet |
|---|---|---|
| `forgeai-default-deny` | tous les pods | `policyTypes: [Ingress, Egress]` **sans aucune règle** — en Kubernetes, un type déclaré sans règle signifie « tout refuser » |
| `forgeai-allow-dns` | tous les pods | egress UDP/TCP **53 uniquement**, vers `kube-system` — aucun `ipBlock`, jamais `0.0.0.0/0` |
| `forgeai-allow-<cible>` | le service cible | ingress depuis les **seuls dépendants déclarés**, borné au port du conteneur cible |

Les allowlists dérivent de `ServiceSpec.depends`, **déjà présent dans le modèle** : aucun champ
n'a été ajouté. Un service dont personne ne dépend ne reçoit **aucune** politique d'ingress.
Une dépendance nommant un service absent du plan est ignorée (le plan peut référencer une brique
non déployée), ce qui est commenté dans le code.

## Défaut trouvé par le laboratoire, invisible aux tests de rendu
Première exécution du laboratoire : le flux `litellm -> redis:6379`, pourtant **justifié par une
dépendance déclarée**, était **BLOQUÉ**. Mes cinq tests de rendu étaient pourtant tous verts.

Cause : Kubernetes n'autorise un flux que si l'egress est permis **à la source** ET l'ingress **à
la destination**. Je n'avais émis que le versant ingress ; le `default-deny` continuait donc de
refuser la sortie du dépendant. Le durcissement livré tel quel aurait **cassé toute communication
inter-services** — un déni de service auto-infligé chez les utilisateurs.

Correction : une quatrième famille `forgeai-allow-<dependant>-egress`, symétrique de la troisième,
bornée aux seules cibles déclarées et à leur port. Le contrôle négatif est préservé : un service
sans dépendance présente dans le plan ne reçoit **aucune** politique d'egress.

**Faux positif de sonde, distingué du vrai défaut.** Le même laboratoire annonçait le DNS bloqué.
Vérification directe : CoreDNS répondait correctement
(`redis.np-lab.svc.cluster.local -> 10.43.147.134`) — ma sonde interrogeait un nom court non
résolvable. La sonde a été corrigée ; **le code, lui, était juste**. Corriger un code sain sur la
foi d'un test défectueux aurait été pire que le défaut d'origine.

## Preuve : test réseau de laboratoire sur cluster RÉEL
Le cluster applique effectivement les NetworkPolicy — vérifié au préalable : une politique
deny-all y bloque la sortie vers Internet. Le manifeste rendu a donc été déployé **tel quel**, puis
les flux mesurés depuis les pods eux-mêmes :

| flux | attendu | mesuré |
|---|---|---|
| `litellm -> redis:6379` (dépendance déclarée) | **permis** | voir `reviews/K8S-023/evidence/lab-reseau.txt` |
| `isole -> redis:6379` (aucune dépendance) | **bloqué** | idem |
| `litellm -> Internet` | **bloqué** | idem |
| `isole -> Internet` | **bloqué** | idem |
| `litellm -> DNS kube-system:53` | **permis** | idem |

C'est la différence entre inspecter du YAML et constater ce que le cluster fait réellement.

## Élargissement de périmètre — DÉCLARÉ
`tests/test_k3s_hardening_fai0004.py` (hors `allowed_paths`) assertait
`out.count("kind: NetworkPolicy") == 1`. Le renderer en émet désormais plusieurs **par conception**.
L'intention du test — aucune duplication accidentelle — est préservée et vérifiée précisément :
chaque politique porte un nom unique et le refus par défaut est émis exactement une fois.

## Rollback
`git revert` → retour à la politique unique (défaut FAI-U-023 connu) ; baseline verte.

# ==== DIFF INTÉGRAL ====
diff --git a/src/forgeai/renderers/k3s.py b/src/forgeai/renderers/k3s.py
index a0ddc29..d41664d 100644
--- a/src/forgeai/renderers/k3s.py
+++ b/src/forgeai/renderers/k3s.py
@@ -581,6 +581,146 @@ def _namespace_block(plan: DeploymentPlan) -> str:
     )
 
 
+def _network_policies(plan: DeploymentPlan) -> str:
+    """Construit les NetworkPolicies du profil Minimal.
+
+    POURQUOI : refus par défaut sur Ingress ET Egress (sinon un pod compromis exfiltre, et tout
+    pod du namespace peut en joindre n'importe quel autre), puis ouverture EXCLUSIVEMENT des
+    flux qu'une dépendance déclarée du plan justifie, plus DNS vers kube-system pour ne pas
+    casser la résolution de noms sans rouvrir l'Internet en 0.0.0.0/0.
+    """
+    parts: list[str] = []
+
+    # 1) Refus par défaut : on déclare Ingress+Egress et on n'émet ni règle ingress ni règle
+    # egress -> Kube interprète « tout refuser ». Ne pas écrire `ingress: []` (règle vide).
+    parts.append("---\n")
+    parts.append("apiVersion: networking.k8s.io/v1\n")
+    parts.append("kind: NetworkPolicy\n")
+    parts.append("metadata:\n")
+    parts.append(f"  name: forgeai-default-deny\n")
+    parts.append(f"  namespace: {NAMESPACE}\n")
+    parts.append("spec:\n")
+    parts.append("  podSelector: {}\n")
+    parts.append("  policyTypes:\n")
+    parts.append("    - Ingress\n")
+    parts.append("    - Egress\n")
+
+    # 2) DNS : on rouvre UNIQUEMENT UDP/53 et TCP/53 vers kube-system.
+    # Aucun ipBlock : sans cela, kube-proxy/CoreDNS joignables et Internet toujours bloqué.
+    parts.append("---\n")
+    parts.append("apiVersion: networking.k8s.io/v1\n")
+    parts.append("kind: NetworkPolicy\n")
+    parts.append("metadata:\n")
+    parts.append(f"  name: forgeai-allow-dns\n")
+    parts.append(f"  namespace: {NAMESPACE}\n")
+    parts.append("spec:\n")
+    parts.append("  podSelector: {}\n")
+    parts.append("  policyTypes:\n")
+    parts.append("    - Egress\n")
+    parts.append("  egress:\n")
+    parts.append("    - to:\n")
+    parts.append("        - namespaceSelector:\n")
+    parts.append("            matchLabels:\n")
+    parts.append("              kubernetes.io/metadata.name: kube-system\n")
+    parts.append("      ports:\n")
+    parts.append("        - protocol: UDP\n")
+    parts.append("          port: 53\n")
+    parts.append("        - protocol: TCP\n")
+    parts.append("          port: 53\n")
+
+    # 3) Une politique par service CIBLE d'au moins une dépendance.
+    # Indexation par nom pour O(1) et conservation de l'ordre d'apparition du plan.
+    by_name: dict[str, ServiceSpec] = {svc.name: svc for svc in plan.services}
+    seen_targets: dict[str, list[str]] = {}  # cible -> dépendants (ordre du plan, sans doublon)
+
+    for dependant in plan.services:
+        for dep_name in dependant.depends:
+            cible = by_name.get(dep_name)
+            # Dépendance pointant un service absent du plan : ignorée silencieusement.
+            # Le plan peut référencer une brique non déployée ; on n'ouvre pas de flux.
+            if cible is None:
+                continue
+            if cible.name not in seen_targets:
+                seen_targets[cible.name] = []
+            if dependant.name not in seen_targets[cible.name]:
+                seen_targets[cible.name].append(dependant.name)
+
+    # Ordre déterministe : ordre d'apparition des cibles dans plan.services.
+    for svc in plan.services:
+        dependants = seen_targets.get(svc.name)
+        if not dependants:
+            continue  # Contrôle négatif : personne ne dépend -> aucune politique, aucun flux.
+
+        target_name = _safe(svc.name, "service.name")
+        parts.append("---\n")
+        parts.append("apiVersion: networking.k8s.io/v1\n")
+        parts.append("kind: NetworkPolicy\n")
+        parts.append("metadata:\n")
+        parts.append(f"  name: forgeai-allow-{target_name}\n")
+        parts.append(f"  namespace: {NAMESPACE}\n")
+        parts.append("spec:\n")
+        parts.append(f"  podSelector:\n")
+        parts.append(f"    matchLabels:\n")
+        parts.append(f"      app: {target_name}\n")
+        parts.append("  policyTypes:\n")
+        parts.append("    - Ingress\n")
+        parts.append("  ingress:\n")
+        parts.append("    - from:\n")
+        for dep in dependants:
+            dep_name = _safe(dep, "dependant.name")
+            parts.append(f"        - podSelector:\n")
+            parts.append(f"            matchLabels:\n")
+            parts.append(f"              app: {dep_name}\n")
+        parts.append(f"      ports:\n")
+        parts.append(f"        - protocol: TCP\n")
+        parts.append(f"          port: {svc.container_port}\n")
+
+    # 4) Politiques d'egress symétriques : Kubernetes exige que la source autorise l'egress
+    # ET la destination l'ingress pour qu'un flux passe. Mesuré sur cluster k3s réel : sans cette
+    # politique, `litellm -> redis:6379` reste bloqué même si `forgeai-allow-redis` ouvre l'ingress.
+    for dep_svc in plan.services:
+        # Collecter les cibles (dans l'ordre du plan, sans doublon) dont dep_svc dépend effectivement
+        cibles: list[str] = []
+        for dep_name in dep_svc.depends:
+            cible_svc = by_name.get(dep_name)
+            if cible_svc is None:
+                continue  # Dépendance pointant un service absent du plan : ignorée
+            if cible_svc.name not in cibles:
+                cibles.append(cible_svc.name)
+        if not cibles:
+            # Contrôle négatif : aucune dépendance présente -> pas de politique
+            continue
+
+        dep_name_safe = _safe(dep_svc.name, "dep.name")
+        parts.append("---\n")
+        parts.append("apiVersion: networking.k8s.io/v1\n")
+        parts.append("kind: NetworkPolicy\n")
+        parts.append("metadata:\n")
+        parts.append(f"  name: forgeai-allow-{dep_name_safe}-egress\n")
+        parts.append(f"  namespace: {NAMESPACE}\n")
+        parts.append("spec:\n")
+        parts.append(f"  podSelector:\n")
+        parts.append(f"    matchLabels:\n")
+        parts.append(f"      app: {dep_name_safe}\n")
+        parts.append("  policyTypes:\n")
+        parts.append("    - Egress\n")
+        parts.append("  egress:\n")
+        for cible_name in cibles:
+            cible_safe = _safe(cible_name, "target.name")
+            cible_svc = by_name[cible_name]  # Garanti présent car filtré plus haut
+            container_port = cible_svc.container_port
+            parts.append("    - to:\n")
+            parts.append(f"        - podSelector:\n")
+            parts.append(f"            matchLabels:\n")
+            parts.append(f"              app: {cible_safe}\n")
+            parts.append("      ports:\n")
+            parts.append(f"        - protocol: TCP\n")
+            parts.append(f"          port: {container_port}\n")
+
+
+    return "".join(parts)
+
+
 def render_k3s(plan: DeploymentPlan, node: str | None = None,
                service_type: str = "NodePort",
                config_files: dict[str, str] | None = None) -> str:
@@ -600,20 +740,11 @@ metadata:
   name: forgeai-sa
   namespace: {NAMESPACE}
 automountServiceAccountToken: false
----
-apiVersion: networking.k8s.io/v1
-kind: NetworkPolicy
-metadata:
-  name: forgeai-default
-  namespace: {NAMESPACE}
-spec:
-  podSelector: {{}}
-  policyTypes:
-    - Ingress
-  ingress:
-    - from:
-        - podSelector: {{}}
 """]
+    # K8S-023 : refus par défaut Ingress ET Egress + allowlists dérivées des dépendances
+    # DÉCLARÉES du plan. Remplace l'unique politique `forgeai-default`, qui laissait l'egress
+    # totalement libre et autorisait un accès intra-namespace universel.
+    parts.append(_network_policies(plan))
     used: set[int] = set()
     for svc in plan.services:
         effective_node = svc.node if svc.node is not None else node
diff --git a/tests/test_k3s_hardening.py b/tests/test_k3s_hardening.py
index 73ea5b0..ea40b80 100644
--- a/tests/test_k3s_hardening.py
+++ b/tests/test_k3s_hardening.py
@@ -232,3 +232,114 @@ def test_le_pvc_prime_sur_l_emptydir_de_repli():
     assert montages.count("/qdrant/storage") == 1
     volume = next(v for v in pod["volumes"] if v["name"] == "forgeai-qdrant-data")
     assert "persistentVolumeClaim" in volume and "emptyDir" not in volume
+
+
+# ---------------------------------------------------------------------------
+# K8S-023 / FAI-U-023 — NetworkPolicy : default-deny + allowlists par dépendance.
+# L'unique politique rendue jusqu'ici ne portait que `Ingress` (egress TOTALEMENT libre)
+# et autorisait `from: podSelector: {}` — un accès intra-namespace UNIVERSEL, que le
+# package interdit explicitement.
+# ---------------------------------------------------------------------------
+def _policies(manifest: str) -> list[dict]:
+    return [d for d in yaml.safe_load_all(manifest) if d and d.get("kind") == "NetworkPolicy"]
+
+
+def _plan_dependant():
+    """litellm dépend de redis : une dépendance DÉCLARÉE dont doit dériver l'allowlist."""
+    redis = _svc(name="redis", image="redis:7-alpine", host_port=26379, container_port=6379)
+    litellm = _svc(name="litellm", image="litellm:x", host_port=24000, container_port=4000,
+                   depends=("redis",))
+    return _plan([redis, litellm])
+
+
+def test_default_deny_porte_ingress_ET_egress():
+    """Sans `Egress` dans policyTypes, un pod compromis sort librement : exfiltration ouverte."""
+    politiques = _policies(render_k3s(_plan_dependant()))
+    deny = [p for p in politiques if p["spec"].get("podSelector") == {}]
+    assert deny, "une politique par défaut s'appliquant à TOUS les pods est requise"
+    types = set(deny[0]["spec"].get("policyTypes") or [])
+    assert types == {"Ingress", "Egress"}, f"default-deny incomplet : {types}"
+    assert not deny[0]["spec"].get("ingress"), "la politique par défaut ne doit rien autoriser"
+    assert not deny[0]["spec"].get("egress"), "la politique par défaut ne doit rien autoriser"
+
+
+def test_aucun_acces_intra_namespace_universel():
+    """`from: [{podSelector: {}}]` autorise TOUT pod du namespace à joindre TOUT autre :
+    c'est exactement ce que le package proscrit."""
+    for politique in _policies(render_k3s(_plan_dependant())):
+        for regle in politique["spec"].get("ingress") or []:
+            for origine in regle.get("from") or []:
+                assert origine.get("podSelector") != {}, \
+                    f"accès intra-namespace universel dans {politique['metadata']['name']}"
+
+
+def test_dns_autorise_sans_ouvrir_internet():
+    """Egress refusé par défaut casse la résolution de noms : DNS doit être rouvert
+    explicitement — vers kube-system, sur le port 53, et RIEN d'autre."""
+    politiques = _policies(render_k3s(_plan_dependant()))
+    dns = [p for p in politiques if "dns" in p["metadata"]["name"]]
+    assert dns, "une politique DNS explicite est requise"
+    regles = dns[0]["spec"].get("egress") or []
+    ports = {(pt.get("protocol"), pt.get("port")) for r in regles for pt in (r.get("ports") or [])}
+    assert ports and all(p == 53 for _, p in ports), f"DNS doit se limiter au port 53 : {ports}"
+    for regle in regles:
+        for dest in regle.get("to") or []:
+            assert "ipBlock" not in dest or not dest["ipBlock"].get("cidr", "").endswith("/0"), \
+                "le DNS ne doit pas ouvrir Internet"
+
+
+def test_chaque_dependance_declaree_produit_une_allowlist():
+    """`litellm.depends = ('redis',)` doit produire un flux PERMIS litellm -> redis:6379,
+    et lui seul : chaque flux ouvert correspond à une dépendance du plan."""
+    politiques = _policies(render_k3s(_plan_dependant()))
+    vers_redis = [p for p in politiques
+                  if p["spec"].get("podSelector", {}).get("matchLabels", {}).get("app") == "redis"
+                  and p["spec"].get("ingress")]
+    assert vers_redis, "redis doit porter une politique d'ingress dérivée de la dépendance"
+    origines = [o for p in vers_redis for r in p["spec"]["ingress"] for o in (r.get("from") or [])]
+    apps = {o.get("podSelector", {}).get("matchLabels", {}).get("app") for o in origines}
+    assert apps == {"litellm"}, f"seul le dépendant déclaré doit être autorisé : {apps}"
+    ports = {pt.get("port") for p in vers_redis for r in p["spec"]["ingress"]
+             for pt in (r.get("ports") or [])}
+    assert ports == {6379}, f"le flux doit être borné au port du service cible : {ports}"
+
+
+def test_service_sans_dependant_ne_recoit_aucune_allowlist():
+    """Contrôle négatif : un service dont personne ne dépend ne doit ouvrir aucun flux entrant."""
+    seul = _svc(name="isole", image="x:1", host_port=29999, container_port=9999)
+    politiques = _policies(render_k3s(_plan([seul])))
+    pour_isole = [p for p in politiques
+                  if p["spec"].get("podSelector", {}).get("matchLabels", {}).get("app") == "isole"]
+    assert not any(p["spec"].get("ingress") for p in pour_isole), \
+        "aucun dépendant déclaré : aucun flux entrant ne doit être ouvert"
+
+
+def test_le_dependant_recoit_aussi_une_autorisation_de_sortie():
+    """Défaut MESURÉ sur cluster k3s réel : le flux `litellm -> redis:6379`, pourtant justifié par
+    `litellm.depends = ('redis',)`, était BLOQUÉ. En Kubernetes un flux n'est permis que si
+    l'egress est autorisé À LA SOURCE **et** l'ingress à la destination ; n'ouvrir que la
+    destination laisse le default-deny refuser la sortie du dépendant. La symétrie n'est pas un
+    détail de style, c'est une exigence du modèle réseau."""
+    politiques = _policies(render_k3s(_plan_dependant()))
+    egress_litellm = [p for p in politiques
+                      if p["spec"].get("podSelector", {}).get("matchLabels", {}).get("app") == "litellm"
+                      and "Egress" in (p["spec"].get("policyTypes") or [])
+                      and p["spec"].get("egress")]
+    assert egress_litellm, "le dépendant doit recevoir une autorisation de SORTIE vers sa cible"
+    regles = egress_litellm[0]["spec"]["egress"]
+    cibles = {d.get("podSelector", {}).get("matchLabels", {}).get("app")
+              for r in regles for d in (r.get("to") or [])}
+    assert cibles == {"redis"}, f"la sortie doit être bornée aux cibles déclarées : {cibles}"
+    ports = {pt.get("port") for r in regles for pt in (r.get("ports") or [])}
+    assert ports == {6379}, f"la sortie doit être bornée au port de la cible : {ports}"
+
+
+def test_service_sans_dependance_ne_recoit_aucune_sortie():
+    """Contrôle négatif symétrique : sans dépendance déclarée, aucun egress n'est ouvert et le
+    default-deny continue de confiner le service."""
+    seul = _svc(name="isole", image="x:1", host_port=29999, container_port=9999)
+    politiques = _policies(render_k3s(_plan([seul])))
+    pour_isole = [p for p in politiques
+                  if p["spec"].get("podSelector", {}).get("matchLabels", {}).get("app") == "isole"]
+    assert not any(p["spec"].get("egress") for p in pour_isole), \
+        "aucune dépendance déclarée : aucune sortie ne doit être ouverte"
diff --git a/tests/test_k3s_hardening_fai0004.py b/tests/test_k3s_hardening_fai0004.py
index eed2acd..a75e4a5 100644
--- a/tests/test_k3s_hardening_fai0004.py
+++ b/tests/test_k3s_hardening_fai0004.py
@@ -46,8 +46,16 @@ def test_serviceaccount_and_networkpolicy_emis_une_fois():
     assert out.count("kind: ServiceAccount") == 1
     assert "name: forgeai-sa" in out
     assert out.count("automountServiceAccountToken: false") == 2  # SA + pod spec
-    assert out.count("kind: NetworkPolicy") == 1
-    assert "name: forgeai-default" in out
+    # K8S-023 : le renderer émet désormais PLUSIEURS NetworkPolicies par conception — refus par
+    # défaut, DNS, puis une allowlist par service cible d'une dépendance déclarée. L'intention de
+    # ce test — aucune duplication accidentelle — est préservée et vérifiée précisément : chaque
+    # politique porte un nom unique, et le refus par défaut est émis exactement une fois.
+    noms = [ligne.strip()[len("name: "):] for ligne in out.splitlines()
+            if ligne.strip().startswith("name: forgeai-")]
+    politiques = [n for n in noms if n.startswith("forgeai-default-deny")
+                  or n.startswith("forgeai-allow-")]
+    assert len(politiques) == len(set(politiques)), f"politique dupliquée : {politiques}"
+    assert politiques.count("forgeai-default-deny") == 1
 
 
 def test_redis_clusterip_sans_nodeport():

# ==== ROUGE ====
[ROUGE] sur origin/main (2bbbe4c) — l'unique NetworkPolicy rendue :

  kind: NetworkPolicy
  metadata: {name: forgeai-default}
  spec:
    podSelector: {}
    policyTypes:
      - Ingress            <- Egress ABSENT : sortie totalement libre
    ingress:
      - from:
          - podSelector: {}   <- accès intra-namespace UNIVERSEL

Deux failles :
  (a) `policyTypes` ne porte que `Ingress` -> un pod compromis exfiltre sans entrave ;
  (b) `from: [{podSelector: {}}]` -> tout pod du namespace joint tout autre pod, ce que
      l'objectif du package proscrit explicitement (« aucun accès intra-namespace universel »).

Tests rouges : 4 échecs sur 5 (le 5e, contrôle négatif, passait déjà puisque AUCUNE allowlist
n'existait) — default-deny incomplet, accès universel présent, aucune politique DNS, aucune
allowlist dérivée des dépendances déclarées.

# ==== LABORATOIRE RÉSEAU (cluster réel) ====
# K8S-023 — test réseau de LABORATOIRE sur cluster k3s v1.35.5 réel
# Le manifeste rendu est appliqué TEL QUEL ; les flux sont mesurés DEPUIS les pods.
# Prérequis vérifié au préalable : ce cluster applique effectivement les NetworkPolicy
# (une politique deny-all y bloque la sortie vers Internet).

politiques : 4
  forgeai-allow-dns
  forgeai-allow-litellm-egress
  forgeai-allow-redis
  forgeai-default-deny
  isole-75f588b6b4-wbgpg 0/1 Running
  litellm-97f44644b-m7lwg 0/1 Running
  redis-67dfdffb7-w7rm8 1/1 Running
--- flux PERMIS (dépendance déclarée litellm -> redis) ---
  litellm -> redis:6379                          -> PASSE    (attendu PASSE   ) conforme
--- flux INTERDITS ---
  isole -> redis:6379 (aucune dépendance)       -> BLOQUE   (attendu BLOQUE  ) conforme
  litellm -> Internet (1.1.1.1)                  -> BLOQUE   (attendu BLOQUE  ) conforme
  isole -> Internet (1.1.1.1)                    -> BLOQUE   (attendu BLOQUE  ) conforme
--- DNS (rouvert explicitement, sans ouvrir Internet) ---
  litellm -> DNS kube-system:53                  -> PASSE    (attendu PASSE   ) conforme

## Première exécution (AVANT correctif) — le laboratoire a invalidé l'implémentation
  litellm -> redis:6379   -> BLOQUE (attendu PASSE) : allowlist unidirectionnelle.
  Kubernetes exige la symétrie : egress permis à la SOURCE **et** ingress à la DESTINATION.
  Les 5 tests de rendu étaient pourtant VERTS — ils vérifiaient la forme, jamais l'effet.

## Faux positif de sonde, distingué du vrai défaut
  Le DNS était annoncé bloqué. Vérification directe : CoreDNS répondait
  (redis.np-lab.svc.cluster.local -> 10.43.147.134). La sonde utilisait un nom court non
  résolvable ; le code était juste. Sonde corrigée, code inchangé.

# ==== GATES ====
=== GREEN ciblé ===
........................                                                 [100%]

=== GREEN suite complète ===
...................................s.................................... [ 95%]
............................................                             [100%]
