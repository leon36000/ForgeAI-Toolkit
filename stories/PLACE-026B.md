# PLACE-026B — Diagnostic service → nœud → raison (FAI-U-026)

## Constat de reproduction — deux critères sur trois étaient déjà satisfaits
| critère | état sur `origin/main` |
|---|---|
| 1. sélecteur correct par service ciblé | **déjà satisfait** (héritage PLACE-026A) |
| 2. service `auto` jamais épinglé | **déjà satisfait** |
| 3. diagnostic service → nœud → raison | **manquant** |

Je le rapporte plutôt que de revendiquer une correction que je n'ai pas faite. Mais ces deux
comportements étaient **non protégés** : aucun test ne les verrouillait. Deux tests de
non-régression les couvrent désormais — leçon directe de la revue PLACE-011, où Grok avait relevé
qu'un comportement démontré dans les preuves n'était protégé par aucun test.

## Changement — `placement_diagnostic(plan, node_global, inventaire)`
Retourne une ligne par service : `service`, `node`, `raison`, `validation`.

| cas | node | raison |
|---|---|---|
| `svc.node == "auto"` | `None` | le scheduler choisit |
| `svc.node` = hostname | ce hostname | choix **explicite** du service |
| `svc.node is None` + nœud global | le nœud global | **héritage** du plan |
| `svc.node is None`, pas de global | `None` | auto |

La colonne `validation` confronte la décision à l'inventaire de PLACE-011 : `"OK"`, le message
d'erreur complet avec son code `ERR_PLACE_*`, ou `"non vérifié"` sans inventaire.

## La contrainte qui compte : cette fonction ne lève JAMAIS
Un diagnostic doit **diagnostiquer**, pas planter. Si elle s'interrompait au premier placement
invalide, l'utilisateur ne verrait qu'un problème sur cinq et corrigerait en aveugle, une erreur à
la fois. Preuve à l'exécution : le service `ollama` est refusé (`ERR_PLACE_CPU_ONLY`) **et les trois
autres lignes restent visibles** — l'état complet du plan est lisible d'un seul coup.

## Rollback
`git revert` → retour sans diagnostic (défaut FAI-U-026 connu) ; baseline verte.
