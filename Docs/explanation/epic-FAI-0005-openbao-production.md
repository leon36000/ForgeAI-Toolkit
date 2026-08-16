<!-- Design d'epic — VALIDÉ par revue scellée 3 vendors APPROVE 3/3 (Gemini-3.1-Pro/google, Grok-4.5/xai,
Qwen3.7-Max/alibaba), sceau prompt_sha256=1aa94be0a15af13c1a59e5e02b86f7126e3f03e10d2689471c02e67ef08c3e14,
6 rondes adversariales. STATUT : design figé ; BUILD EN PAUSE (cycle dédié). Epic de coordination = issue #108 ;
sous-stories #142(S1) #143(S2) #144(S3) #145(S4) #146(S5) #147(S6). -->

# Epic FAI-0005 (#108) — OpenBao PRODUCTION : design d'architecture validé

> **Statut** : design accepté (revue scellée 3/3, 2026-07-23) — **implémentation en pause** (cycle dédié).
> **Contexte** : le vecteur réseau est déjà fermé (openbao ClusterIP interne, #113) ; risque résiduel borné.


## Principe : INIT privilégié (flux de déploiement Python) + RE-UNSEAL bête (sidecar shell). Secrets PRÉ-CRÉÉS pour briser le chicken-and-egg.

## A. Cœur Python `src/forgeai/secrets/openbao_init.py` (exécuté par le flux de déploiement ; transports injectés ; testable)
`ensure_openbao_ready(bao_http, key_store, secret_store, addr) -> app_token` — **réconciliation par état
désiré, idempotente, transactionnelle** (pas de branche monolithique) :
1. `GET /v1/sys/health` ; si **non-initialisé** (501) → `POST /v1/sys/init {secret_shares:1, secret_threshold:1}`
   → parse JSON (Python) → **écrit unseal_key + root_token dans UN SEUL Secret/fichier `forgeai-openbao-keys`
   en UNE écriture (atomique)** AVANT toute autre étape, PUIS **read-back de vérification des DEUX valeurs**
   avant de poursuivre (openbao ne re-renvoie JAMAIS le root après init : une écriture partielle = coffre
   irrécupérable → l'écriture unique + read-back garantit qu'on ne dépasse l'init que si les 2 clés sont durables).
   Le sidecar (§B) ne montera QUE l'item `unseal_key` de ce Secret (mount sélectif d'item) → il ne voit jamais le root.
2. si **scellé** (503) → si key_store VIDE → **`OpenBaoError` fail-fast** (état cassé, jamais boucle brique) ;
   sinon `unseal`.
3. **KV** : LIST `/v1/sys/mounts` ; si `secret/` absent → enable kv-v2.
4. **policy** : **PUT** (overwrite idempotent, pas de test-présence) `forgeai-app` =
   `path "secret/data/forgeai/*" {capabilities=["create","read","update","delete"]}` +
   `path "secret/metadata/forgeai/*" {capabilities=["read","list","delete"]}`.
5. **token** : lire le token courant de secret_store ; si présent → `lookup-self` (200 + policy correcte) →
   **réutiliser** (pas de ré-émission) ; sinon émettre un token **PÉRIODIQUE** (`period=720h`, orphan,
   no_default_policy, policies=[forgeai-app]) — un token NON-root a TOUJOURS un TTL (seul le root n'expire
   pas) ; un token périodique reste valide indéfiniment TANT QU'il est renouvelé dans sa période. L'écrire
   dans secret_store et **révoquer** l'ancien s'il existait (pas d'accumulation). Root token ne quitte JAMAIS
   key_store. Renouvellement : `src/forgeai/secrets/vault.py` fait **renew-self** proactif (quand TTL restant < période/2,
   et sur 403 il relit le token du secret_store) — le token reste donc perpétuellement valide sans root.
Le flux de déploiement l'appelle APRÈS que openbao tourne (voir C) et AVANT de valider le socle prêt.

## B. Sidecar re-unseal (image openbao, shell — sans jq, sans curl, sans écriture, sans RBAC)
Conteneur additionnel du POD openbao (k3s) / service `openbao-unsealer` (compose). Utilise le **binaire `bao`
DÉJÀ présent dans l'image** (pas de curl — souvent absent des images minimales openbao). Constantes nommées :
`INIT_DEADLINE=600` (attente init), `KEY_GRACE=300` (propagation kubelet), les deux **absolues depuis le
premier échantillon** de l'état concerné (pas glissantes). Boucle (sleep 5), `bao status` (code sortie :
0=unsealed, 2=sealed ; erreur/489 non-init) :
- **non-initialisé** → **attendre** (le flux de déploiement init) jusqu'à `INIT_DEADLINE` → sinon exit 1 ;
- **scellé** → si `/keys/unseal_key` **non vide** → `bao operator unseal "$(cat /keys/unseal_key)"` ;
  si **VIDE** → fenêtre de grâce `KEY_GRACE` (le kubelet met des dizaines de s à propager le PATCH ; vide
  transitoire ≠ cassé) → exit 1 **seulement après** `KEY_GRACE` (réellement cassé) ;
- **unsealed** → no-op ; réinitialise les compteurs de deadline.
- Le sidecar ne monte QUE l'**item `unseal_key`** du Secret `forgeai-openbao-keys` (mount sélectif d'item →
  le root n'est JAMAIS dans le volume du sidecar), RAW, RO, montage par RÉPERTOIRE (pas `subPath` — subPath
  ne se rafraîchit pas après PATCH).
