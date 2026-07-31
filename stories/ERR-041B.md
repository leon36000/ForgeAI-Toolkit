# ERR-041B — Rédiger stderr dans les déploiements Compose/K3s

- **Issue** : #267
- **Tier** : T2 (sécurité — surface de fuite de secret dans les messages d'erreur de déploiement)
- **Dépend de** : ERR-041A (`forgeai.core.redaction`, mergé) ; HEALTH-028B (mergé).
- **Reprise lane CODEX** (Codex retiré).
- **Périmètre fichiers** : `src/forgeai/deploy/compose.py`, `src/forgeai/deploy/k3s.py`,
  `tests/test_err041b_deploy_redaction.py` (nouveau), `stories/ERR-041B.md`.

## 1. Problème (code réel)

Les fonctions de déploiement interpolent le **`proc.stderr` brut** d'un sous-processus
(`docker compose` / `kubectl`) dans le message d'une `DeployError`. Ce stderr peut contenir un secret
(variable d'env, jeton, en-tête `Authorization` émis par l'outil sous-jacent). 5 sites :

- `compose.py:35` — `docker compose up a échoué :\n{proc.stderr[-2000:]}`
- `compose.py:44` — `docker compose down a échoué :\n{proc.stderr[-2000:]}`
- `k3s.py:22` — `kubectl apply a échoué :\n{proc.stderr[-2000:]}`
- `k3s.py:32` — `Déploiements non disponibles … :\n{state}\n{proc.stderr[-1000:]}`
- `k3s.py:39` — `kubectl delete namespace a échoué :\n{proc.stderr[-1000:]}`

Déjà sûrs (aucun changement) : `web/server.py` deploy-state (rédigé par ERR-041A) ;
`openbao_flow.py:234` (n'inclut PAS stderr — commentaire explicite, valeur passée en stdin) ;
`compose.py:130` (`r.stdout` parsé en interne pour `ps`, jamais mis dans un message).

## 2. Décision (adoption minimale, une justification)

À chacun des 5 sites, envelopper le `proc.stderr[…]` interpolé par `redact_text(...)` de
`forgeai.core.redaction`. *Justif :* source de vérité unique déjà éprouvée (ERR-041A) ; `redact_text`
ne lève jamais, ne tronque jamais la reconnaissance, rédige Bearer/clé=valeur/sk-/jeton long. On rédige
UNIQUEMENT le fragment issu du sous-processus (le texte fixe et le nombre de secondes restent lisibles).
Ajout d'un `from forgeai.core.redaction import redact_text` en tête de `compose.py` et `k3s.py`.
Le `{state}` de `k3s.py:32` (sortie `kubectl get pods -o wide` : noms/statuts, pas de secret) est aussi
passé par `redact_text` par défense en profondeur (coût nul, cohérence).

## 3. Stratégie de test TDAD (`tests/test_err041b_deploy_redaction.py` — RED d'abord)

Monkeypatch de `_compose` / `_kubectl` pour retourner un `subprocess.CompletedProcess` d'échec
(`returncode=1`, `stderr` porteur d'un faux-secret distinctif), puis capture de la `DeployError` :

- **G1** `compose_up` échec avec stderr = `"env FORGEAI_API_TOKEN=" + "h"*32` → `DeployError` levée,
  message contient « docker compose up a échoué », le secret ABSENT (fenêtres de 8 car.), `REDACTED` présent.
- **G2** `compose_down` échec avec `Bearer …` → secret absent, REDACTED présent.
- **G3** `k3s_apply` échec avec `sk-…` → secret absent.
- **G4** `k3s_wait_deployments` échec avec un mot de passe factice dans stderr → secret absent, message
  garde le texte fixe (« Déploiements non disponibles »). <!-- proof:allow : exemple prose -->
- **G5** `k3s_delete_namespace` échec avec une clé d'API factice → secret absent. <!-- proof:allow : exemple prose -->
- **G6** non-régression : le texte fixe et les infos non-secrètes (nom de service, timeout) restent
  présents ; un stderr sans secret passe inchangé (hors marqueur).
- **G7** chemin heureux : `returncode=0` → aucune `DeployError` levée (les fonctions retournent None).

## 4. Critères d'acceptation

- **CA1** les 5 sites : le `stderr` du sous-processus est rédigé dans le message d'erreur (secret + fenêtres absents).
- **CA2** `REDACTED` présent quand un secret était là ; message toujours diagnostique (texte fixe conservé).
- **CA3** non-régression : `returncode==0` ne lève pas ; stderr sans secret inchangé.
- **CA4** aucune signature publique changée (`compose_up/down`, `k3s_apply/wait/delete` inchangées).
- **CA5** suite complète verte, no-stub, couverture ≥ 85 %.

## 5. Risques

- Sur-rédaction d'un fragment de stderr légitime (hash, id) — assumé (ERR-041A §3d), coût = diagnostic.
- Un futur site de déploiement ré-introduisant `proc.stderr` non rédigé — atténué par le test qui
  couvre chaque fonction publique ; suivi : garde statique éventuelle (hors périmètre).
