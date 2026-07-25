# COMPOSE-025 — Durcir les services Compose par défaut (FAI-U-025)

## Cause racine
`src/forgeai/renderers/compose.py` (`render_compose` + `_openbao_unsealer_block`) n'émettait AUCUNE
option de durcissement conteneur : ni `security_opt`, ni `cap_drop`, ni `read_only`, ni `user`. Le
renderer k3s frère émettait déjà un `_security_block` (allowPrivilegeEscalation:false + seccomp),
créant une asymétrie de posture entre les deux backends (audit FAI-U-025 / Docker Bench 5.25).

## Changement (minimal, cause racine)
Émettre pour CHAQUE service rendu (services du plan + service `openbao-unsealer`) :
```
    security_opt:
      - no-new-privileges:true
```
inséré juste après `restart: unless-stopped`.

## Décision de conception (pourquoi ce sous-ensemble)
`no-new-privileges` est l'analogue Compose de `allowPrivilegeEscalation:false` du renderer k3s : il
est **universellement sûr** (n'exige ni utilisateur non-root, ni drop de capabilities) donc appliqué
par défaut. `cap_drop:[ALL]`, `read_only` et `user:` NE sont PAS appliqués en bloc : preuve runtime
existante (renderers/k3s.py::_security_block, prouvée sur cluster réel) — `drop:[ALL]` casse les
images à état (redis `chown /data` → CrashLoopBackOff). Ces options exigent une preuve de
compatibilité PAR SERVICE (`docker compose up` + healthcheck) non disponible hors-ligne dans cet
environnement (pull d'images bloqué). Elles sont donc laissées à un durcissement par-service prouvé
ultérieur, exactement comme k3s a borné son `_security_block`. Ce choix est documenté en commentaire
dans le code, au point d'émission.

## Preuves
- ROUGE : `reviews/COMPOSE-025/RED-reproduction.txt` (2 tests échouent : « ollama sans no-new-privileges »).
- VERTE : `reviews/COMPOSE-025/GREEN-focused.txt` (18/18 tests ciblés).
- `docker compose config` exit 0 : `reviews/COMPOSE-025/docker-compose-config.out` (+ manifeste rendu `rendered-sample.yaml`).
- Suite complète : verte (0 régression ; skips pré-existants docker-absent).
- gitleaks : 0 fuite.

## Périmètre
Modifié : `src/forgeai/renderers/compose.py`, `tests/test_renderers.py`. Aucun fichier hors `allowed_paths`.

## Rollback
`git revert` du commit → retrait des 4 lignes émises + des 2 tests ; la baseline `origin/main` reste
verte (prouvé : `reviews/COMPOSE-025/ROLLBACK.txt`).
