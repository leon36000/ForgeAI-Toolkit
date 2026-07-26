# K8S-024 — Pod Security Admission sur le Namespace rendu (FAI-U-024)

## Cause racine
Le Namespace émis par `render_k3s` ne portait **aucune** étiquette `pod-security.kubernetes.io/*` :

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: forgeai-minimal
```

Conséquence directe : tout le durcissement des pods livré par K8S-022 (profil PSS `restricted` par
service) restait **purement déclaratif**. Le cluster n'appliquait rien, ne signalait rien, et une
régression future — un pod privilégié réintroduit par erreur — aurait été **acceptée en silence**.
La preuve de K8S-022 elle-même n'a pu être faite qu'en posant l'étiquette **à la main** : c'était
précisément le défaut.

## Changement
`_namespace_block(plan)` émet le Namespace avec les trois modes d'admission :
- `enforce` : **refuse** les pods non conformes ;
- `audit` : journalise l'écart dans l'audit de l'API server ;
- `warn` : renvoie un avertissement à l'auteur de l'apply.

Chaque mode porte sa **version épinglée** `_PSA_VERSION = "v1.25"` — version de stabilisation des
Pod Security Standards, donc comprise par tout cluster ≥ 1.25. `latest` est refusé : il ferait
**dériver la politique** au gré des montées de version du cluster, exactement le défaut que
FAI-0011 a corrigé pour les images.

## Exception : plan contenant un service GPU (mesurée, jamais supposée)
Un pod GPU en passthrough `hostPath` a été soumis à chaque niveau sur cluster k3s v1.35.5 réel :

| enforce | résultat mesuré |
|---|---|
| `restricted` | **REFUSÉ** — « restricted volume type hostPath », « runAsNonRoot » |
| `baseline` | **REFUSÉ** — « hostPath volumes (volume "dri") » |
| `privileged` | **ACCEPTÉ** |

`baseline` interdit lui aussi `hostPath` : contrairement à l'intuition, il n'existe **aucun niveau
intermédiaire** qui admette le passthrough de devices. Annoncer `restricted` sur un plan GPU
produirait donc un déploiement que le cluster refuse — un mensonge coûteux pour l'utilisateur.

Traitement : `enforce` descend à `privileged` **uniquement** si le plan contient un service dont le
GPU a été explicitement demandé, tandis que `audit` **et** `warn` restent à `restricted` — l'API
server continue donc de signaler chaque écart. Deux commentaires `# forgeai:` dans le manifeste
déclarent la dégradation et sa raison : l'exception est **visible**, jamais silencieuse.

## Preuves
- ROUGE : `reviews/K8S-024/evidence/RED.txt` — 4 tests, aucune étiquette d'admission émise.
- Mesure des niveaux : `reviews/K8S-024/evidence/mesure-niveaux-psa.txt` (3 namespaces réels).
- E2E : `reviews/K8S-024/evidence/DEPLOIEMENT-REEL.txt` — le manifeste rendu est appliqué **tel
  quel**, sans aucune étiquette posée à la main ; le namespace naît avec `enforce=restricted`
  épinglé v1.25 et les pods sont admis puis démarrent. Le produit s'applique son propre profil.

## Rollback
`git revert` → Namespace sans étiquettes (défaut FAI-U-024 connu) ; baseline verte.

