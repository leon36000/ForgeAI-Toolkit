# REG-029A — Définir la complétude structurée des registres

- **Issue** : #278 · **Tier** : T2 (gouvernance — une attestation manquante ne se voit pas)
- **Dépend de** : ORCH-001 — complété.
- **Périmètre** : `src/forgeai/core/registre_completude.py` (nouveau), `scripts/registre.py`,
  `tests/test_reg029a_completude.py` (nouveau), `stories/REG-029A.md`.

## 1. État MESURÉ
`registre.verify()` valide la **chaîne** (hash/HMAC, chaînage `prev_hash`) — c'est-à-dire
l'**intégrité** : rien n'a été altéré. Il ne dit **rien de la COMPLÉTUDE** : une chaîne parfaitement
intègre peut être **muette** sur ce qu'elle devrait attester. Le gate CI `registres`
(`gates.yml:55`) ne lance que `registre.py verify` — donc aujourd'hui, **une story déclarée terminée
sans aucune trace de revue passe le gate sans bruit.**

Deux constats issus du registre réel (380+ entrées, 39 stories déclarées complètes) :
- **Deux conventions d'attestation coexistent.** Les stories anciennes portent la revue **en ligne**
  dans le payload de `story_complete` (champ `revue`) ; les récentes émettent une entrée
  **`revue_scellee` séparée**. Toute règle qui n'en accepterait qu'une déclarerait faussement
  incomplète la moitié de l'historique — et serait aussitôt affaiblie pour repasser au vert.
- **Les entrées `revue_scellee` récentes n'ont PAS de champ `story`** (15 entrées) : elles ne portent
  qu'un `dossier` (`reviews/WEB-017`). Elles ne sont donc rattachables à leur story qu'en **analysant
  un chemin** — une jointure fragile, introduite par mes propres chores de coordination.

Anomalie réelle restante après application de la règle complète : **1 sur 39** (`D4`), dont le
`story_complete` est une entrée narrative de capacité sans aucune attestation de revue. **Le registre
ne peut donc pas prouver que D4 a été revue** — ce qui est exactement le genre de trou que cette story
existe pour rendre visible.

## 2. Décision
1. **Définir la complétude comme un contrat explicite**, distinct de l'intégrité :
   - un **schéma par type d'entrée** (champs obligatoires) — notamment `revue_scellee` doit désormais
     porter `story`, `prompt_sha256` et `vendors` ;
   - une **règle de complétude** : toute `story_complete` doit être **attestée par une revue**, soit
     par une entrée `revue_scellee` de la même story, soit **en ligne** (champ `revue`/`preuve`).
2. **Rétro-compatibilité assumée et documentée, pas silencieuse** : la jointure accepte `story`,
   `package`, ou à défaut le **nom de base de `dossier`**. C'est une concession explicite à
   l'historique — pas un contournement : le schéma exige `story` pour les entrées **nouvelles**.
3. **Rapporter, ne pas réécrire.** Le registre est append-only et haché : corriger l'historique est
   impossible *et* interdit. L'outil **signale** les anomalies avec leur raison ; leur remédiation
   (entrée corrective d'attestation) relève d'une décision explicite, pas d'un effet de bord.
4. **Pas de gate CI dans cette story.** REG-029A *définit* et *outille* la complétude ; brancher le
   gate appartient à REG-029B — livrer un gate rouge dès le premier jour ne ferait qu'inviter à
   l'affaiblir.

## 3. TDAD (RED d'abord) — `tests/test_reg029a_completude.py`
- **G1 schéma** : une entrée `revue_scellee` sans `story`/`prompt_sha256`/`vendors` est signalée,
  avec le nom du champ manquant.
- **G2 complétude** : une `story_complete` sans aucune attestation est signalée.
- **G3 attestation séparée** : `story_complete` + `revue_scellee` de la même story → conforme.
- **G4 attestation en ligne** : `story_complete` portant `revue` → conforme (historique préservé).
- **G5 jointure par dossier** : `revue_scellee` sans `story` mais avec `dossier: reviews/X` rattache
  bien à la story `X` (rétro-compatibilité), tout en étant signalée au titre du schéma (G1).
- **G6 registre réel** : le contrôle sur `Registres/mission.jsonl` s'exécute et ne signale **que**
  des anomalies réelles — le compte est **borné** (assertion sur un maximum), de sorte qu'une
  régression future qui multiplierait les trous ferait ROUGIR.
- **G7 intégrité ≠ complétude** : un registre à chaîne intègre mais incomplet est accepté par
  `verify()` **et** rejeté par le contrôle de complétude — c'est la démonstration que le nouveau
  contrôle ajoute quelque chose.
- **Mutation** : retirer la règle d'attestation → G2 tombe ; retirer la jointure par dossier → G5 tombe.

## 4. Critères d'acceptation
- **CA1** schéma par type + règle d'attestation, exprimés en code et testés.
- **CA2** les deux conventions historiques (séparée / en ligne) sont acceptées ; la jointure par
  `dossier` est documentée comme rétro-compatibilité.
- **CA3** l'outil **rapporte** (ne réécrit jamais) et distingue explicitement intégrité et complétude.
- **CA4** suite complète verte, couverture ≥ 85 % ; aucun gate CI ajouté ici (REG-029B).

## 5. Revue — objections mineures traitées (tour R1, APPROVE 3/3, 0 bloquante)
- **« couverture non vérifiable dans le pack »** — objection fondée : le pack R1 a été construit
  pendant que la suite tournait encore. Mesure jointe au pack R2 : **93 %** sur le module neuf
  (`registre_completude.py`, 41 instructions / 3 non couvertes) et **91 %** au global,
  soit au-dessus du seuil CA4 (≥ 85 %). L'objection portait sur la **preuve**, pas sur le code.
- **« `charger(chemin)` sans annotation »** — objection fondée : le reste du module est typé.
  Corrigé en `chemin: str | Path`. Aucun changement de comportement (8/8 tests toujours verts) ;
  la revue est **re-scellée** sur le contenu corrigé, car un sceau n'atteste que ce qu'il a lu.
