# LAB-033N — Qualifier le chemin NVIDIA de bout en bout en laboratoire

## Identité
- Package : `LAB-033N` (`coordination/work-packages.json`, status EXTERNAL, ide CLAUDE_CODE)
- Issue : #279 · Dépendance : CAP-033A (**livrée** — registre mission seq 288, PR #294)
- Branche : `story/LAB-033N` · Tier : **T1**
- Banc : cluster k3s v1.35.5 réel, 4 nœuds Ready ; **nœud cible `pc3-grs-a`** (RTX 5080 16 Gio +
  RTX 2080 SUPER 8 Gio, driver 595.71.05, CUDA 13.2, GPU Operator installé,
  `nvidia.com/gpu` allouable = 2, label `forge.gpu=nvidia`). Autorisation : carte blanche
  Nathan 2026-07-30 sur pc2/pc3/pc4 (machines de laboratoire, reformatage prévu).

## Contexte
CAP-033A a aligné les claims docs sur les preuves disponibles : la ligne NVIDIA de
`Docs/reference/gpu-drivers-support.md` cite HW-010, qui ne prouve que la **détection** et la
recommandation de driver. Le chemin de **déploiement** GPU n'a jamais été mesuré sur matériel :
`renderers/k3s.py` l'acte lui-même (commentaires « packages LAB-033*, BLOCKED_LAB », zones
`_pod_security_block`/`_security_block`). Le renderer émet `nvidia.com/gpu: "1"` en *supposant*
le device plugin présent sur le cluster (le GPU Operator est recommandé par `drivers.py`,
jamais déployé par le toolkit) — hypothèse jamais vérifiée en réel.

## Décision
Qualifier le chemin NVIDIA par le **flux produit, sans aucune étape posée à la main** :

```
sonde matérielle RÉELLE de pc3 (chemin produit B-07, SSH)
→ derive_profile (VRAM mesurées → minimal-gpu-cuda)
→ assemble_plan(target=K3S, placement service GPU → pc3-grs-a)
→ valider_placement (inventaire nœuds, vendor nvidia)
→ render_k3s → manifeste appliqué TEL QUEL (kubectl apply)
→ pod GPU Running SUR pc3 → inference réelle servie par le GPU
→ teardown propre
```

Véhicule : script versionné `scripts/proof/prove_gpu_nvidia_e2e.py` (patron
`prove_ubuntu_vierge.sh` : rejouable, evidence verbatim, teardown en `finally`), avec un mode
`--render-only` exécutable sans cluster (partie CI).

## Critères d'acceptation (tous mesurés — run #2, 2026-07-30, `LAB-033N-PROOF-OK`)
- [x] **T1-CI-1** : `prove_gpu_nvidia_e2e.py --render-only` produit un manifeste où le service
  GPU porte `nvidia.com/gpu: "1"` (limits) et où le Namespace porte ses étiquettes PSS —
  vérifié par `tests/test_prove_gpu_nvidia_e2e.py` (5 passed, **sans cluster**).
- [x] **T1-CI-2** : test docs (`tests/test_docs_consistency.py`) : ROUGE capturé
  (`evidence/RED.txt`, 1 failed/4 passed) puis VERT (`evidence/GREEN-docs.txt`, 5 passed).
- [x] **T1-BANC-1** : sonde **réelle** de pc3 par le produit installé sur place
  (`evidence/hardware-pc3.json` : Ultra 7 265KF, 30,5 Go, RTX 5080 16303 + 2080 SUPER
  8192 Mio) → profil `minimal-gpu-cuda` dérivé des mesures.
- [x] **T1-BANC-2** : manifeste appliqué **tel quel** ; ollama et vector-store `1/1 Running`
  sur `pc3-grs-a` (`evidence/DEPLOIEMENT-REEL.txt`) ; namespace né avec ses étiquettes PSS.
- [x] **T1-BANC-3** : (a) `nvidia.com/gpu` alloué `1` pendant le run, `0` après ;
  (b) `nvidia-smi` dans le pod voit la RTX 5080 (driver 595.71.05, CUDA 13.2) ;
  (c) inference réelle qwen2.5:0.5b — 185 tokens, `llama-server 726 MiB` de VRAM
  échantillonnée **pendant** la génération (`evidence/mesure-gpu-inference.txt`).
- [x] **T1-BANC-4** : teardown vérifié par le script : namespace disparu, allocation GPU
  retombée à 0 (assertion programmatique, pas une lecture d'humain).
- [x] **T1-DOC** : ligne NVIDIA de `gpu-drivers-support.md` mise à jour (AMD/Intel intactes) ;
  chemins d'écriture GPU mesurés : `/root/.nv/ComputeCache/*` (+ `/root/.ollama` déjà en
  PVC) — input consigné pour une future levée de `readOnlyRootFilesystem`.
- [x] **Gates** : `pytest` complet vert (exit 0, 1 skip préexistant), `no_stub_scan.py --all`
  au commit, revue scellée 3/3 à suivre (section Revue).

