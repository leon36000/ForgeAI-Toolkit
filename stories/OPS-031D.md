# OPS-031D — Introduire des correlation IDs de bout en bout

- **Issue** : #253 · **Tier** : T2 (exploitabilité + surface d'injection de logs)
- **Dépend de** : REL-038C — mergé.
- **Périmètre** : `src/forgeai/web/server.py`, `tests/test_ops031d_correlation.py` (nouveau),
  `stories/OPS-031D.md`.

## 1. Problème (mesuré)
Aucun identifiant de corrélation n'existe (`grep -rn "correlation|request_id|trace_id"` → néant), et
`log_message` est neutralisé (aucun journal d'accès). Le manque est devenu **concret depuis WEB-015** :
les erreurs renvoyées au client sont volontairement **génériques** (`{"error": "erreur interne"}`) et
la trace complète part sur `stderr`. C'était le bon arbitrage de sécurité, mais il laisse
l'**opérateur sans moyen de relier le signalement d'un utilisateur à la bonne trace** : « j'ai eu
"erreur interne" » ne désigne aucune des tracebacks du flux stderr. Même problème pour l'audit : les
entrées de registre écrites pendant une requête (`deploy_started`, `route_cloud_ajoutee`) ne portent
rien qui les rattache à l'appel HTTP qui les a provoquées.

## 2. Décision
Un **identifiant de corrélation par requête**, propagé sur les trois surfaces.

1. **Origine** : accepté depuis l'en-tête `X-Request-Id` **si et seulement s'il est valide**, sinon
   **généré** (`secrets.token_hex`). Un identifiant fourni par le client est une **entrée non fiable
   qui atterrit dans les journaux** : sans validation c'est une **injection de logs** (retours à la
   ligne pour forger de fausses entrées, longueur non bornée, caractères de contrôle). La validation
   est donc une **allowlist stricte** — `[A-Za-z0-9._-]{8,64}` — et tout ce qui n'y répond pas est
   **remplacé** (jamais tronqué ni « nettoyé » : on ne rafistole pas une entrée hostile).
   Accepter un ID *validé* venu d'un proxy est ce qui rend la corrélation réellement **de bout en
   bout** dans un déploiement en amont.
2. **Vers le client** : en-tête de réponse `X-Request-Id` sur **toutes** les réponses, et champ
   `request_id` **ajouté au corps d'erreur générique**. L'utilisateur dispose ainsi d'une référence
   **opaque** à citer, **sans qu'aucun détail interne ne fuie** — la garantie de WEB-015 est intacte.
3. **Vers l'opérateur** : l'identifiant précède la traceback sur `stderr` dans `_send_internal_error`
   → l'appariement signalement ↔ trace devient immédiat.
4. **Vers l'audit** : les entrées de registre écrites pendant la requête portent `request_id`.

### 2b. Conséquence sur WEB-015 (test hérité réconcilié)
WEB-015 assertait que le corps d'erreur vaut **exactement** `{"error": "erreur interne"}` — « aucune
clé en plus » y était le moyen de garantir l'absence de fuite. L'ajout de `request_id` respecte
l'**intention** (le jeton est opaque, généré par le serveur, et ne dit rien de l'exception) mais viole
la **lettre**. Les assertions sont donc reformulées en **invariant de clés** — `set(corps) ⊆ {error,
request_id}` — ce qui exprime la garantie plus précisément qu'une égalité stricte, et le test vérifie
en plus que `request_id` est bien **conforme à l'allowlist** (donc opaque) plutôt que de le supposer.

### 2c. Remise à zéro par requête (objection CRITIQUE de revue, mesurée)
Une revue a signalé que mémoïser l'identifiant sur `self` le ferait **fuir d'une requête à l'autre** :
`BaseHTTPRequestHandler.handle()` boucle sur `handle_one_request()` en **réutilisant l'instance** tant
que la connexion reste ouverte. **Mécanisme exact — mais mesure faite, la précondition est absente
aujourd'hui** : CPython n'honore `Connection: keep-alive` que si `protocol_version >= HTTP/1.1`, or le
serveur reste en **HTTP/1.0** ; la connexion se ferme donc après chaque requête et l'instance n'est
jamais réutilisée (vérifié : une tentative de connexion persistante par socket brut est fermée par le
serveur). Le défaut était donc **latent, non actif**.

Il est corrigé quand même : un futur passage en HTTP/1.1 le rendrait actif **silencieusement**, et la
garde coûte trois lignes au seul endroit qui délimite exactement une requête (`handle_one_request`).
Le test porte sur le **mécanisme de remise à zéro** plutôt que sur un keep-alive que la configuration
actuelle interdit — un test qui ne peut pas s'exécuter ne protège rien.

## 3. TDAD (RED d'abord) — `tests/test_ops031d_correlation.py`
- **G1** toute réponse porte un en-tête `X-Request-Id` non vide (y compris une réponse d'erreur).
- **G2** un `X-Request-Id` **valide** fourni par le client est **repris tel quel** (corrélation amont).
- **G3** un `X-Request-Id` **hostile** (retour à la ligne, > 64 car., caractères de contrôle, vide) est
  **remplacé** par un identifiant généré conforme — le contenu hostile n'apparaît **nulle part** dans
  la réponse ni sur stderr (anti-injection de logs).
- **G4** le corps d'erreur générique contient `request_id` **et rien d'autre d'interne** (WEB-015
  préservé : ni type d'exception, ni chemin).
- **G5** l'identifiant du corps est **le même** que celui de l'en-tête, et **le même** que celui
  imprimé sur stderr avec la traceback (corrélation vérifiable de bout en bout).
- **G6** deux requêtes successives obtiennent des identifiants **distincts**.
- **Mutation** : retirer la validation → G3 tombe ; ne pas propager l'ID au corps d'erreur → G4/G5
  tombent.

## 4. Critères d'acceptation
- **CA1** identifiant par requête, exposé en en-tête sur toutes les réponses.
- **CA2** entrée client acceptée **seulement si valide** (allowlist), sinon remplacée — aucune
  injection de journal possible.
- **CA3** corrélation vérifiable : même identifiant en en-tête, dans le corps d'erreur générique et
  devant la traceback stderr ; garantie de non-fuite de WEB-015 préservée.
- **CA4** non-régression : suite complète verte, couverture ≥ 85 %.