# ======== DIFF INTÉGRAL ========
diff --git a/src/forgeai/renderers/k3s.py b/src/forgeai/renderers/k3s.py
index c93321b..a0ddc29 100644
--- a/src/forgeai/renderers/k3s.py
+++ b/src/forgeai/renderers/k3s.py
@@ -101,8 +101,11 @@ _PROFILS_SECURITE: dict[str, ProfilSecurite] = {
     ),
     "qdrant": ProfilSecurite(
         uid=1000,
-        chemins_inscriptibles=("/qdrant/snapshots",),
-        preuve="qdrant/qdrant:v1.12.5 : panic « Can't create Snapshots directory: PermissionDenied » sans ce volume ; READY avec",
+        chemins_inscriptibles=("/qdrant/storage", "/qdrant/snapshots"),
+        preuve="qdrant/qdrant:v1.12.5 : panic « Can't create Snapshots directory: PermissionDenied » "
+               "sans /qdrant/snapshots ; et « Service internal error: Read-only file system (os error 30) » "
+               "sans /qdrant/storage lorsque AUCUN volume de données n'est déclaré (mesuré e2e K8S-024). "
+               "Si un PVC est monté sur ce chemin, l'emptyDir est écarté (garde anti-doublon de montage).",
     ),
     "postgres": ProfilSecurite(
         uid=999,
@@ -542,6 +545,42 @@ spec:
 """
 
 
+_PSA_VERSION = "v1.25"
+
+
+def _namespace_block(plan: DeploymentPlan) -> str:
+    """Émet le Namespace avec les étiquettes Pod Security Admission.
+
+    Sans ces étiquettes, le durcissement des pods reste purement déclaratif :
+    le cluster n'applique aucune politique de sécurité aux pods déployés.
+    """
+    enforce = "privileged" if any(svc.gpu for svc in plan.services) else "restricted"
+
+    comments = ""
+    if enforce == "privileged":
+        comments = (
+            "# forgeai: le niveau enforce est abaissé à privileged car le plan "
+            "demande explicitement le passthrough hostPath des devices GPU.\n"
+            "# forgeai: restricted et baseline refusent tous deux les volumes hostPath ; "
+            "audit et warn restent à restricted pour signaler l'écart.\n"
+        )
+
+    return (
+        "apiVersion: v1\n"
+        "kind: Namespace\n"
+        f"{comments}"
+        "metadata:\n"
+        f"  name: {NAMESPACE}\n"
+        "  labels:\n"
+        f"    pod-security.kubernetes.io/enforce: {enforce}\n"
+        f"    pod-security.kubernetes.io/enforce-version: {_PSA_VERSION}\n"
+        "    pod-security.kubernetes.io/audit: restricted\n"
+        f"    pod-security.kubernetes.io/audit-version: {_PSA_VERSION}\n"
+        "    pod-security.kubernetes.io/warn: restricted\n"
+        f"    pod-security.kubernetes.io/warn-version: {_PSA_VERSION}\n"
+    )
+
+
 def render_k3s(plan: DeploymentPlan, node: str | None = None,
                service_type: str = "NodePort",
                config_files: dict[str, str] | None = None) -> str:
@@ -554,11 +593,7 @@ def render_k3s(plan: DeploymentPlan, node: str | None = None,
         raise ValueError(
             f"service_type invalide : {service_type!r} (attendu {sorted(_SERVICE_TYPES)})")
     parts = [f"""# Généré par ForgeAI Toolkit — plan {plan.plan_id} (profil {plan.profile})
-apiVersion: v1
-kind: Namespace
-metadata:
-  name: {NAMESPACE}
----
+{_namespace_block(plan)}---
 apiVersion: v1
 kind: ServiceAccount
 metadata:
diff --git a/tests/test_k3s_hardening.py b/tests/test_k3s_hardening.py
index 86c42cc..73ea5b0 100644
--- a/tests/test_k3s_hardening.py
+++ b/tests/test_k3s_hardening.py
@@ -147,3 +147,88 @@ def test_root_filesystem_en_lecture_seule_par_defaut():
     # readOnlyRootFilesystem sans /tmp inscriptible casse la plupart des runtimes -> emptyDir explicite
     montages = {m["mountPath"] for m in cont.get("volumeMounts") or []}
     assert "/tmp" in montages
+
+
+# ---------------------------------------------------------------------------
+# K8S-024 / FAI-U-024 — Pod Security Admission : le Namespace rendu doit PORTER le niveau
+# d'enforcement, sinon le profil restricted de K8S-022 n'est jamais APPLIQUÉ par le cluster.
+# Le niveau enforce doit correspondre à ce que les manifests respectent réellement.
+# ---------------------------------------------------------------------------
+_PSA_PREFIXE = "pod-security.kubernetes.io/"
+
+
+def _namespace(manifest: str) -> dict:
+    for doc in yaml.safe_load_all(manifest):
+        if doc and doc.get("kind") == "Namespace":
+            return doc
+    raise AssertionError("aucun Namespace dans le manifeste rendu")
+
+
+def test_namespace_porte_l_admission_pod_security():
+    """Sans ces étiquettes, le cluster n'applique RIEN : le durcissement reste déclaratif."""
+    ns = _namespace(render_k3s(_plan([_svc(name="service-quelconque")])))
+    labels = ns["metadata"].get("labels") or {}
+    assert labels.get(_PSA_PREFIXE + "enforce") == "restricted"
+    assert labels.get(_PSA_PREFIXE + "audit") == "restricted"
+    assert labels.get(_PSA_PREFIXE + "warn") == "restricted"
+
+
+def test_versions_d_admission_epinglees():
+    """`latest` ferait dériver la politique au gré des montées de version du cluster : versions
+    ÉPINGLÉES, comme les images le sont déjà (FAI-0011)."""
+    ns = _namespace(render_k3s(_plan([_svc(name="service-quelconque")])))
+    labels = ns["metadata"].get("labels") or {}
+    for mode in ("enforce", "audit", "warn"):
+        version = labels.get(f"{_PSA_PREFIXE}{mode}-version")
+        assert version and version != "latest", f"{mode}-version doit être épinglée, vu : {version!r}"
+        assert version.startswith("v1."), f"version k8s attendue (vX.Y), vu : {version!r}"
+
+
+def test_enforce_correspond_aux_manifests_rendus():
+    """Le niveau annoncé doit être TENU : un plan sans GPU est conforme restricted, donc enforce
+    reste `restricted`. C'est le lien entre l'étiquette et la réalité du rendu."""
+    out = render_k3s(_plan([_svc(name="service-quelconque")]))
+    assert violations_pss_restricted(out) == []
+    labels = _namespace(out)["metadata"].get("labels") or {}
+    assert labels.get(_PSA_PREFIXE + "enforce") == "restricted"
+
+
+def test_exception_gpu_degrade_enforce_et_reste_visible():
+    """Un service GPU DÉROGE au profil restricted (mesure K8S-022 : non-root = 0/4 devices).
+    Annoncer `enforce: restricted` sur un tel plan serait un mensonge : le cluster REFUSERAIT les
+    pods au déploiement. Niveau réellement tenu, MESURÉ sur cluster k3s v1.35.5 avec le pod GPU réel :
+      enforce=restricted -> REFUSÉ (« restricted volume type hostPath », « runAsNonRoot »)
+      enforce=baseline    -> REFUSÉ (« hostPath volumes (volume "dri") »)
+      enforce=privileged  -> ACCEPTÉ
+    `baseline` interdit lui aussi hostPath : seul `privileged` admet le passthrough de devices.
+    L'exception doit donc être VISIBLE : enforce descendu au seul niveau qui tient, audit ET warn
+    MAINTENUS à restricted pour que l'API server continue de signaler chaque écart."""
+    out = render_k3s(_plan([_svc(name="ollama", gpu=True, gpu_vendor="amd")]))
+    labels = _namespace(out)["metadata"].get("labels") or {}
+    assert labels.get(_PSA_PREFIXE + "enforce") == "privileged"
+    assert labels.get(_PSA_PREFIXE + "audit") == "restricted"
+    assert labels.get(_PSA_PREFIXE + "warn") == "restricted"
+    assert "# forgeai:" in out.split("kind: Namespace")[1].split("---")[0]
+
+
+def test_service_sans_volume_declare_garde_un_chemin_de_donnees_inscriptible():
+    """Régression K8S-022 attrapée par l'E2E de K8S-024 : avec readOnlyRootFilesystem, un service
+    dont le répertoire de données n'est PAS déclaré en volume ne peut plus le créer. Mesuré sur
+    cluster réel : qdrant sans volume -> « Service internal error: Read-only file system (os error
+    30) ». Le profil doit donc fournir un emptyDir de repli sur ce chemin."""
+    out = render_k3s(_plan([_svc(name="qdrant", image="qdrant/qdrant:v1.12.5")]))
+    cont = _deployments(out)[0]["spec"]["template"]["spec"]["containers"][0]
+    montages = {m["mountPath"] for m in cont.get("volumeMounts") or []}
+    assert "/qdrant/storage" in montages
+
+
+def test_le_pvc_prime_sur_l_emptydir_de_repli():
+    """Le repli ne doit JAMAIS masquer les données : quand un volume persistant est déclaré sur le
+    même chemin, il est monté seul (un mountPath dupliqué rendrait d'ailleurs le pod invalide)."""
+    out = render_k3s(_plan([_svc(name="qdrant", image="qdrant/qdrant:v1.12.5",
+                                volumes=("forgeai-qdrant-data:/qdrant/storage",))]))
+    pod = _deployments(out)[0]["spec"]["template"]["spec"]
+    montages = [m["mountPath"] for m in pod["containers"][0].get("volumeMounts") or []]
+    assert montages.count("/qdrant/storage") == 1
+    volume = next(v for v in pod["volumes"] if v["name"] == "forgeai-qdrant-data")
+    assert "persistentVolumeClaim" in volume and "emptyDir" not in volume

# ======== PREUVE ROUGE ========
[ROUGE] sur origin/main (8380bc3) — le Namespace rendu ne porte AUCUNE étiquette d'admission :
  labels du Namespace : None

# ======== PREUVE VERTE ========
=== GREEN ciblé ===
.................                                                        [100%]

=== GREEN suite complète ===
....s................................................................... [ 98%]
.............                                                            [100%]

# ======== MESURE DES NIVEAUX PSA (cluster réel) ========
enforce=restricted -> REFUSÉ : Error from server (Forbidden): error when creating "STDIN": pods "gpu" is forbidden: violates PodSecurity "restricted:latest": restricted volume types (volume "dri" uses restricted volume type "hostPath"), runAsNonRoot !
enforce=baseline -> REFUSÉ : Error from server (Forbidden): error when creating "STDIN": pods "gpu" is forbidden: violates PodSecurity "baseline:latest": hostPath volumes (volume "dri") 
enforce=privileged -> ACCEPTÉ

# ======== DÉPLOIEMENT RÉEL ========
# K8S-024 — déploiement RÉEL du manifeste rendu (aucune étiquette posée à la main)

## Namespace créé PAR LE MANIFESTE (étiquettes portées par le rendu lui-même)
{"kubernetes.io/metadata.name":"k8s024-bis","pod-security.kubernetes.io/audit":"restricted","pod-security.kubernetes.io/audit-version":"v1.25","pod-security.kubernetes.io/enforce":"restricted","pod-security.kubernetes.io/enforce-version":"v1.25","pod-security.kubernetes.io/warn":"restricted","pod-security.kubernetes.io/warn-version":"v1.25"}

## Pods sous enforcement auto-appliqué
qdrant-7d5f4cdd75-6xc4w   1/1   Running   0     3m33s
redis-5f7dc98d97-qbcc4    1/1   Running   0     3m33s

## Refus d'admission PodSecurity : AUCUN
  évènements forbidden/violation : 0

## Volumes inscriptibles émis (correction de la régression K8S-022)
  inscriptible-qdrant-snapshots
  inscriptible-qdrant-storage
  inscriptible-tmp

## AVANT correction (même manifeste, sans /qdrant/storage) : qdrant CrashLoopBackOff
  Error: Service internal error: Read-only file system (os error 30)
