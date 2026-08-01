# OPS-031B — `forgeai logs` avec limites, filtres et rédaction

- **Issue** : #258 · **Tier** : T2 (sécurité — fuite de secret dans le flux de logs)
- **Dépend de** : OPS-031A — mergé.
- **Périmètre** : `src/forgeai/web/server.py`, `src/forgeai/cli.py`,
  `tests/test_ops031b_logs.py` (nouveau), `stories/OPS-031B.md`.

## 1. Problème (mesuré) — une asymétrie que ERR-041B a laissée ouverte
ERR-041B rédige les lignes de déploiement **à l'écriture disque** (`_persist_deploy_state`, l.501 :
`[redact_text(line) for line in _DEPLOY_STATE["lines"]]`). Mais la **mémoire** conserve les lignes
**BRUTES** (l.1471 : `_DEPLOY_STATE["lines"].append(line.rstrip(...))`), et `GET /api/deploy/events`
les **diffuse telles quelles** au client HTTP (l.1021/1031). **La copie persistée était protégée, le
flux en direct ne l'était pas.** Une commande `docker`/`kubectl` qui échotype un jeton le renvoie donc
au navigateur — et à quiconque écoute ce flux.

Par ailleurs, aucune commande `forgeai logs` n'existe : pour relire un déploiement il faut le serveur
web, et rien ne borne la sortie.

## 2. Décision
1. **Rédiger à l'INGESTION, pas à chaque sortie.** La rédaction descend au point où la ligne **entre**
   dans `_DEPLOY_STATE["lines"]`. C'est le seul choix qui tienne : ERR-041B a rédigé *une* sortie (le
   disque) et en a **manqué une autre** (le flux) — exactement le mode d'échec qu'un point d'entrée
   unique élimine. La mémoire ne détient alors plus jamais le secret, et **tout** consommateur —
   présent ou futur — est couvert sans y penser. (`_persist_deploy_state` garde sa rédaction :
   `redact_text` est idempotent, et le fichier peut avoir été écrit par une version antérieure.)
2. **`forgeai logs [--tail N] [--grep MOTIF] [--json]`** lit l'état persisté (`deploy-state.json`) :
   relecture possible **sans serveur web**.
   - **Limites** : `--tail` borné, défaut raisonnable, **plafond dur** — une commande de diagnostic ne
     doit pas pouvoir déverser un fichier arbitrairement gros dans un terminal ni dans un tube.
   - **Filtres** : `--grep` en **sous-chaîne littérale**, pas en expression régulière — un motif
     fourni par l'utilisateur et compilé serait une porte ouverte au ReDoS pour un gain nul ici.
   - **Rédaction** : appliquée **aussi à la lecture**, car le fichier a pu être écrit par une version
     antérieure à ce correctif (défense en profondeur assumée, pas redondance décorative).

## 3. TDAD (RED d'abord) — `tests/test_ops031b_logs.py`
- **G1** (détecteur de la fuite) : une ligne de déploiement porteuse d'un faux-secret arrive en
  mémoire **déjà rédigée** ; `GET /api/deploy/events` ne la diffuse donc jamais en clair.
- **G2** `forgeai logs` borne sa sortie au défaut, et `--tail N` la borne à N ; au-delà du plafond dur,
  la valeur est ramenée au plafond (jamais de déversement illimité).
- **G3** `--grep` filtre en sous-chaîne et ne compile aucune expression régulière (un motif comme
  `a(((` ne fait pas planter la commande).
- **G4** la rédaction s'applique **à la lecture** : un fichier d'état contenant une ligne brute
  (écrite par une version antérieure) ressort rédigé.
- **G5** `--json` produit un JSON valide ; sans fichier d'état, la commande sort proprement (code 0,
  message explicite) plutôt que par une trace.
- **Mutation** : retirer la rédaction à l'ingestion → G1 tombe ; retirer le plafond → G2 tombe.

## 4. Critères d'acceptation
- **CA1** aucune ligne brute ne subsiste en mémoire ni dans le flux `/api/deploy/events`.
- **CA2** `forgeai logs` : sortie bornée (défaut + plafond dur), `--grep` littéral, `--json`.
- **CA3** rédaction également appliquée à la lecture (fichiers d'une version antérieure).
- **CA4** non-régression : `/api/deploy/events` et la persistance inchangés par ailleurs ; suite
  complète verte, couverture ≥ 85 %.