Le sidecar N'INIT JAMAIS (séparation).

## C. Chicken-and-egg k8s → **Secrets PRÉ-CRÉÉS** + ordre + connectivité (résout tour-3 critique)
1. Le flux de déploiement (Python, machine opérateur, a kubectl) **pré-crée des Secrets PLACEHOLDER vides**
   `forgeai-openbao-keys` (contiendra unseal_key + root) et `forgeai-secrets` (contiendra le token applicatif)
   AVANT `kubectl apply` d'openbao (+ montages `optional: true` en défense). → le POD openbao (avec sidecar
   montant SEULEMENT l'item `unseal_key` de `forgeai-openbao-keys`) **schedule et démarre** (Secret existe, vide).
   ⚠️ **Ces Secrets sont RUNTIME-MANAGED, PAS déclaratifs** : créés en `create-if-absent` (get→create, jamais
   `apply` d'une version vide) et **EXCLUS du jeu de manifests ré-appliqué** → un re-`apply`/GitOps ne les
   ÉCRASE JAMAIS (sinon retour au chicken-and-egg + perte des clés). Documenté comme état runtime, pas IaC.
2. `kubectl apply` openbao → attendre Pod **Running** (liveness tolérant scellé). Sidecar boucle en 501 (attend).
3. **Connectivité opérateur→openbao** : `kubectl port-forward svc/openbao 8200:8200` éphémère (wait-for-Ready +
   nettoyage garanti try/finally). compose : openbao publié sur `127.0.0.1:8200` le temps de l'init (ou `docker
   compose exec`), + wait/retry connectivité.
4. Flux de déploiement appelle `ensure_openbao_ready` → **PATCH** les Secrets placeholder (peuple clés + token).
   Le sidecar voit la clé apparaître (volume Secret rafraîchi) → unseal. openbao devient **Ready** (readiness).
5. **APRÈS** peuplement du token → `kubectl apply` des CONSOMMATEURS (litellm, etc.) → leur `secretKeyRef`
   lit un `forgeai-secrets` DÉJÀ peuplé (ordre ferme la course ; + retry vault.py en défense).

## D. compose — écriture depuis l'hôte + volume clés séparé
Le key_store compose = **répertoire bind-mount hôte** `${FORGEAI_HOME}/openbao-keys` (0700), écrit
DIRECTEMENT par le flux Python (hôte), monté **RO** dans `openbao-unsealer` (`:/keys:ro`) — PAS un volume
Docker nommé (qu'un process hôte ne peut écrire). Séparé du volume data `forgeai-openbao-data`. token → écrit
dans `.env`/secret consommateur après init. `openbao-unsealer` `depends_on: openbao {condition: service_started}`
+ `restart: unless-stopped` ; consommateurs `service_healthy` (= unsealed).

## E. Config HCL + manifests (S1)
`storage "file" {path="/openbao/file"}` (répertoire PRÉ-CRÉÉ inscriptible par l'UID openbao de l'image ;
`/openbao/data` serait possédé par root sur un volume neuf → non inscriptible, corrigé S6) ; `listener "tcp"
{address="0.0.0.0:8200", tls_disable=1}` ;
`api_addr="http://openbao:8200"` ; **disable_mlock** (posture conteneur standard — `bao` tourne en non-root sans file-cap, un IPC_LOCK resterait inopérant/CapEff=0 ; contrôle compensatoire = swap-off au nœud, prouvé e2e S6) ; openbao
**single-replica** ; volume persistant data ; liveness `?standbyok=true&sealedcode=200&uninitcode=200`,
readiness strict. Détails S1 : ENTRYPOINT image (valider `command:["server","-config=..."]`), UID + droits /openbao/data.

## Décomposition (DAG) — chacune PROOF + scellé 3/3, base main
- **S1** deploy-specs + renderers : HCL/volume(/openbao/file)/probes/single-replica ; disable_mlock (pas d'IPC_LOCK) ; retrait dev token. Rollback documenté.
- **S2** cœur Python `ensure_openbao_ready` (réconciliation état désiré, fail-fast, token reuse/revoke, policy PUT) — pur, injecté, tests exhaustifs. ∥ S1.
- **S3** sidecar re-unseal (asset shell + rendu) + câblage k3s (sidecar, Secrets placeholder pré-créés, port-forward init, probes). Dépend S1+S2.
- **S4** câblage compose (unsealer service, bind-mount clés hôte séparé, healthcheck unsealed, restart unless-stopped, depends_on). Dépend S1+S2.
- **S5** intégration flux de déploiement (pré-création Secrets → apply openbao → init → apply consommateurs) + `src/forgeai/bootstrap/secrets.py` sans dev-root + migration `Docs/how-to/openbao-migration.md` + `test_vault_e2e.py`→prod. Dépend S3+S4.
- **S6** preuve e2e réelle : init+unseal+KV+round-trip + **restart→re-unseal auto→KV OK** + **posture mlock : disable_mlock + non-root + swap-off** + token scopé (root≠app). Dépend S5.

## Frontières T3 (Nathan) + compromis DOCUMENTÉS (acceptés)
- etcd at-rest encryption (k3s) = prérequis opérateur documenté ; gestion clés d'un déploiement vivant.
- **Compromis acceptés & documentés** : (1) clé d'unseal 1-part persistée à côté (séparée des données) — vs KMS
  cloud impossible en souverain ; (2) **token applicatif PÉRIODIQUE (`period=720h`) renouvelé par renew-self**
  (§A) — un token non-root ne peut PAS être non-expirant ; réutilisé si valide (pas ré-émis) donc pas
  d'accumulation ; révoqué à la rotation ; (3) TLS interne = évolution (réseau ClusterIP/LAN aujourd'hui).
  ⚠️ COHÉRENCE : le token N'EST JAMAIS « non-expirant » — S2/S5 DOIVENT implémenter le renew-self (sinon
  impasse : expiration silencieuse). Seul le root (dans key_store, non distribué) n'expire pas.

## Vérification : chaque story gates+scellé 3/3+registre ; S6 = init+unseal+**survie restart**+**posture mlock (disable_mlock/non-root/swap-off)** prouvés. Rollback S1/S3/S4. Zéro secret réel committé (gitleaks EVIDENCE=0).
