# LAB-033I — Qualifier le chemin Intel de bout en bout en laboratoire

## Identité
- Package : `LAB-033I` (`coordination/work-packages.json`, status EXTERNAL, ide CLAUDE_CODE)
- Issue : #284 · Dépendance : CAP-033A (**livrée** — registre seq 288, PR #294)
- Branche : `story/LAB-033I` · Tier : **T1**
- Prédécesseurs : LAB-033N (PR #301, mergée) et **LAB-033A** (qui livre le correctif de code
  partagé AMD+Intel : accès GPU par ressource de device plugin). Cette story **ne recorrige
  rien** : elle qualifie le chemin Intel sur le code déjà corrigé.
- Banc : **nœud `pc2-forge-b`** — laptop Lenovo 82Y3, i9-13900H, 30,6 Gio RAM,
  **Intel Iris Xe (Raptor Lake-P, `8086:a7a0`)** + RTX 4070 Laptop (`10de:2860`).
  `i915` et `xe` chargés, `/dev/dri` peuplé (card1, card2, renderD128, renderD129).
  Device plugin Intel installé sur le banc → `gpu.intel.com/i915: 1` exposé (mesuré).

## Contexte
CAP-033A a laissé la ligne Intel de `Docs/reference/gpu-drivers-support.md` explicitement
non qualifiée : « Implémenté — qualification laboratoire de bout en bout à réaliser.
Suivi : issue `LAB-033I` ». C'est le seul des trois vendors dont le claim n'a jamais
prétendu être prouvé — cette story lève cet écart.

Le chemin Intel partageait le défaut central corrigé par LAB-033A : le passthrough
`hostPath` de `/dev/dri` était **inopérant** (cgroup devices ⇒ repli CPU silencieux). Le
code corrigé demande désormais `gpu.intel.com/i915: "1"`.

## Décision
Qualifier le chemin Intel par le **flux produit**, sans étape posée à la main :

```
sonde matérielle RÉELLE de pc2 (chemin produit, SSH)
→ derive_profile → minimal-gpu-intel   (VÉRIFIÉ sur sonde réelle de pc2)
→ assemble_plan(target=K3S) → render_k3s(node=pc2-forge-b, inventaire intel)
→ manifeste appliqué TEL QUEL → pod Running SUR pc2 avec gpu.intel.com/i915 alloué
→ /dev/dri injecté par le plugin et OUVRABLE depuis le conteneur
→ teardown propre (ressource i915 libérée)
```

