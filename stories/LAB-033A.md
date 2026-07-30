# LAB-033A — Qualifier le chemin AMD de bout en bout en laboratoire

## Identité
- Package : `LAB-033A` (`coordination/work-packages.json`, status EXTERNAL, ide CLAUDE_CODE)
- Issue : #282 · Dépendance : CAP-033A (**livrée** — registre mission seq 288, PR #294)
- Branche : `story/LAB-033A` · Tier : **T1** · Précédent direct : LAB-033N (PR #301)
- Banc : cluster k3s v1.35.5 réel ; **nœud cible `pc4-grs-b`** — Ryzen 9 9950X3D2, 45,1 Gio RAM,
  **3 GPU AMD** : Navi 48 `1002:7551` (Radeon AI PRO R9700, 31,9 Gio VRAM sysfs), Navi 48
  `1002:7550` (RX 9070 XT, 15,9 Gio), iGPU Granite Ridge `1002:13c0` (0,5 Gio). `amdgpu`
  chargé, `/dev/kfd` + 3 `renderD*` présents, label `forge.gpu=amd`. Autorisation : carte
  blanche Nathan 2026-07-30 (machines de laboratoire).

## Contexte
La ligne AMD de `Docs/reference/gpu-drivers-support.md` cite HW-037 comme preuve « matériel
réel », mais HW-037 déclare lui-même ne couvrir que **la recommandation de driver et son
affichage, pas l'exécution**. Le chemin de **déploiement** AMD n'a jamais été mesuré.

Le chemin AMD est structurellement **différent de NVIDIA** (LAB-033N) : `renderers/k3s.py`
n'émet **aucune** ressource `amd.com/gpu` — il monte `/dev/kfd` et `/dev/dri` en
**passthrough `hostPath`**, ce qui force le Namespace en `enforce: privileged`. Trois
conséquences à mesurer, non à supposer : (a) le scheduler n'a aucune connaissance du GPU
(placement par `nodeSelector` seul, pas de comptabilité de ressource) ; (b) l'accès aux
devices dépend des permissions hôte (`/dev/kfd` en groupe `render` gid **991** sur pc4,
`/dev/dri/card*` en `video`) ; (c) rien ne garantit que le moteur du plan sache exploiter
ces devices.

## Décision
Qualifier le chemin AMD par le **flux produit**, sans étape posée à la main, avec la preuve
d'usage GPU adaptée au vendor :

```
sonde matérielle RÉELLE de pc4 (chemin produit, SSH)
→ derive_profile → minimal-gpu-rocm   (VÉRIFIÉ : 3 GPU amd, iGPU marqué [integrated])
→ assemble_plan(target=K3S) → render_k3s(node=pc4-grs-b, inventaire amd)
→ manifeste appliqué TEL QUEL → pod Running SUR pc4 avec /dev/kfd + /dev/dri montés
→ inference réelle servie PAR LE GPU, prouvée par le sysfs amdgpu de l'hôte
→ teardown propre
```

**Preuve d'usage GPU (spécifique AMD — il n'existe pas d'équivalent `nvidia-smi` ici)** :
échantillonner sur l'hôte pc4, pendant la génération,
`/sys/class/drm/card*/device/mem_info_vram_used` et `gpu_busy_percent` (valeurs de repos
mesurées : ~60/89/17 Mio utilisés, busy 0 %). Une occupation VRAM franche et/ou un
`gpu_busy_percent > 0` sur une carte **dGPU** pendant l'inference = preuve. Corroboration :
les logs du moteur nomment le device retenu.

**Fait de reconnaissance (mesuré 2026-07-30, pod jetable sur pc4)** : l'image `ollama` du
stack embarque le backend **Vulkan** et détecte les deux dGPU via RADV — `Vulkan0 = AMD
Radeon Graphics (RADV GFX1201) 0000:03:00.0 discrete 31.9 GiB` et `Vulkan1 = AMD Radeon
RX 9070 XT (RADV GFX1201) 0000:07:00.0 discrete 15.9 GiB` — et **écarte l'iGPU de
lui-même** (« dropping integrated GPU »). Le chemin AMD est donc servable par le stack
minimal ; la qualification doit le confirmer en inference réelle, pas s'en contenter.

Véhicule : `scripts/proof/prove_gpu_amd_e2e.py`, même patron que
`prove_gpu_nvidia_e2e.py` (rejouable, evidence verbatim, teardown en `finally`, mode
`--render-only` testable en CI sans cluster).

## Critères d'acceptation
- [ ] **T1-CI-1** : `--render-only` produit un manifeste où le service GPU monte
  `/dev/kfd` **et** `/dev/dri` en `hostPath`, **sans** aucune ressource `amd.com/gpu`, et où
  le Namespace porte `enforce: privileged` avec ses commentaires `# forgeai:` de dégradation
  — vérifié par pytest **sans cluster**.
- [ ] **T1-CI-2** : le profil dérivé du JSON de sonde AMD est `minimal-gpu-rocm` ; un JSON
  n'ayant qu'un iGPU AMD `[integrated]` est **refusé** (aucun manifeste produit).
- [ ] **T1-BANC-1** : sonde **réelle** de pc4 par le produit installé sur place ; profil
  `minimal-gpu-rocm` dérivé des mesures (aucune fixture).
- [ ] **T1-BANC-2** : manifeste appliqué **tel quel** ; pod GPU `1/1 Running` **sur
  `pc4-grs-b`** ; `/dev/kfd` et `/dev/dri` effectivement visibles **dans** le conteneur
  (vérifié depuis le pod, pas depuis l'hôte).
- [ ] **T1-BANC-3** : preuve d'usage GPU en trois volets : (a) le moteur nomme un device
  **dGPU** RADV dans ses logs et n'utilise pas l'iGPU ; (b) **inference réelle** servie
  (réponse non vide, tokens comptés) ; (c) `mem_info_vram_used` d'une carte dGPU **croît
  franchement** pendant la génération par rapport au repos, et/ou `gpu_busy_percent > 0`
  (échantillons verbatim, avant/pendant/après).
- [ ] **T1-BANC-4** : teardown : namespace supprimé, VRAM des cartes revenue au niveau de
  repos (vérification programmatique), aucun état résiduel.
- [ ] **T1-DOC** : la ligne AMD de `gpu-drivers-support.md` distingue explicitement
  « recommandation de driver (HW-037) » et « déploiement e2e en laboratoire (LAB-033A,
  evidence `reviews/LAB-033A/evidence/`) » — **sans toucher** aux lignes NVIDIA/Intel.
  ROUGE d'abord (test docs), VERT après.
- [ ] **Gates** : `pytest` vert, `no_stub_scan.py --all` vert, revue scellée 3/3
  (3 vendors distincts ≠ vendor du codeur), registre à jour.

## Preuves (chemins attendus)
- `reviews/LAB-033A/evidence/RED.txt` / `GREEN-docs.txt` — cycle TDD du claim docs.
- `reviews/LAB-033A/evidence/hardware-pc4.json` — sonde réelle.
- `reviews/LAB-033A/evidence/manifeste-rendu.yaml` — manifeste exact appliqué.
- `reviews/LAB-033A/evidence/DEPLOIEMENT-REEL.txt` — kubectl verbatim (pod sur pc4,
  devices dans le conteneur, namespace PSS, teardown).
- `reviews/LAB-033A/evidence/mesure-gpu-inference.txt` — logs device du moteur, réponse
  d'inference, échantillons sysfs VRAM/busy repos → génération → retour au repos.
- `Registres/mission.jsonl` (`tdad_red`/`tdad_green`, `story_impl`, `revue_scellee`).

## Rollback
Teardown en `finally` ; en cas d'échec mi-course `kubectl delete namespace <ns du plan>`.
`git revert` de la PR → ligne docs revenue au claim HW-037 seul ; aucun état résiduel cluster.

## Écart résiduel (à ne pas masquer)
- Qualification valable pour **ce banc** (k3s v1.35.5, `amdgpu` noyau 7.0, Navi 48 RDNA4,
  backend Vulkan/RADV) — pas une matrice multi-versions ni une preuve du chemin **ROCm/HIP**
  (`rocminfo` n'est pas installé sur pc4 ; le stack sert via Vulkan). Le nom du profil
  (`minimal-gpu-rocm`) est donc plus large que ce qui est prouvé : à consigner.
- Absence de `amd.com/gpu` : le scheduler ne compte pas les GPU AMD ; deux pods GPU AMD
  peuvent être placés sur le même nœud sans arbitrage. Constat de conception, pas corrigé ici.
- Les findings F2/F3 de LAB-033N (egress d'amorçage du modèle, NodePort sous policies)
  s'appliquent aussi ici : mêmes NetworkPolicies rendues, même contingence de banc étiquetée.