## Findings mesurés au banc (run #1, 2026-07-30 — échec honnête)
Le run #1 du banc a produit `LAB-033N-PROOF-FAIL` (pods pas Ready en 420 s) avec un
**finding produit majeur**, capturé verbatim dans `evidence/finding-oom-ollama.txt` :
- **OOMKill du moteur LLM** : le pod ollama est rendu avec `limits.memory: 256Mi` et meurt
  en `exit 137 (OOMKilled)` ~10 s après démarrage, pendant « discovering available GPUs »
  (chargement des bibliothèques CUDA). Cause racine vérifiée : la table ADR RES-012A
  contient une classe `llm` (4Gi/8Gi) mais `assemble_plan` n'assigne **aucune**
  `resource_class` aux services du stack → tout hérite du défaut `utilitaire` (256Mi).
  Correctif chirurgical dans CETTE story (data-driven, la table ADR n'est pas modifiée) :
  les overlays déclarent `resource_class` (`ollama`→`llm`, `vector-store`→`db`) et
  `assemble_plan` la transmet. RED dédié : `tests/test_res_classes_stack_minimal.py`.
- **Mesures collatérales positives** : sonde portable produit OK sur pc3 (30,5 Go RAM,
  RTX 5080 + 2080 SUPER — `evidence/hardware-pc3.json`) ; egress-deny des NetworkPolicies
  effectif (refus `ollama.com:443` visible dans les logs du pod) ; avertissement PSS
  `warn=restricted` émis à l'apply (mesuré) ; image épinglée par digest tirée (3,26 Go) ;
  teardown propre vérifié (désallocation GPU contrôlée par le script).

### Findings run #2 (PROOF-OK — à traiter en stories de suivi, hors périmètre ici)
- **F2 — le stack rendu ne peut pas amorcer son propre modèle** : `ollama pull qwen2.5:0.5b`
  (le modèle déclaré par le plan) est **bloqué** par les NetworkPolicies rendues
  (deny egress + allow-DNS seul) — échec verbatim + policies dans
  `evidence/networkpolicy-finding.txt`. Le run a appliqué une policy **de banc** étiquetée
  (`evidence/banc-lab033n-egress-temporaire.yaml`), tiré le modèle, puis l'a retirée avant
  l'inference. Décision produit à cadrer : egress d'amorçage opt-in vs pré-provisionnement.
- **F3 — le NodePort rendu est inaccessible sous les policies rendues** : l'appel
  `http://100.81.54.24:32058/api/generate` échoue ; l'inference a dû passer par le fallback
  `kubectl port-forward` (consigné). Le point d'entrée utilisateur déclaré par le manifeste
  ne fonctionne pas en l'état — ingress deny sans règle d'admission pour le NodePort.
- **F4 (mesure)** : chemins d'écriture du pod GPU pendant l'inference =
  `/root/.nv/ComputeCache/*` uniquement (hors PVC modèles) — la levée de
  `readOnlyRootFilesystem` (cf. `k3s.py`, commentaires LAB-033) devient possible avec un
  `emptyDir` sur `/root/.nv`.

## Preuves (chemins attendus)
- `reviews/LAB-033N/evidence/RED.txt` — test docs rouge sur l'état avant story.
- `reviews/LAB-033N/evidence/manifeste-rendu.yaml` — le manifeste exact appliqué.
- `reviews/LAB-033N/evidence/DEPLOIEMENT-REEL.txt` — sorties kubectl verbatim
  (nodes, pod Running sur pc3, describe, allocations).
- `reviews/LAB-033N/evidence/mesure-gpu-inference.txt` — nvidia-smi dans le pod,
  mémoire GPU pendant l'inference, chemins d'écriture mesurés.
- `Registres/PATCH-LAB-033N.jsonl` + `Registres/mission.jsonl` (`story_complete`).

## Revue scellée
APPROVE **3/3** — `reviews/LAB-033N/*.verdict.json`, sceau `prompt_sha256`
`296a225fb49f1d19…`, vendors distincts **alibaba / deepseek / xiaomi** (≠ vendor du codeur,
Moonshot/Kimi — swap appliqué après routes instables 429/408 sur deux reviewers du trio
initial, journalisé ici). Dépouillement déterministe : `python3 scripts/revue.py tally
reviews/LAB-033N` → `{"result":"APPROVE","reason":"3/3 APPROVE"}`, zéro objection bloquante.

**Objection mineure examinée et REJETÉE avec preuve** (un reviewer affirmait que
`evidence/manifeste-rendu.yaml` datait du run #1 pré-correctif, citant
`requests.memory=4608Mi / limits.memory=10240Mi`) : ces deux valeurs sont le **ResourceQuota
agrégé** du namespace, dont la somme post-correctif est exactement
`4096+512 = 4608 Mi` et `8192+2048 = 10240 Mi` ; le conteneur ollama du même fichier porte
bien `memory: "8Gi"` et `nvidia.com/gpu: "1"`. Horodatages concordants :
`deploy-minimal.json` 03:53:27 → `manifeste-rendu.yaml` 03:56:43 → `DEPLOIEMENT-REEL.txt`
03:57:54. Le reviewer a confondu quota de namespace et limite de conteneur ; aucune
correction n'était requise.

## Rollback
Le script est idempotent et son teardown est en `finally` ; en cas d'échec mi-course :
`kubectl delete namespace <ns du plan>` suffit. `git revert` de la PR → la ligne docs revient
au claim HW-010 (état CAP-033A connu) ; aucun état résiduel côté cluster.

## Écart résiduel (à ne pas masquer)
- La qualification vaut pour **ce banc** (k3s v1.35.5, GPU Operator présent, driver 595.71.05,
  RTX 5080/2080 SUPER) — ce n'est pas une matrice multi-versions/multi-GPU.
- `k3s.py` (`readOnlyRootFilesystem` désactivé sur pods GPU) reste **inchangé** : cette story
  mesure les chemins d'écriture et les consigne ; la levée éventuelle = story dédiée.
- pc2 (NVIDIA laptop hybride, device plugin en CrashLoopBackOff) : **hors périmètre** — le
  nœud qualifiant est pc3 ; l'état de pc2 est consigné au suivi banc, sans impact sur ce
  chemin.