**Preuve d'usage GPU (spécifique Intel)** : il n'existe ni `nvidia-smi` ni `mem_info_vram_*`
exploitable pour un iGPU Intel (mémoire partagée avec la RAM système). La preuve retenue,
par ordre de force :
1. la ressource `gpu.intel.com/i915` est **allouée** sur le nœud pendant le run (0 → 1 → 0) ;
2. `/dev/dri/renderD*` est **ouvrable en lecture-écriture depuis le conteneur** (le test
   discriminant de LAB-033A : sans la ressource du plugin, c'est EPERM) ;
3. la charge GPU est observée via `/sys/class/drm/card*/gt_act_freq_mhz` (fréquence GT
   effective, propre à `i915`) et/ou les compteurs `i915` d'`intel_gpu_top` si présent ;
4. un moteur qui **choisit** le device Intel le nomme dans ses logs.

⚠ **Écart à mesurer, non à supposer** : le moteur du stack minimal (`ollama`) écarte les GPU
intégrés (« dropping integrated GPU », mesuré sur pc4). L'Iris Xe étant un **iGPU**, il est
probable que le moteur par défaut refuse de l'utiliser. La story doit MESURER ce
comportement et le consigner comme finding, sans le maquiller : le chemin *Kubernetes* Intel
(ressource, injection, ouverture du device) peut être prouvé même si le moteur *par défaut*
choisit le CPU. Le cas échéant, la preuve d'usage GPU réel sera faite avec le runtime Intel
du catalogue (`OpenVINO`, cf. `tests/test_intel_openvino_runtime.py`) ou
`OLLAMA_IGPU_ENABLE=1`, en le déclarant explicitement dans l'evidence.

Véhicule : `scripts/proof/prove_gpu_intel_e2e.py`, même patron que les deux précédents.

## Critères d'acceptation
- [ ] **T1-CI-1** : `--render-only` produit un manifeste où le service GPU porte
  `gpu.intel.com/i915: "1"` en `limits`, **aucun** volume `hostPath`, **aucune** ressource
  `nvidia.com/gpu` ni `amd.com/gpu`, et `enforce: baseline` — vérifié par pytest sans cluster.
- [ ] **T1-CI-2** : le profil dérivé du JSON de sonde de pc2 est `minimal-gpu-intel`.
- [ ] **T1-BANC-1** : sonde **réelle** de pc2 par le produit installé sur place ; profil
  `minimal-gpu-intel` dérivé des mesures.
- [ ] **T1-BANC-2** : manifeste appliqué **tel quel** ; pod `1/1 Running` **sur
  `pc2-forge-b`** ; ressource `gpu.intel.com/i915` allouée = 1 pendant le run.
- [ ] **T1-BANC-3** : `/dev/dri/renderD*` **ouvrable en lecture-écriture depuis le
  conteneur** (preuve que l'injection par le device plugin fonctionne là où le hostPath
  échouait) ; comportement du moteur vis-à-vis de l'iGPU **mesuré et consigné**, quel qu'il
  soit.
- [ ] **T1-BANC-4** : teardown : namespace supprimé, ressource `gpu.intel.com/i915`
  revenue à 0, aucun état résiduel.
- [ ] **T1-DOC** : la ligne Intel de `gpu-drivers-support.md` passe de « à réaliser » à
  qualifiée, avec la divulgation exacte de CE QUI est prouvé (chemin Kubernetes + ouverture
  du device) et de ce qui ne l'est pas (choix du device par le moteur par défaut).
  **Sans toucher** aux lignes NVIDIA/AMD. ROUGE d'abord, VERT après.
- [ ] **Findings pc2 consignés** (déjà collectés, `evidence/findings-pc2-preliminaires.txt`) :
  seuil VRAM 8192 (I1), garde HW-010 contournée (I2), CrashLoop du device plugin NVIDIA de
  pc2 (I3). Aucun n'est corrigé ici — chacun exige sa propre story.
- [ ] **Gates** : `pytest` vert, `no_stub_scan.py --all` vert, revue scellée 3/3, registre.

## Preuves (chemins attendus)
- `reviews/LAB-033I/evidence/findings-pc2-preliminaires.txt` — **déjà écrit** (I1/I2/I3).
- `reviews/LAB-033I/evidence/RED.txt` / `GREEN-docs.txt` — cycle TDD du claim docs.
- `reviews/LAB-033I/evidence/hardware-pc2.json` — sonde réelle.
- `reviews/LAB-033I/evidence/manifeste-rendu.yaml` — manifeste exact appliqué.
- `reviews/LAB-033I/evidence/DEPLOIEMENT-REEL.txt` — kubectl verbatim.
- `reviews/LAB-033I/evidence/mesure-gpu-intel.txt` — allocation i915, ouverture des devices,
  logs du moteur, fréquences GT.

## Rollback
Teardown en `finally` ; `kubectl delete namespace <ns>` en secours. `git revert` → la ligne
docs Intel revient à « qualification à réaliser » ; aucun état résiduel cluster.

## Écart résiduel (à ne pas masquer)
- Le GPU cible est un **iGPU** à mémoire partagée : la preuve d'usage est plus faible que
  pour une carte discrète (pas de VRAM dédiée à observer). Ce que la story prouve est le
  **chemin Kubernetes** (ressource, injection, ouverture du device) ; le choix du device par
  un moteur donné est un comportement du moteur, consigné mais hors contrôle du produit.
- Aucun GPU Intel **discret** (Arc) au banc : le chemin dGPU Intel reste non qualifié.
- Les findings I1/I2/I3 restent ouverts, chacun renvoyé à une story dédiée.
