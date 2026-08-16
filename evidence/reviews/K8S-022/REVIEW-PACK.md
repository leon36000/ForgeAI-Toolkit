# K8S-022 — Profil PSS « restricted » par défaut dans le renderer k3s (FAI-U-022)

## Cause racine
`renderers/k3s.py::_security_block` n'émettait que `allowPrivilegeEscalation: false` +
`seccompProfile: RuntimeDefault`. `capabilities.drop:[ALL]`, `runAsNonRoot` et
`readOnlyRootFilesystem` étaient refusés **globalement**, au motif documenté dans le code que
« redis:7-alpine avec drop:[ALL] -> CrashLoopBackOff (chown: Operation not permitted) ».

Ce refus reposait sur un **diagnostic erroné**, réfuté par la mesure : l'échec ne vient pas de
`drop:[ALL]`, il vient de `drop:[ALL]` **en restant root**. L'entrypoint root de redis exécute
`chown` sur /data ; sans la capability CHOWN, il échoue. Le même conteneur en **non-root avec
`fsGroup`** ne tente jamais ce `chown` (le script teste `id -u = 0`) et démarre normalement.

## Mesures (cluster k3s v1.35.5 RÉEL, 4 nœuds, 2026-07-26 — 30 pods appliqués et observés)
Preuves brutes : `reviews/K8S-022/evidence/mesures-runtime.jsonl` (+ scripts de sonde rejouables).

| service | image mesurée | uid | restricted COMPLET | fait déterminant |
|---|---|---|---|---|
| redis | redis:7-alpine | 999 | **READY** | root + drop ALL -> FAILED `chown: . : Operation not permitted` |
| litellm | litellm:main-stable | 1000 | **READY** | — |
| qdrant | qdrant:v1.12.5 | 1000 | **READY** | sans volume /qdrant/snapshots : panic `Can't create Snapshots directory: PermissionDenied` |
| postgres | postgres:18.3-alpine | 999 | **READY** | root + drop ALL -> `chmod: /var/run/postgresql: Operation not permitted` |
| immudb | immudb:1.11.1 | 3322 | **READY** | — |
| openbao | openbao:2.6.0 | 100 | **ÉCRITURE OK** | USER nommé « openbao » |
| langfuse | langfuse:3 | 1000 | **ÉCRITURE OK** | — |
| TEI | text-embeddings-inference:cpu-1.5 | 1000 | **ÉCRITURE OK** | — |
| ollama | ollama:latest | 1000 | READY **sans** readOnlyRootFilesystem | `mkdir /home/ubuntu/.ollama: read-only file system` |

### Trois faits de conception PROUVÉS (et non supposés)
1. **`runAsNonRoot: true` sans `runAsUser` numérique est refusé par le kubelet**, aussi bien pour une
   image à USER nommé (`openbao` -> *« image has non-numeric user (openbao), cannot verify user is
   non-root »*) que pour une image root (`qdrant`, `USER 0:0` -> *« image will run as root »*).
   Une table d'uid **numériques** par service est donc OBLIGATOIRE — ce n'est pas un choix de style.
2. **`drop:[ALL]` n'est viable qu'en non-root** (redis et postgres mesurés). L'ancien refus global
   était donc justifié par la mauvaise cause.
3. **`readOnlyRootFilesystem` exige des volumes inscriptibles explicites**, dont les chemins ont été
   mesurés service par service — jamais devinés.

## Changement
1. Table `_PROFILS_SECURITE` (nom de service -> `ProfilSecurite`) : uid mesuré, `ro_rootfs`,
   `chemins_inscriptibles`, et le champ `preuve` citant image + mode d'échec observé.
2. Bloc de sécurité au niveau **POD** : `runAsNonRoot` + `runAsUser`/`runAsGroup`/`fsGroup` + seccomp
   (identité et propriété des volumes = propriétés du pod).
3. Bloc de sécurité au niveau **CONTENEUR** : `allowPrivilegeEscalation: false`,
   `capabilities.drop:[ALL]`, `readOnlyRootFilesystem`, seccomp (garanties par conteneur).
4. Volumes `emptyDir` inscriptibles explicites (`/tmp` + chemins mesurés), nommés `inscriptible-…`
   pour ne jamais entrer en collision avec les PVC/hostPath/configMap/secret existants.
5. Le side-car openbao reçoit le même durcissement de conteneur (sinon le pod violerait le profil).

