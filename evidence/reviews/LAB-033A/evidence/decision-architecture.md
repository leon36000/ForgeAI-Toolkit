# Décision d'architecture LAB-033A — chemin GPU AMD/Intel

Date : 2026-07-30T08:40:19Z · Décideur : Orchestrateur · Avis : panel 3 vendors distincts

## Question
Le passthrough hostPath des devices GPU rendu pour AMD/Intel est INOPÉRANT sur Kubernetes
(cgroup devices ⇒ EPERM ; repli CPU silencieux). Trois options : (1) device plugin comme
NVIDIA ; (2) `privileged: true` sur le conteneur ; (3) statu quo documenté.
Question complète : voir la section « Options » ci-dessous.

## Avis reçus — UNANIMES sur l'option 1

### DeepSeek-V4-Pro
> **AVIS ARCHITECTURAL — LAB-033A (GPU AMD/Intel via device plugin)**
> 
> ---
> 
> ### 1. OPTION RETENUE
> 
> **Option 1 – Device plugin (alignement AMD/Intel sur NVIDIA).**
> 
> - **Justification de sécurité** : L’option 1 supprime tout `hostPath` de device, donc le Namespace n’a plus besoin de privilège PSS (`enforce: privileged`). Le conteneur conserve `drop: [ALL]`, `allowPrivilegeEscalation: false` et n’est jamais `privileged`. La surface d’attaque est réduite et le produit respecte la posture *restricted* du projet.  
> - **Exactitude fonctionnelle** : Les preuves mesurées montrent que seul le chemin avec `limits` (ex. `amd.com/gpu: "1"`) et *sans* hostPath permet au conteneur d’accéder au GPU via le device plugin et d’exécuter effectivement le moteur Vulkan. Sans cela, le retour silencieux sur CPU trahit l’intention de l’utilisateur.  
> - **Portabilité** : C’est le même contrat d’exploitation que pour NVIDIA. Le cluster doit installer le device plugin officiel du vendeur (`rocm/k8s-device-plugin` ou `intel-gpu-plugin`). L’hypothèse est déjà assumée et documentée pour NVIDIA ; l’étendre garantit une expérience homogène.  
> - **Isolation et scheduling** : Le scheduler Kubernetes comptabilise enfin les GPU, et le device plugin injecte uniquement le(s) GPU alloué(s) au pod (isolation réelle, mesurée en config D).
> 
> Les options 2 et 3 sont rejetées :  
> - #2 réintroduit `privileged: true`, en contradiction avec la politique de sécurité et sans i
_(avis complet conservé hors dépôt : sortie de modèle = CLAIM, la décision est celle de l'Orchestrateur)_

### Qwen3.7-Max
> # AVIS D'ARCHITECTURE — LAB-033A (GPU AMD/Intel)
> 
> ## 1. OPTION RETENUE
> **Option 1 : Device Plugin (Alignement strict sur le paradigme NVIDIA)**
> 
> *Justification :*
> - **Sécurité** : La suppression du `hostPath` élimine la nécessité de dégrader le Pod Security Standard (PSS) du Namespace. On évite la régression catastrophique de l'option 2 (`privileged: true`) qui ouvrirait le nœud aux conteneurs.
> - **Exactitude** : Corrige le repli CPU silencieux. Le device plugin est le seul mécanisme Kubernetes natif capable de configurer correctement le cgroup `devices` pour autoriser l'accès aux character devices.
> - **Isolation & Ordonnancement** : Le scheduler compte enfin les GPU (fin du surcommit aveugle) et le plugin n'injecte que le GPU alloué au pod (isolation matérielle stricte, contrairement au `hostPath` qui expose tout le bus).
> - **Cohérence** : Unifie le paradigme d'accélération matérielle dans le produit.
> 
> ## 2. RÉPONSES AUX QUESTIONS (a → e)
> 
> **a) Argumentation (Sécurité, Exactitude, Portabilité)**
> L'option 1 est la seule qui respecte le contrat de sécurité du produit (posture `restricted`/`baseline`) tout en garantissant le fonctionnement réel du matériel. L'option 2 est un anti-pattern Kubernetes absolu. L'option 3 est inacceptable (livrer un produit défectueux qui ment à l'utilisateur).
> 
> **b) Périmètre de la story (AMD et Intel ensemble ou scindés ?)**
> **Traiter les deux dans la même story (LAB-033A).**
> Le code actuel couple AMD et Intel da
_(avis complet conservé hors dépôt : sortie de modèle = CLAIM, la décision est celle de l'Orchestrateur)_

### MiMo-Pro-V2
> # AVIS D'ARCHITECTURE — LAB-033A
> 
> ## (1) OPTION RETENUE
> 
> **Option 1 : Device plugin, sans hésitation.**
> 
> | Critère | Option 1 (device plugin) | Option 2 (privileged) | Option 3 (statu quo) |
> |---|---|---|---|
> | **Exactitude fonctionnelle** | ✅ GPU réel, prouvé config D | ✅ GPU réel, prouvé config C | ❌ Silencieusement sur CPU |
> | **Sécurité** | ✅ Améliorée (plus de hostPath) | ❌ Régression franche (privileged) | — (non applicable) |
> | **Isolation GPU** | ✅ 1 pod = 1 GPU dédié | ❌ Tous les GPU pour tous les pods | — |
> | **Scheduler** | ✅ Compte les GPU, Pending si épuisés | ❌ Aveugle | — |
> | **Cohérence vendor** | ✅ Unifié avec NVIDIA | ❌ NVIDIA reste device plugin, AMD/Intel divergent | ❌ NVIDIA ok, autres cassés |
> | **Portabilité cluster** | ⚠️ Nécessite le plugin vendor | ⚠️ Nécessite privileged | ❌ Fonctionne nulle part |
> 
> **Justification triple :**
> 
> - **Sécurité** : Le projet a explicitement choisi `drop: [ALL]`, `allowPrivilegeEscalation: false`, et posture restricted. L'option 2 (`privileged: true`) dynamite cette posture pour deux vendors entiers. Inacceptable.
> - **Exactitude** : L'option 3 est la pire : le produit *ment* — il déploie un pod qui prétend être GPU mais tourne sur CPU. C'est un bug silencieux, le pire type de bug. La confiance utilisateur est en jeu.
> - **Portabilité** : L'hypothèse « le device plugin est installé » est **déjà le contrat implicite du chemin NVIDIA** (GPU Operator)
_(avis complet conservé hors dépôt : sortie de modèle = CLAIM, la décision est celle de l'Orchestrateur)_

## Décision retenue
**Option 1 — device plugin.** AMD → `amd.com/gpu`, Intel → `gpu.intel.com/i915`,
suppression du passthrough hostPath pour les deux vendors. Motifs :
1. **Exactitude** : c'est la seule option où le GPU est réellement utilisé (mesuré).
2. **Sécurité** : plus aucun hostPath ⇒ la dégradation PSS `enforce: privileged`
   (K8S-024) devient inutile, le namespace d'un plan GPU reste `restricted`. L'option 2
   aurait fait l'inverse : conteneur tout-puissant sur le nœud.
3. **Isolation** : le plugin n'injecte que le GPU alloué (mesuré : 1 carte sur 3),
   là où le passthrough exposait tous les devices à tout pod GPU.
4. **Ordonnancement** : le scheduler comptabilise enfin les GPU AMD/Intel.
5. **Cohérence** : hypothèse « device plugin du vendor installé par l'administrateur »
   déjà assumée pour NVIDIA (qualifiée par LAB-033N) et déjà recommandée par
   `hardware/drivers.py` (amd-gpu-operator, intel-device-plugins).

AMD et Intel sont corrigés ENSEMBLE (même bloc de code) : n'en corriger qu'un laisserait
l'autre en bug silencieux. LAB-033I qualifiera le chemin Intel e2e sur pc2 à partir de ce
code déjà corrigé — la correction est ici, la qualification Intel est là-bas.

## Hors périmètre, explicitement
Le durcissement des pods GPU (retour à `runAsNonRoot` et `readOnlyRootFilesystem: true`)
n'est PAS traité : il exige sa propre mesure par vendor. Seuls les commentaires de
justification devenus faux sont corrigés.

## Options soumises au panel (verbatim)
## Options
1. **Device plugin (aligner AMD/Intel sur NVIDIA)** : émettre `amd.com/gpu: "1"` /
   `gpu.intel.com/i915: "1"` en limits, SUPPRIMER le passthrough hostPath. Effets : le
   Namespace n'a plus besoin de `enforce: privileged` (plus aucun hostPath) ⇒ posture de
   sécurité AMÉLIORÉE ; le scheduler compte enfin les GPU ; isolation par GPU. Coût : le
   cluster doit avoir le device plugin du vendor installé — exactement l'hypothèse DÉJÀ
   assumée pour NVIDIA. Casse les tests existants qui figent le passthrough
   (tests/test_k3s_gpu_vendor.py parties AMD/Intel, tests/test_k3s_hardening_fai0004.py:145
   supersession privileged K8S-008, éventuellement les tests K8S-024 sur la dégradation PSS).
2. **`privileged: true` sur le conteneur GPU amd/intel** : garde le passthrough, fait
   fonctionner le GPU. Coût : régression de sécurité franche (conteneur tout-puissant sur le
   nœud), en contradiction avec la posture restricted du projet ; ne corrige pas la cécité du
   scheduler ni l'absence d'isolation (tous les GPU exposés à tous les pods GPU).
3. **Ne rien changer, documenter l'écart** : le produit continue de rendre un chemin AMD/Intel
   qui ne sert pas sur GPU sans le dire. (Option de statu quo, à évaluer honnêtement.)

## Questions précises
