# RC1-528 — `_extract_text()` lève AttributeError sur un JSON valide non-dict

## Contexte
Issue [#528](https://github.com/leon36000/ForgeAI-Toolkit/issues/528). Découvert pendant #456,
même famille de défaut que #482/#492/#527 : traitement d'une sortie externe (ici la réponse HTTP
d'une gateway/API cloud configurée par l'utilisateur) sans valider la structure JSON avant d'y
accéder.

## Problème
`src/forgeai/models/probe.py::_extract_text(payload)` catch `json.JSONDecodeError` (échec de
*parsing*) mais pas le cas où le JSON est **valide** tout en n'étant pas de la forme attendue :
top-level non-dict (`[1,2,3]`, `"texte"`, `42`, `null`), ou un élément de `choices` non-dict.
`data.get(...)`/`choice.get(...)` lèvent alors `AttributeError`, non rattrapée.

`probe_route()` (même fichier) appelle `_extract_text(payload)` SANS `try/except` autour — la
fonction teste une URL de gateway/modèle cloud configurée par l'utilisateur
(`forgeai model add-cloud` puis `forgeai model test`). Un serveur mal configuré peut répondre
HTTP 200 avec un corps JSON valide mais non conforme.

Appelant CLI vérifié (`cli.py:853`, commande `forgeai model test <name>`) : hors du
`try/except (RouteError, KeyError)` local, et le dispatcher final de `main()` ne catch que
`except DeployError` — pas de catch-all générique. `forgeai model test` planterait avec une
traceback Python brute au lieu du message `ECHEC: ...` attendu.

## Critères d'acceptation
1. `_extract_text()` retourne `""` (comportement "souple" déjà contractuel de la fonction, pas
   d'exception) pour un payload JSON valide dont le top-level n'est pas un dict (liste, chaîne,
   nombre, `null`).
2. `_extract_text()` retourne `""` (pas d'exception) si un élément de `choices` n'est pas un dict
   — le reste de la liste `choices` doit continuer d'être examiné normalement (ignorer l'élément
   malformé, pas abandonner toute l'extraction).
3. Le comportement EXISTANT pour un payload valide/bien formé (dict avec `choices` bien formé)
   reste STRICTEMENT inchangé — ne pas changer la valeur de retour pour les cas déjà couverts par
   les tests existants de `tests/test_models_probe.py` (si le fichier existe) ou tout autre test
   touchant `_extract_text`/`probe_route`.
4. Un test TDD reproduit exactement les 4 cas de l'issue (`[1,2,3]`, `"erreur texte brute"`,
   `"42"`, `"null"`) et vérifie `_extract_text(payload) == ""` (pas d'exception levée).
5. Un test TDD couvre le cas d'un élément non-dict au milieu d'une liste `choices` par ailleurs
   valide (ex. `choices: [{"message": {"content": "ok"}}]` mélangé à un élément `null`/liste/etc.)
   — le contenu valide doit toujours être trouvé si un élément malformé apparaît AVANT lui dans la
   liste.

## Hors scope
Les 3 autres sites cités dans l'issue (`gateway.py:106`, `local.py:125`, `routes.py:94`) ne sont
PAS vérifiés/couverts par cette story — l'issue les mentionne comme non-vérifiés individuellement
dans cette itération. Seul `_extract_text()` et son unique appelant direct `probe_route()` sont
dans le périmètre.