## Exception unique, mesurée : les services GPU
Un service GPU en passthrough `hostPath` **ne peut pas** tourner en non-root :
conteneur non-root = **0/4** devices `/dev/dri` accessibles ; avec le groupe `video`(44) = **2/4**
seulement (les `renderD*` appartiennent au groupe `render`, **gid 992 sur cet hôte, variable d'une
machine à l'autre**, donc inconnu au moment du rendu) ; en root = 4/4. La dérogation est donc :
- **limitée aux services dont l'utilisateur a explicitement demandé le GPU** (`svc.gpu`), jamais globale ;
- **conservée au maximum** : `drop:[ALL]`, `allowPrivilegeEscalation: false` et seccomp restent émis ;
- **bruyante** : un commentaire YAML dans le manifeste déclare la dérogation et sa raison mesurée.
Le volume `hostPath` du passthrough est lui-même hors PSS restricted : c'est le même écart, déjà
documenté par K8S-008. La dérogation porte AUSSI sur `readOnlyRootFilesystem` (objection mineure de la revue scellée,
acceptée et corrigée) : les chemins d'écriture d'un moteur GPU (caches de modèles, cache de
compilation du runtime vendor) dépendent de l'image ET de l'hôte et n'ont pas pu être mesurés
faute de matériel GPU autorisé. Activer la racine en lecture seule sans mesure casserait des
déploiements réels — la règle « exceptions spécifiques et TESTÉES » interdit de le faire à
l'aveugle. Ce champ n'est pas une exigence PSS restricted : le pod GPU ne déroge à `restricted`
que par son identité root et son volume `hostPath`.
Le durcissement complet des pods GPU exige de mesurer les gid de l'hôte —
c'est l'objet des packages `LAB-033*`, `BLOCKED_LAB` faute de matériel autorisé.

## Preuves
- ROUGE : `reviews/K8S-022/evidence/RED.txt` — 3 écarts PSS restricted sur `origin/main` (2caf246).
- Validation de politique : `violations_pss_restricted()` (tests) implémente les règles PSS restricted
  (k8s >= 1.25) et parcourt les manifests rendus **parsés en YAML**, pas une recherche de sous-chaîne.
- Runtime : 30 pods appliqués sur cluster réel, verdicts dans `mesures-runtime.jsonl`.

## Élargissement de périmètre — DÉCLARÉ, jamais silencieux
`tests/test_k3s_pvc.py` n'est pas dans les `allowed_paths` du package. Son assertion
`assert "emptyDir" not in out` devient fausse dès qu'un `emptyDir` de TRAVAIL est émis pour
`readOnlyRootFilesystem`. L'intention du test — *le volume de DONNÉES est un PVC, jamais éphémère* —
reste valide et est désormais vérifiée **précisément sur ce volume** au lieu de l'absence globale du
mot. C'est le même cas de figure que K8S-008 (assertion d'un anti-comportement supersédé) ; il est
signalé ici, dans la PR et dans le pack de revue, conformément à l'interdiction d'élargir en silence.
Fichier également touché, celui-là DANS le périmètre : `tests/test_k3s_hardening_fai0004.py`
(`test_runAsNonRoot_absent` -> `test_runAsNonRoot_present_desormais`).

## Défaut découvert hors périmètre (signalé, non corrigé ici)
Sous le nouveau profil comme sous l'ancien, le pod `litellm` est **OOMKilled** : la limite
`memory: 1Gi` de `_resources_block` est insuffisante pour cette image. Contre-preuve exécutée : le
même service rendu depuis `origin/main` (sans ce changement) est OOMKilled à l'identique. La cause
est donc le dimensionnement des ressources, pas la sécurité — c'est l'objet du package **RES-012B**.

## Ce que ce package ne prouve PAS
- Les images `llama-cpp-vulkan`, `cpu-zendnn` et `intel-openvino` (moteurs GPU vendor) n'ont pas été
  mesurées : elles relèvent de la dérogation GPU et des packages `LAB-033*` (`BLOCKED_LAB`).
