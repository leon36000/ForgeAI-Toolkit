# Migrer openbao du mode DEV vers la PRODUCTION (FAI-0005)

> Public : opérateur d'un socle ForgeAI déjà déployé avec un openbao en **mode développement**
> (token root pré-partagé, coffre auto-descellé, stockage en mémoire). Objectif : passer à un openbao
> **production** (stockage fichier persistant, coffre scellé, init/unseal orchestrés, token applicatif
> scopé) sans perdre les secrets applicatifs.

## Ce qui change

| | mode DEV (avant) | PRODUCTION (FAI-0005) |
|---|---|---|
| Stockage | en mémoire (perdu au restart) | fichier `/openbao/data` (volume persistant) |
| Descellement | automatique | init/unseal orchestrés (clé d'unseal persistée à côté) |
| Token | `BAO_DEV_ROOT_TOKEN_ID` root, dans `.env` (`FORGEAI_BAO_TOKEN`) | token applicatif **scopé** (policy `forgeai-app`, périodique 720h), émis au déploiement, jamais le root |
| mlock | inactif | actif (capability `IPC_LOCK`) |
| Descellement au restart | sans objet | service/sidecar `openbao-unsealer` (re-descelle depuis l'unique item `unseal_key`) |

`FORGEAI_BAO_TOKEN` **n'est plus généré** par `bootstrap/secrets.py` : le token applicatif est créé au
déploiement par `ensure_openbao_ready` et persisté en **runtime** (fichier hôte / Secret k8s), jamais dans
`.env`. Le **root token ne quitte jamais** son store (isolé du volume monté à l'unsealer).

## Compose (clé en main) — `forge wizard --rag-durci`

Le wizard fait tout automatiquement (backend compose) :

1. Prépare le key-store hôte `${workdir}/openbao-keys` (0700) — la clé d'unseal y sera écrite ; le root
   token est écrit **séparément** dans `${workdir}/secrets/openbao_root` (hors du répertoire monté à
   l'unsealer → l'unsealer ne voit jamais le root).
2. Démarre **openbao + openbao-unsealer seuls** (les consommateurs attendent `service_healthy` = coffre
   descellé ; les démarrer d'abord provoquerait un interblocage).
3. Appelle `initialize_openbao` (cœur `ensure_openbao_ready`) : init (si vierge), unseal, KV v2, policy
   `forgeai-app`, émission d'un token applicatif périodique 720h. Écrit la clé d'unseal → l'`openbao-unsealer`
   la reprend et re-descellera à chaque restart.
4. Démarre les consommateurs (litellm, …) qui deviennent `service_healthy`.
5. Écrit puis relit la master key passerelle au coffre **avec le token applicatif** (le coffre est porteur).

Rien à faire côté opérateur au-delà de `forge wizard --rag-durci`.

### Migration d'un déploiement DEV existant vers compose PROD

1. Récupérer les secrets applicatifs actuels (master key passerelle, etc.) hors du coffre DEV.
2. `docker compose down` (le coffre DEV en mémoire est jetable) ; retirer `BAO_DEV_ROOT_TOKEN_ID` (déjà
   absent des specs). Supprimer `FORGEAI_BAO_TOKEN` de `.env` (ignoré désormais).
3. Redéployer via `forge wizard --rag-durci` : le coffre PROD s'initialise et re-reçoit la master key.
4. Conserver `${workdir}/openbao-keys/unseal_key` et `${workdir}/secrets/openbao_root` **hors du dépôt**,
   sauvegardés de façon sûre : ce sont les seules créances de récupération du coffre.

## Kubernetes (k3s) — flux OPÉRATEUR

openbao est exposé en **ClusterIP** (interne, durcissement #113) : aucune connectivité NodePort. L'amorçage
production sur k3s passe donc par un **port-forward opérateur** (le wizard k3s échoue explicitement en dirigeant
ici, plutôt que de bloquer sur un `wait deployments` d'un coffre jamais descellé). Étapes :

1. `kubectl apply` du manifeste rendu (openbao + son sidecar `openbao-unsealer` + consommateurs). Le pod
   openbao démarre **scellé** ; le Secret `forgeai-openbao-keys` est monté `optional: true` (le pod schedule
   même si le Secret n'existe pas encore) ; le sidecar attend la clé (fenêtre de grâce).
2. Ouvrir un accès éphémère : `kubectl port-forward svc/openbao 8200:8200 -n forgeai-minimal`.
3. Amorcer (Python, machine opérateur) via le VRAI code — le `KubectlKeyStore` écrit le Secret
   `forgeai-openbao-keys` (clé d'unseal + root, **valeurs par STDIN, jamais en argv**) ; le sidecar reprend
   l'item `unseal_key` et descelle ; openbao devient `Ready` :

   ```python
   from forgeai.deploy.openbao_flow import KubectlKeyStore, FileSecretStore, initialize_openbao
   key_store = KubectlKeyStore("forgeai-openbao-keys", "forgeai-minimal")
   secret_store = FileSecretStore("secrets/openbao_app_token.json")  # opérateur, hors du cluster
   app_token = initialize_openbao("http://127.0.0.1:8200", key_store, secret_store)
   ```
3. Écrire la master key passerelle au coffre avec `app_token` (`forgeai.secrets.vault.store` / `read`),
   fermer le port-forward.

Le sidecar re-descelle automatiquement à chaque restart du pod (le storage fichier repart scellé). Le
Secret `forgeai-openbao-keys` est **runtime-managed** : ne PAS le ré-appliquer via GitOps (sinon écrasement
des clés → coffre irrécupérable).

## Renouvellement du token (perpétuité sans root)

Le token applicatif est **périodique** (`period=720h`) : un token non-root a toujours un TTL (seul le root
n'expire pas). Il reste valide indéfiniment **tant qu'il est renouvelé dans sa période** — `forgeai.secrets.vault.renew_self(bao_url, app_token)` fait ce renouvellement proactif. `ensure_openbao_ready`
réutilise le token existant s'il est encore valide (pas de ré-émission ni d'accumulation) et révoque
l'ancien lors d'une rotation.

## Sauvegarde / récupération

- `openbao-keys/unseal_key` (+ `secrets/openbao_root` en compose, ou le Secret `forgeai-openbao-keys` en k8s)
  = **seules** créances de récupération. À sauvegarder de façon sûre, hors du dépôt (jamais committées).
- Perte de la clé d'unseal = coffre irrécupérable (compromis souverain accepté : pas de KMS cloud).
- Chiffrement at-rest du storage (etcd k3s / volume compose) = prérequis opérateur documenté (frontière T3).
