# Story SEC-YAML-INJECT — durcissement anti-injection YAML/Compose au niveau du plan

## Origine
Finding Sentinelle (Qwen3.7-Max, 2026-07-24T02:21:35Z) sur `src/forgeai/renderers/k3s.py:87` :
interpolation non sanitisée de `plan.plan_id` / `plan.profile` dans un commentaire `#`. Un `\n`
dans l'un de ces champs brise le commentaire et injecte des documents YAML arbitraires dans le flux
multi-documents k3s (idem `compose.py:15`).

## Analyse (preuve déterministe + CIV 3/3)
- **Mécaniquement CONFIRMÉ** : repro exécutée — un `plan_id` porteur de
  `\n---\n…ClusterRoleBinding…cluster-admin…\n---\n# ` produit, après `yaml.safe_load_all`, un
  `ClusterRoleBinding` supplémentaire liant `forgeai-sa` à `cluster-admin`.
- **NON atteignable dans le flux actuel** : `plan_id` = `p1-<hex8>` (`assemble.py:147`),
  `profile` ∈ littéraux fixes (`profile.py`) ; aucun `--profile` CLI ; aucune reconstruction de
  `DeploymentPlan` depuis un JSON externe.
- **Atteignabilité résiduelle réelle** (Gemini) : le toolkit est `pip install`-able — un tiers
  instanciant `DeploymentPlan(...)` directement contourne le flux interne. Le constructeur est une
  surface publique de la lib. Un futur `from_json` (LongCat) réintroduirait le risque.
- **CIV 3 vendors distincts** (DeepSeek-V4-Pro, Gemini-3.1-Pro, LongCat-2.0, tous ≠ Qwen auteur) :
  3/3 fix dans `DeploymentPlan.__post_init__`, 3/3 stratégie = **rejeter** (exception, pas strip).
- **Contrainte produit** : stdlib-pur (`dependencies=[]`) — pas de sérialiseur YAML tiers.

## Périmètre (proportionné)
Durcir les champs scalaires de `DeploymentPlan` qui atteignent en brut le YAML/Compose rendu :
`plan_id`, `profile`, `model`, `embed_model`. Rejet des caractères de contrôle (dont `\n`, `\r`,
`\t`, et tout `\x00`–`\x1f`/`\x7f`). Les champs de `ServiceSpec` (origine catalogue) sont un suivi
séparé (leur validation, notamment des valeurs `env` potentiellement multi-lignes, mérite sa propre
analyse pour éviter les faux rejets).

## Critères d'acceptation (testables)
1. `DeploymentPlan(plan_id="p1-x\n---\n…", …)` lève `ValueError` mentionnant le champ fautif —
   AVANT tout rendu. (RED sur l'ancien code : l'objet se construit sans erreur.)
2. Idem pour `profile`, `model`, `embed_model` porteurs d'un caractère de contrôle.
3. Un `DeploymentPlan` légitime (plan_id `p1-<hex8>`, profils réels) se construit sans erreur —
   aucune régression : `pytest` reste vert, `wizard --ci --dry-run` RC=0 sur les 4 backends.
4. Le message d'erreur nomme le champ et ne divulgue pas la valeur complète injectée (pas de fuite
   du payload dans les logs).
5. `no_stub_scan.py --all` vert ; revue scellée 3/3 APPROVE.

## Hors périmètre
- Champs `ServiceSpec` (suivi séparé).
- Migration vers un sérialiseur YAML (interdit : produit stdlib-pur).