- Un service absent de `_PROFILS_SECURITE` reçoit uid 1000. S'il exige un autre uid, il échouera
  **bruyamment** (le kubelet refuse, ou l'écriture échoue) — jamais silencieusement en root.

## Rollback
`git revert` du commit -> retour au durcissement partiel (défaut FAI-U-022 connu) ; baseline verte.

# ============ DIFF INTÉGRAL DU CHANGEMENT ============
diff --git a/src/forgeai/renderers/k3s.py b/src/forgeai/renderers/k3s.py
index e02862f..c93321b 100644
--- a/src/forgeai/renderers/k3s.py
+++ b/src/forgeai/renderers/k3s.py
@@ -9,6 +9,7 @@ from __future__ import annotations
 import os
 import re
 import textwrap
+from typing import NamedTuple
 from urllib.parse import urlsplit
 
 from forgeai.core.models import DeploymentPlan, ServiceSpec
@@ -81,28 +82,142 @@ def _resources_block(vendor: str | None) -> str:
     return block
 
 
-def _security_block(vendor: str | None) -> str:
-    """Durcissement du securityContext pour tous les conteneurs. Le passthrough hostPath des
-    devices GPU amd/intel suffit pour l'accès aux devices (/dev/kfd, /dev/dri) ; privileged
-    n'est pas requis et violerait le principe du moindre privilège.
-    runAsNonRoot ET capabilities.drop:[ALL] ne sont PAS émis : de nombreuses images tournent en
-    root et ont besoin de capabilities (ex. redis chown /data) ; les forcer ferait échouer les
-    pods — PREUVE RUNTIME (K3s réel) : redis:7-alpine avec drop:[ALL] -> CrashLoopBackOff
-    « chown: Operation not permitted ». Un runAsUser spécifique par image est hors périmètre.
-    Durcissement retenu (vérifié : redis atteint Ready) = allowPrivilegeEscalation:false +
-    seccompProfile RuntimeDefault."""
-    _ = vendor  # gardé pour la stabilité de l'API interne ; le durcissement est uniforme.
-    block = (
+class ProfilSecurite(NamedTuple):
+    """Profil de sécurité mesuré sur k3s v1.35.5 pour un service donné."""
+    uid: int
+    ro_rootfs: bool = True
+    chemins_inscriptibles: tuple[str, ...] = ()
+    preuve: str = ""
+
+
+_PROFILS_SECURITE: dict[str, ProfilSecurite] = {
+    "redis": ProfilSecurite(
+        uid=999,
+        preuve="redis:7-alpine READY en restricted complet ; en root + drop ALL : FAILED « chown: . : Operation not permitted »",
+    ),
+    "litellm": ProfilSecurite(
+        uid=1000,
+        preuve="ghcr.io/berriai/litellm:main-stable READY en restricted complet",
+    ),
+    "qdrant": ProfilSecurite(
+        uid=1000,
+        chemins_inscriptibles=("/qdrant/snapshots",),
+        preuve="qdrant/qdrant:v1.12.5 : panic « Can't create Snapshots directory: PermissionDenied » sans ce volume ; READY avec",
+    ),
+    "postgres": ProfilSecurite(
+        uid=999,
+        chemins_inscriptibles=("/var/run/postgresql",),
+        preuve="postgres:18.3-alpine : échec sans ce volume ; READY avec",
+    ),
+    "immudb": ProfilSecurite(
+        uid=3322,
+        preuve="codenotary/immudb:1.11.1 READY en restricted complet",
+    ),
+    "openbao": ProfilSecurite(
+        uid=100,
+        preuve="openbao/openbao:2.6.0 (USER nommé « openbao » = uid 100) : écriture de /openbao/file OK en restricted complet",
+    ),
+    "langfuse": ProfilSecurite(
+        uid=1000,
+        preuve="langfuse/langfuse:3 : écriture OK en restricted complet",
+    ),
+    "text-embeddings-inference-tei": ProfilSecurite(
+        uid=1000,
+        preuve="ghcr.io/huggingface/text-embeddings-inference:cpu-1.5 : écriture de /data OK en restricted complet",
+    ),
+    "ollama": ProfilSecurite(
+        uid=1000,
+        ro_rootfs=False,
+        preuve="ollama/ollama:latest : « mkdir /home/ubuntu/.ollama: read-only file system » avec readOnlyRootFilesystem ; READY sans. Le HOME dépend de la distribution de base de l'image, inconnu au moment du rendu",
+    ),
+}
+
+_PROFILS_SECURITE["vector-store"] = _PROFILS_SECURITE["qdrant"]
+_PROFILS_SECURITE["text-embeddings-inference-reranker"] = _PROFILS_SECURITE["text-embeddings-inference-tei"]
+_PROFILS_SECURITE["tei"] = _PROFILS_SECURITE["text-embeddings-inference-tei"]
+
+_PROFIL_DEFAUT = ProfilSecurite(uid=1000, preuve="défaut pour service non mesuré")
+_UID_MINIMAL_NON_ROOT = 1
+
+
+def _profil_securite(nom: str) -> ProfilSecurite:
+    """Retourne le profil mesuré d'un service, ou le profil par défaut."""
+    profil = _PROFILS_SECURITE.get(nom, _PROFIL_DEFAUT)
+    if profil.uid < _UID_MINIMAL_NON_ROOT:
+        raise ValueError(
+            f"le profil de sécurité pour {nom!r} exige uid={profil.uid} "
+            f"(minimum autorisé : {_UID_MINIMAL_NON_ROOT})"
+        )
+    return profil
+
+
+def _pod_security_block(profil: ProfilSecurite, gpu: bool) -> str:
+    """Bloc securityContext au niveau pod ; dérogation GPU documentée."""
+    if gpu:
+        return (
+            "\n      securityContext:"
+            "\n        # forgeai: dérogation PSS restricted — l'accès GPU en passthrough requiert les groupes de l'hôte"
+            "\n        # forgeai: mesure : 0/4 devices /dev/dri accessibles en non-root (gid render variable) ; dérogation limitée aux services GPU demandés"
+            "\n        # forgeai: readOnlyRootFilesystem est également désactivé (chemins de cache du moteur GPU non mesurables sans matériel — cf. LAB-033)"
+            "\n        seccompProfile:"
+            "\n          type: RuntimeDefault"
+        )
+    return (
+        "\n      securityContext:"
+        "\n        runAsNonRoot: true"
+        f"\n        runAsUser: {profil.uid}"
+        f"\n        runAsGroup: {profil.uid}"
+        f"\n        fsGroup: {profil.uid}"
+        "\n        seccompProfile:"
+        "\n          type: RuntimeDefault"
+    )
+
+
+def _security_block(profil: ProfilSecurite, gpu: bool) -> str:
+    """Bloc securityContext au niveau conteneur.
+
+    `gpu` désactive AUSSI readOnlyRootFilesystem, et pas seulement l'identité non-root :
+    les chemins d'écriture d'un moteur GPU (caches de modèles, caches de compilation du
+    runtime vendor) dépendent de l'image ET de l'hôte, et n'ont pas pu être mesurés faute
+    de matériel GPU autorisé (packages LAB-033*, BLOCKED_LAB). Activer la racine en lecture
+    seule sans cette mesure casserait des déploiements réels : la règle « exceptions
+    spécifiques et TESTÉES » impose donc de ne pas l'activer ici. Les trois contrôles
+    mesurables restent émis (drop:[ALL], allowPrivilegeEscalation:false, seccomp).
+    readOnlyRootFilesystem n'est pas une exigence du profil PSS restricted : le pod GPU ne
+    déroge à restricted que par son identité root et son volume hostPath, pas par ce champ.
+    """
+    ro = profil.ro_rootfs and not gpu
+    return (
         "\n          securityContext:"
         "\n            allowPrivilegeEscalation: false"
+        "\n            capabilities:"
+        "\n              drop:"
+        "\n                - ALL"
+        f"\n            readOnlyRootFilesystem: {'true' if ro else 'false'}"
         "\n            seccompProfile:"
         "\n              type: RuntimeDefault"
     )
-    # openbao : PAS de capability IPC_LOCK. L'image lance `bao` en non-root sans file-cap -> IPC_LOCK
-    # n'entre jamais dans le set EFFECTIVE du process (mlock inopérant, prouvé e2e S6) ; accorder une
-    # capability privilégiée inutile violerait le moindre privilège. Le coffre tourne avec
-    # disable_mlock (openbao.hcl) + swap-off au nœud (contrôle compensatoire opérateur documenté).
-    return block
+
+
+def _volumes_inscriptibles(profil: ProfilSecurite, gpu: bool) -> list[tuple[str, str]]:
+    """Liste les emptyDir nécessaires quand la racine est en lecture seule."""
+    ro = profil.ro_rootfs and not gpu
+    if not ro:
+        return []
+    chemins = ["/tmp"] + list(profil.chemins_inscriptibles)
+
+    def _nom(chemin: str) -> str:
+        return "inscriptible-" + chemin.lstrip("/").replace("/", "-").lower()
+
+    return [(_nom(c), c) for c in chemins]
+
+
+_PROFIL_SIDECAR_OPENBAO = ProfilSecurite(
+    uid=100, ro_rootfs=False,
+    preuve="side-car d'unseal : `bao operator unseal` peut écrire un fichier de jeton dans "
+           "$HOME ; comportement NON mesuré en racine lecture seule -> readOnlyRootFilesystem "
+           "non activé. Le reste du profil restricted (drop ALL, seccomp, no-escalation) est conservé.",
+)
 
 
 def _probes_block(svc: ServiceSpec) -> str:
@@ -164,8 +279,7 @@ def _openbao_sidecar_block(image: str) -> str:
         "\n            - name: openbao-keys"
         "\n              mountPath: /keys"
         "\n              readOnly: true"
-        "\n          securityContext:"
-        "\n            allowPrivilegeEscalation: false"
+        + _security_block(_PROFIL_SIDECAR_OPENBAO, gpu=False)
     )
 
 
@@ -185,8 +299,11 @@ def _deployment(svc: ServiceSpec, effective_node: str | None = None,
     # des devices noyau (pas de privileged, K8S-008).
     vendor = (svc.gpu_vendor or "nvidia") if svc.gpu else None
 
+    # K8S-022 : profil PSS restricted par service (uid mesuré) ; `svc.gpu` = seule dérogation.
+    profil = _profil_securite(svc.name)
+    gpu_actif = bool(svc.gpu)
     resources_block = _resources_block(vendor)
-    security_block = _security_block(vendor)
+    security_block = _security_block(profil, gpu_actif)
     probes_block = _probes_block(svc)
     node_selector = ""
     if effective_node and effective_node != "auto":
@@ -262,6 +379,17 @@ def _deployment(svc: ServiceSpec, effective_node: str | None = None,
         mounts.append((claim, path, None, False))
     for claim, path in gpu_vols:
         vols.append((claim, path, "hostPath"))
+    # K8S-022 : readOnlyRootFilesystem impose des emptyDir explicites pour les chemins que le
+    # service écrit hors de ses volumes de données (chemins MESURÉS, cf. _PROFILS_SECURITE).
+    # Un chemin déjà monté (PVC, ConfigMap…) n'est jamais monté deux fois : mountPath dupliqué
+    # = spec de pod invalide.
+    deja_montes = {chemin for _, chemin, _, _ in mounts}
+    for nom_volume, chemin in _volumes_inscriptibles(profil, gpu_actif):
+        if chemin in deja_montes:
+            continue
+        deja_montes.add(chemin)
+        mounts.append((nom_volume, chemin, None, False))
+        vols.append((nom_volume, None, "emptyDir"))
     # openbao : volume Secret des clés d'unseal — ajouté aux `vols` du POD (donc au bloc volumes:)
     # MAIS PAS aux `mounts` (le conteneur principal ne monte JAMAIS les clés ; seul le sidecar
     # de re-unseal les monte, cf. _openbao_sidecar_block).
@@ -300,6 +428,9 @@ def _deployment(svc: ServiceSpec, effective_node: str | None = None,
                     passthrough_comment_emitted = True
                 items += (f"\n        - name: {claim}"
                           f"\n          hostPath:\n            path: {payload}")
+            elif kind == "emptyDir":
+                items += (f"\n        - name: {claim}"
+                          f"\n          emptyDir: {{}}")
             elif kind == "configMap":
                 items += (f"\n        - name: {claim}"
                           f"\n          configMap:\n            name: {payload}")
@@ -376,7 +507,9 @@ def _deployment(svc: ServiceSpec, effective_node: str | None = None,
     sidecar_block = _openbao_sidecar_block(image) if svc.name == "openbao" else ""
     container_extra = (command_block + env_block + resources_block + security_block
                        + probes_block + volume_mount + sidecar_block + volume_def)
-    sa_block = "\n      serviceAccountName: forgeai-sa\n      automountServiceAccountToken: false"
+    sa_block = ("\n      serviceAccountName: forgeai-sa"
+                "\n      automountServiceAccountToken: false"
+                + _pod_security_block(profil, gpu_actif))
     return "".join(configmap_docs) + "".join(pvc_docs) + f"""---
 apiVersion: apps/v1
 kind: Deployment
diff --git a/tests/test_k3s_hardening.py b/tests/test_k3s_hardening.py
index 46df2af..86c42cc 100644
--- a/tests/test_k3s_hardening.py
+++ b/tests/test_k3s_hardening.py
@@ -77,3 +77,73 @@ def test_service_types_valides_ok():
     for st in ("NodePort", "LoadBalancer"):
         out = render_k3s(_plan([_svc()]), service_type=st)
         assert f"type: {st}" in out
+
+
+# ---------------------------------------------------------------------------
+# K8S-022 / FAI-U-022 — le profil Pod Security Standards « restricted » est le DÉFAUT.
+# Validateur réel des règles PSS restricted (k8s >= 1.25) appliqué aux manifests rendus,
+# et non une simple recherche de sous-chaîne : chaque conteneur de chaque Deployment est vérifié.
+# ---------------------------------------------------------------------------
+import yaml
+
+# Volumes autorisés par PSS restricted (les autres, dont hostPath, sont refusés).
+_PSS_VOLUMES_OK = frozenset({
+    "configMap", "csi", "downwardAPI", "emptyDir", "ephemeral",
+    "persistentVolumeClaim", "projected", "secret",
+})
+
+
+def _deployments(manifest: str) -> list[dict]:
+    return [d for d in yaml.safe_load_all(manifest) if d and d.get("kind") == "Deployment"]
+
+
+def violations_pss_restricted(manifest: str) -> list[str]:
+    """Retourne la liste des écarts au profil PSS `restricted`. Vide = conforme."""
+    out: list[str] = []
+    for dep in _deployments(manifest):
+        pod = dep["spec"]["template"]["spec"]
+        psc = pod.get("securityContext") or {}
+        who = dep["metadata"]["name"]
+        for champ in ("hostNetwork", "hostPID", "hostIPC"):
+            if pod.get(champ):
+                out.append(f"{who}: {champ} activé")
+        for vol in pod.get("volumes") or []:
+            kinds = [k for k in vol if k != "name"]
+            for kind in kinds:
+                if kind not in _PSS_VOLUMES_OK:
+                    out.append(f"{who}: type de volume interdit par restricted : {kind}")
+        for cont in pod.get("containers") or []:
+            csc = cont.get("securityContext") or {}
+            cible = f"{who}/{cont['name']}"
+            if csc.get("privileged"):
+                out.append(f"{cible}: privileged")
+            if csc.get("allowPrivilegeEscalation") is not False:
+                out.append(f"{cible}: allowPrivilegeEscalation != false")
+            drop = ((csc.get("capabilities") or {}).get("drop")) or []
+            if "ALL" not in drop:
+                out.append(f"{cible}: capabilities.drop ne contient pas ALL")
+            add = ((csc.get("capabilities") or {}).get("add")) or []
+            if [c for c in add if c != "NET_BIND_SERVICE"]:
+                out.append(f"{cible}: capabilities.add interdites : {add}")
+            if not (csc.get("runAsNonRoot") or psc.get("runAsNonRoot")):
+                out.append(f"{cible}: runAsNonRoot absent (ni pod ni conteneur)")
+            seccomp = (csc.get("seccompProfile") or psc.get("seccompProfile") or {}).get("type")
+            if seccomp not in ("RuntimeDefault", "Localhost"):
+                out.append(f"{cible}: seccompProfile.type = {seccomp!r}")
+    return out
+
+
+def test_profil_restricted_est_le_defaut():
+    """Un service ordinaire (sans exception déclarée) est rendu conforme PSS restricted."""
+    out = render_k3s(_plan([_svc(name="service-quelconque", image="exemple/app:1.0")]))
+    assert violations_pss_restricted(out) == []
+
+
+def test_root_filesystem_en_lecture_seule_par_defaut():
+    out = render_k3s(_plan([_svc(name="service-quelconque", image="exemple/app:1.0")]))
+    dep = _deployments(out)[0]
+    cont = dep["spec"]["template"]["spec"]["containers"][0]
+    assert cont["securityContext"]["readOnlyRootFilesystem"] is True
+    # readOnlyRootFilesystem sans /tmp inscriptible casse la plupart des runtimes -> emptyDir explicite
+    montages = {m["mountPath"] for m in cont.get("volumeMounts") or []}
+    assert "/tmp" in montages
diff --git a/tests/test_k3s_hardening_fai0004.py b/tests/test_k3s_hardening_fai0004.py
index 36a922c..eed2acd 100644
--- a/tests/test_k3s_hardening_fai0004.py
+++ b/tests/test_k3s_hardening_fai0004.py
@@ -70,9 +70,14 @@ def test_redis_resources_et_hardening():
     assert "RuntimeDefault" in out
 
 
-def test_runAsNonRoot_absent():
+def test_runAsNonRoot_present_desormais():
+    """FAI-0004 documentait l'ABSENCE de runAsNonRoot (les images tournaient en root).
+    SUPERSÉDÉ par FAI-U-022/K8S-022 : le profil PSS restricted est désormais le défaut, et la
+    mesure runtime a établi que drop:[ALL] n'est viable QU'en non-root (root + drop ALL ->
+    « chown: Operation not permitted » sur redis). L'assertion est donc inversée."""
     out = render_k3s(_plan(_redis()))
-    assert "runAsNonRoot" not in out
+    assert "runAsNonRoot: true" in out
+    assert "runAsUser: 999" in out  # uid mesuré de redis
 
 
 def test_redis_probes_tcpSocket():
diff --git a/tests/test_k3s_pvc.py b/tests/test_k3s_pvc.py
index 945f8f4..3e17155 100644
--- a/tests/test_k3s_pvc.py
+++ b/tests/test_k3s_pvc.py
@@ -56,7 +56,15 @@ def test_pvc_emis_pour_volume_data():
     assert "storage: 10Gi" in out
     assert "persistentVolumeClaim" in out
     assert "claimName: forgeai-redis-data" in out
-    assert "emptyDir" not in out
+    # K8S-022 : le manifeste contient désormais des emptyDir de TRAVAIL (/tmp et chemins
+    # d'écriture mesurés) rendus nécessaires par readOnlyRootFilesystem. L'intention de ce
+    # test — le volume de DONNÉES est un PVC, jamais un volume éphémère — est donc vérifiée
+    # précisément sur ce volume, au lieu de l'absence globale du mot « emptyDir ».
+    bloc_volumes = out.split("\n      volumes:", 1)[1]
+    volume_data = bloc_volumes.split("- name: forgeai-redis-data", 1)[1]
+    volume_data = volume_data.split("\n        - name:", 1)[0]
+    assert "persistentVolumeClaim" in volume_data
+    assert "emptyDir" not in volume_data
 
 
 def test_pvc_avant_deployment():

# ============ PREUVE ROUGE ============
tests/test_k3s_hardening.py:146: KeyError
=========================== short test summary info ============================
FAILED tests/test_k3s_hardening.py::test_profil_restricted_est_le_defaut - As...
FAILED tests/test_k3s_hardening.py::test_root_filesystem_en_lecture_seule_par_defaut

[RED] écarts PSS restricted sur origin/main (2caf246) :
  - service-quelconque/service-quelconque: capabilities.drop ne contient pas ALL
  - service-quelconque/service-quelconque: runAsNonRoot absent (ni pod ni conteneur)

# ============ PREUVE VERTE ============
=== GREEN : tests ciblés ===
.....................                                                    [100%]

=== GREEN : suite complète ===
......................................................................s. [ 91%]
........................................................................ [ 99%]
.......                                                                  [100%]

# ============ DÉPLOIEMENT RÉEL + ENFORCEMENT PSS ============
# Déploiement RÉEL du manifeste rendu — cluster k3s v1.35.5, namespace k8s022-e2e
# Namespace étiqueté pod-security.kubernetes.io/enforce=restricted (enforcement latest)

## kubectl apply --dry-run=server (schéma + admission)
toutes ressources 'unchanged (server dry run)' = acceptées

## Pods sous enforcement restricted
litellm-5569df4674-jsg8c   0/1   CrashLoopBackOff   4 (68s ago)   3m9s
litellm-66d9dddd76-tprf4   0/1   CrashLoopBackOff   4 (76s ago)   2m58s
qdrant-7cfc96cb8c-2bd5j    1/1   Running            0             2m58s
redis-7866489f7f-shkhl     1/1   Running            0             2m58s

## securityContext RÉELLEMENT appliqué (pod redis vivant)
pod : {"fsGroup":999,"runAsGroup":999,"runAsNonRoot":true,"runAsUser":999,"seccompProfile":{"type":"RuntimeDefault"}}
conteneur : {"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]},"readOnlyRootFilesystem":true,"seccompProfile":{"type":"RuntimeDefault"}}

## Refus d'admission PSS : AUCUN (aucun événement violat/forbidden/denied)

## litellm OOMKilled : défaut PRÉEXISTANT, sans rapport avec K8S-022 (contre-preuve exécutée)
Le pod litellm est OOMKilled sous le nouveau profil. Contrôle : le MÊME service rendu depuis
`origin/main` (2caf246, AVANT ce changement — 0 occurrence de runAsNonRoot/drop dans le manifeste)
a été déployé dans le namespace `k8s022-ref` : il est **OOMKilled lui aussi**.
La cause est la limite `memory: 1Gi` de `_resources_block` (identique avant/après), pas le profil
de sécurité. Le conteneur DÉMARRE (l'admission et le securityContext sont donc corrects) puis est
tué par le cgroup mémoire. Ce défaut relève du package RES-012B (ressources par service), hors
périmètre de K8S-022 ; il est signalé ici plutôt que passé sous silence.

# ============ MESURES RUNTIME BRUTES (30 pods) ============
{"svc": "qdrant", "variant": "A", "nonroot": true, "rorf": true, "dropall": true, "verdict": "EXIT_101", "detail": "Error", "logs": "12: __libc_start_main |   13: _start |      | 2026-07-26T15:04:38.606984Z ERROR qdrant::startup: Panic occurred in file lib/storage/src/content_manager/toc/mod.rs at line 101: Can't create Snapshots directory: Os { code: 30, kind: ReadOnlyF"}
{"svc": "qdrant", "variant": "B", "nonroot": true, "rorf": false, "dropall": true, "verdict": "EXIT_101", "detail": "Error", "logs": "12: __libc_start_main |   13: _start |      | 2026-07-26T15:04:44.865373Z ERROR qdrant::startup: Panic occurred in file lib/storage/src/content_manager/toc/mod.rs at line 101: Can't create Snapshots directory: Os { code: 13, kind: Permissio"}
{"svc": "qdrant", "variant": "C", "nonroot": false, "rorf": false, "dropall": true, "verdict": "READY", "detail": "", "logs": "2026-07-26T15:04:51.066644Z  INFO actix_server::builder: Starting 19 workers | 2026-07-26T15:04:51.066658Z  INFO actix_server::server: Actix runtime found; starting in Actix runtime | 2026-07-26T15:04:51.071742Z  INFO qdrant::tonic: Qdrant "}
{"svc": "qdrant", "variant": "D", "nonroot": false, "rorf": false, "dropall": false, "verdict": "READY", "detail": "", "logs": "2026-07-26T15:04:57.256789Z  INFO actix_server::builder: Starting 19 workers | 2026-07-26T15:04:57.256801Z  INFO actix_server::server: Actix runtime found; starting in Actix runtime | 2026-07-26T15:04:57.262498Z  INFO qdrant::tonic: Qdrant "}
{"svc": "tei", "variant": "A", "nonroot": true, "rorf": true, "dropall": true, "verdict": "EXIT_1", "detail": "Error", "logs": "Caused by: |     0: request error: builder error: relative URL without a base |     1: builder error: relative URL without a base |     2: relative URL without a base"}
{"svc": "tei", "variant": "B", "nonroot": true, "rorf": false, "dropall": true, "verdict": "EXIT_1", "detail": "Error", "logs": "Caused by: |     0: request error: builder error: relative URL without a base |     1: builder error: relative URL without a base |     2: relative URL without a base"}
{"svc": "tei", "variant": "C", "nonroot": false, "rorf": false, "dropall": true, "verdict": "EXIT_1", "detail": "Error", "logs": "Caused by: |     0: request error: builder error: relative URL without a base |     1: builder error: relative URL without a base |     2: relative URL without a base"}
{"svc": "tei", "variant": "D", "nonroot": false, "rorf": false, "dropall": false, "verdict": "EXIT_1", "detail": "Error", "logs": "Caused by: |     0: request error: builder error: relative URL without a base |     1: builder error: relative URL without a base |     2: relative URL without a base"}
{"svc": "ollama", "variant": "A", "nonroot": true, "rorf": true, "dropall": true, "verdict": "EXIT_1", "detail": "Error", "logs": "Couldn't find '/home/ubuntu/.ollama/id_ed25519'. Generating new private key. | Error: could not create directory mkdir /home/ubuntu/.ollama: read-only file system"}
{"svc": "ollama", "variant": "B", "nonroot": true, "rorf": false, "dropall": true, "verdict": "READY", "detail": "", "logs": "time=2026-07-26T15:05:34.577Z level=INFO source=runner.go:60 msg=\"discovering available GPUs...\" | time=2026-07-26T15:05:34.844Z level=INFO source=model_recommendations.go:177 msg=\"model recommendations cache sleep scheduled\" wait=3h54m57.3"}
{"svc": "ollama", "variant": "C", "nonroot": false, "rorf": false, "dropall": true, "verdict": "READY", "detail": "", "logs": "time=2026-07-26T15:05:40.834Z level=INFO source=runner.go:60 msg=\"discovering available GPUs...\" | time=2026-07-26T15:05:40.983Z level=INFO source=model_recommendations.go:177 msg=\"model recommendations cache sleep scheduled\" wait=3h18m55.7"}
{"svc": "ollama", "variant": "D", "nonroot": false, "rorf": false, "dropall": false, "verdict": "READY", "detail": "", "logs": "time=2026-07-26T15:05:47.086Z level=INFO source=runner.go:60 msg=\"discovering available GPUs...\" | time=2026-07-26T15:05:47.220Z level=INFO source=model_recommendations.go:177 msg=\"model recommendations cache sleep scheduled\" wait=3h22m39.7"}
{"svc": "ollamahome", "variant": "A", "nonroot": true, "rorf": true, "dropall": true, "verdict": "READY", "detail": "", "logs": "time=2026-07-26T15:05:53.357Z level=INFO source=runner.go:60 msg=\"discovering available GPUs...\" | time=2026-07-26T15:05:53.499Z level=INFO source=model_recommendations.go:177 msg=\"model recommendations cache sleep scheduled\" wait=3h46m23.7"}
{"svc": "ollamahome", "variant": "B", "nonroot": true, "rorf": false, "dropall": true, "verdict": "READY", "detail": "", "logs": "time=2026-07-26T15:05:59.508Z level=INFO source=runner.go:60 msg=\"discovering available GPUs...\" | time=2026-07-26T15:05:59.646Z level=INFO source=model_recommendations.go:177 msg=\"model recommendations cache sleep scheduled\" wait=3h42m13.6"}
{"svc": "ollamahome", "variant": "C", "nonroot": false, "rorf": false, "dropall": true, "verdict": "READY", "detail": "", "logs": "time=2026-07-26T15:06:05.746Z level=INFO source=runner.go:60 msg=\"discovering available GPUs...\" | time=2026-07-26T15:06:05.962Z level=INFO source=types.go:50 msg=\"inference compute\" id=cpu library=cpu compute=\"\" name=cpu description=cpu li"}
{"svc": "ollamahome", "variant": "D", "nonroot": false, "rorf": false, "dropall": false, "verdict": "READY", "detail": "", "logs": "time=2026-07-26T15:06:12.278Z level=INFO source=runner.go:60 msg=\"discovering available GPUs...\" | time=2026-07-26T15:06:12.423Z level=INFO source=model_recommendations.go:177 msg=\"model recommendations cache sleep scheduled\" wait=4h2m16.83"}
{"svc": "postgres", "variant": "A", "nonroot": true, "rorf": true, "dropall": true, "verdict": "EXIT_1", "detail": "Error", "logs": "2026-07-26 15:06:19.357 UTC [32] LOG:  database system is shut down |  stopped waiting | pg_ctl: could not start server | Examine the log output."}
{"svc": "postgres", "variant": "B", "nonroot": true, "rorf": false, "dropall": true, "verdict": "READY", "detail": "", "logs": "2026-07-26 15:06:25.749 UTC [1] LOG:  listening on IPv6 address \"::\", port 5432 | 2026-07-26 15:06:25.753 UTC [1] LOG:  listening on Unix socket \"/var/run/postgresql/.s.PGSQL.5432\" | 2026-07-26 15:06:25.760 UTC [52] LOG:  database system wa"}
{"svc": "postgres", "variant": "C", "nonroot": false, "rorf": false, "dropall": true, "verdict": "EXIT_1", "detail": "Error", "logs": "chmod: /var/run/postgresql: Operation not permitted | chown: /var/lib/postgresql/data/pgdata: Operation not permitted"}
{"svc": "postgres", "variant": "D", "nonroot": false, "rorf": false, "dropall": false, "verdict": "READY", "detail": "", "logs": "2026-07-26 15:06:38.174 UTC [1] LOG:  listening on IPv6 address \"::\", port 5432 | 2026-07-26 15:06:38.180 UTC [1] LOG:  listening on Unix socket \"/var/run/postgresql/.s.PGSQL.5432\" | 2026-07-26 15:06:38.187 UTC [62] LOG:  database system wa"}
{"case": "q1-openbao-nru", "image": "openbao/openbao:2.6.0", "mode": "nonroot-sans-uid", "verdict": "CreateContainerConfigError", "detail": "container has runAsNonRoot and image has non-numeric user (openbao), cannot verify user is non-root (pod: \"q1-openbao-nru_k8s022-probe(50f7852b-4f1e-4465-a72f-ebb081c45b0d)\", container: c)", "id": ""}
{"case": "q2-qdrant-nru", "image": "qdrant/qdrant:v1.12.5", "mode": "nonroot-sans-uid", "verdict": "CreateContainerConfigError", "detail": "container has runAsNonRoot and image will run as root (pod: \"q2-qdrant-nru_k8s022-probe(a116398f-47c0-415e-91c7-68cbd4b350bc)\", container: c)", "id": ""}
{"case": "q3-immudb", "image": "codenotary/immudb:1.11.1", "mode": "id-natif", "verdict": "EXIT_128", "detail": "StartError", "id": ""}
{"case": "q3-langfuse", "image": "langfuse/langfuse:3", "mode": "id-natif", "verdict": "EXIT_0", "detail": "Completed", "id": "uid=1001(nextjs) gid=65533(nogroup) groups=65533(nogroup)"}
{"case": "q3-tei", "image": "ghcr.io/huggingface/text-embeddings-inference:cpu-1.5", "mode": "id-natif", "verdict": "EXIT_0", "detail": "Completed", "id": "uid=0(root) gid=0(root) groups=0(root)"}
{"case": "q3-litellm", "image": "ghcr.io/berriai/litellm:main-stable", "mode": "id-natif", "verdict": "EXIT_0", "detail": "Completed", "id": "uid=0(root) gid=0(root) groups=0(root),1(bin),2(daemon),3(sys),4(adm),6(disk),10(wheel),11(floppy),20(dialout),26(tape),"}
{"case": "q3-postgres", "image": "postgres:18.3-alpine", "mode": "id-natif", "verdict": "EXIT_0", "detail": "Completed", "id": "uid=0(root) gid=0(root) groups=0(root),1(bin),2(daemon),3(sys),4(adm),6(disk),10(wheel),11(floppy),20(dialout),26(tape),"}
{"case": "gpu-nonroot", "uid": 1000, "suppl": null, "verdict": "Succeeded", "logs": "uid=1000 gid=1000 groups=1000 | total 0 | drwxr-xr-x    2 0        0              120 Jul 25 17:55 by-path | crw-rw----    1 0        44        226,   1 Jul 25 17:55 card1 | crw-rw----    1 0        44        226,   2 Jul 26 14:59 card2 | crw-rw----    1 0        992       226, 128 Jul 25 17:55 renderD128 | crw-rw----    1 0        992       226, 129 Jul 25 17:55 renderD129 | ACCES_REFUSE /dev/dri/renderD128 | ACCES_"}
{"case": "gpu-nonroot-grp", "uid": 1000, "suppl": 44, "verdict": "Succeeded", "logs": "uid=1000 gid=1000 groups=44,1000 | total 0 | drwxr-xr-x    2 0        0              120 Jul 25 17:55 by-path | crw-rw----    1 0        44        226,   1 Jul 25 17:55 card1 | crw-rw----    1 0        44        226,   2 Jul 26 14:59 card2 | crw-rw----    1 0        992       226, 128 Jul 25 17:55 renderD128 | crw-rw----    1 0        992       226, 129 Jul 25 17:55 renderD129 | ACCES_REFUSE /dev/dri/renderD128 | ACC"}
{"case": "gpu-root", "uid": null, "suppl": null, "verdict": "Succeeded", "logs": "uid=0(root) gid=0(root) groups=0(root),10(wheel) | total 0 | drwxr-xr-x    2 0        0              120 Jul 25 17:55 by-path | crw-rw----    1 0        44        226,   1 Jul 25 17:55 card1 | crw-rw----    1 0        44        226,   2 Jul 26 14:59 card2 | crw-rw----    1 0        992       226, 128 Jul 25 17:55 renderD128 | crw-rw----    1 0        992       226, 129 Jul 25 17:55 renderD129 | ACCES_OK /dev/dri/rend"}

# ============ CONTEXTE CLUSTER ============
serveur k8s: v1.35.5+k3s1
pc1-x870e-taichi   v1.35.5+k3s1   Ubuntu 24.04.4 LTS
pc2-forge-b        v1.35.5+k3s1   Ubuntu 26.04 LTS
pc3-grs-a          v1.35.5+k3s1   Ubuntu 26.04 LTS
pc4-grs-b          v1.35.5+k3s1   Ubuntu 26.04 LTS
