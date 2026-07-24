# Story SEC-SVCSPEC-INJECT — durcissement anti-injection YAML/Compose des champs de `ServiceSpec`

Tier: T2

<!-- Sécurité (injection de manifeste), critique mais NON irréversible : pas de paiement/secret
prod/suppression/publication/engagement externe. Défense en profondeur d'input-validation.
⇒ T2 (3 vendors distincts + Sentinelle + TDAD obligatoire, human_required=False). -->

## Origine
Suivi explicite de **SEC-YAML-INJECT (#151)**, qui a durci `DeploymentPlan.__post_init__`
(`plan_id`, `profile`, `model`, `embed_model`) mais a laissé « en suivi séparé » les champs de
`ServiceSpec`. Lot Sentinelle 2026-07-24 : finding majeure « injection YAML par nom de service ».
Le vecteur critique (`name` porteur de `\n` → injection de documents YAML dans le flux
multi-documents k3s / le stream compose) est aujourd'hui mitigé **au rendu** par `_safe()` dans
`renderers/k3s.py`, mais **il n'existe aucune défense à la source**, et le **renderer compose
(`renderers/compose.py`) n'a AUCUN équivalent de `_safe`** — il interpole `svc.name`, `svc.image`,
les clés `env`, `depends`, `command` et `volumes` en brut ou sous-échappés.

## Analyse (preuve déterministe + atteignabilité)
- **Mécaniquement CONFIRMÉ** : `ServiceSpec` étant une dataclass frozen publique de la lib
  (`pip install`-able), un tiers — ou un futur `from_json` chargeant une brique externe — peut
  construire `ServiceSpec(name="redis\n---\n<doc arbitraire>\n---\n#", …)`. Rendu k3s : le `_safe`
  actuel LÈVE (mitigation au rendu) ; rendu compose : **aucune garde** → le document injecté passe.
- **Défense au rendu ≠ défense à la source** : `_safe` protège k3s si (et seulement si) tout champ
  interpolé y passe ; le compose ne le fait pas. La seule défense qui couvre **tous les renderers
  présents et futurs** est le rejet **à la construction** de `ServiceSpec`.
- **Champs concernés** = tout scalaire `str` de `ServiceSpec` atteignant en brut un renderer :
  `name`, `image`, `healthcheck_url`, `node`, et chaque élément de `volumes`, `command`, `depends`,
  ainsi que chaque **clé ET valeur** de `env`. (`host_port`/`container_port` = `int` ; `gpu` =
  `bool` ; `gpu_vendor` = jamais interpolé brut, seulement comparé à un jeu fixe → hors vecteur.)
- **Pas de faux rejet** : les valeurs légitimes proviennent de `data/deploy-*.json` (statique,
  vérifié sans caractère de contrôle) et de chemins/URLs construits (`http://…{path}`) — jamais
  de `\n`/`\t`/`\x00`. Scan déterministe des 3 specs de déploiement = 0 caractère Cc.

## Périmètre (proportionné)
`ServiceSpec.__post_init__` **rejette** (exception, pas nettoyage) tout caractère de contrôle
Unicode (catégorie **Cc** : `\x00`–`\x1f` + `\x7f`, couvre `\n`, `\r`, `\t`) dans les champs
ci-dessus, dès la construction, en **réutilisant** le helper `_rejeter_caracteres_de_controle`
introduit par #151 (source unique de vérité, message anti-fuite). `depends` et `node` sont inclus
(vecteurs réels : `depends` interpolé brut en compose ; `node` en k3s) pour fermer la **classe**
de vulnérabilité, pas seulement les instances énumérées par la finding.

## Critères d'acceptation (testables)
1. `ServiceSpec(name="redis\n---\n…", …)` lève `ValueError` mentionnant `name` — **AVANT** tout
   rendu. (RED sur l'ancien code : l'objet se construit sans erreur.)
2. Idem pour `image`, `healthcheck_url`, `node`, et pour un élément porteur de contrôle dans
   `volumes`, `command`, `depends`, ainsi que pour une **clé** et une **valeur** de `env`.
3. Le vecteur critique est neutralisé pour **les DEUX renderers** : ni `render_k3s` ni
   `render_compose` ne peuvent recevoir un `ServiceSpec` malveillant (la `ValueError` tombe à la
   construction, en amont du rendu). Prouvé pour compose (qui n'a pas de `_safe`).
4. Le message d'erreur nomme le champ et **ne divulgue pas** la valeur/le payload complet
   (anti-fuite des logs) — hérité du helper #151.
5. Aucune régression : `pytest` complet vert (le catalogue/les specs réels sont RFC 1123, sans
   contrôle) ; `no_stub_scan.py --all` vert ; revue scellée **3/3 APPROVE** (3 vendors distincts
   ≠ vendor du codeur).

## Hors périmètre
- `gpu_vendor` (jamais interpolé brut — seulement comparé à `{"nvidia","amd","intel"}`).
- Migration vers un sérialiseur YAML tiers (interdit : produit stdlib-pur, `dependencies=[]`).
- Le paramètre `project` de `render_compose` (argument d'appel, pas un champ de `ServiceSpec`).
