# TRUST-019A — ADR : modèle de menace et racine de confiance des registres

## Identité

- **Owner/repo** : `leon36000/ForgeAI-Toolkit`
- **Branche cible** : `main`
- **Branche de travail** : `docs/TRUST-019A-ledger-trust-model`
- **Exécuteur** : `COPILOT`
- **Lane** : `trust-design`
- **Statut** : `DESIGN_FIRST` (aucun code produit — ADR uniquement, arrêt après fusion)
- **Priorité/Sévérité** : `P2_HIGH` / `S2_MEDIUM`
- **Finding source** : `FAI-U-019` / `FND-SEC-TAMPER-1`
- **Dépendance** : `ORCH-001` — fusionné dans `main` (`f8928ab0`, PR #155 ; archivage `1b09b399`,
  PR #156).

## Procédure exécutée

1. Lu `00-LIRE-MOI-EN-PREMIER.md`, contrat commun, `ISSUES/TRUST-019A.md` et
   `AUDIT-REFERENCE/ORIGINAL-ISSUES/FAI-U-019.md` en intégralité (retrouvés dans le pack ZIP
   extrait `/tmp/copilote-zip/COPILOTE-FORGEAI-PACK/` — non présents comme tels dans le dépôt).
2. Vérifié via `SCRIPTS/list_next_tasks.py --repo .` (script canonique du pack, exécuté contre
   le dépôt réel) : `completed_count: 3` (ORCH-001, SAST-042, SECRET-020A), `eligible` liste
   `TRUST-019A` en premier (avant `UI-039`), aucune dépendance manquante — confirme le choix.
3. Vérifié l'absence de claim actif (`coordination/active-claims.json` : `claims: []`).
4. Synchronisé sur le dernier `origin/main` (`1f00076`, post-PR #162 archivage SECRET-020A) et
   créé la branche `docs/TRUST-019A-ledger-trust-model` depuis ce commit exact.
5. Vérifié les gates de référence AVANT tout changement : `no_stub_scan.py --all` OK (261
   fichiers), `registre.py verify Registres/mission.jsonl` OK (257 entrées, chaîne intègre),
   `validate_coordination.py` PASS (3 complétés, 0 claim, 0 erreur).
6. Lu intégralement le code source réel concerné : `src/forgeai/core/registre.py` (module
   complet, 123 lignes), `src/forgeai/catalogue/loader.py` (module complet, 92 lignes),
   `src/forgeai/models/vault.py` (module complet, 132 lignes — construction HMAC-SHA256 déjà
   revue/approuvée par revue aveugle 3 vendors, réutilisable sans nouvelle primitive), et les
   tests existants `tests/test_registre.py` (99 lignes, 9 tests — confirmé : couvre uniquement
   l'altération *partielle* d'une entrée, jamais une réécriture *totale* cohérente de la chaîne).
7. **Reproduit empiriquement le défaut par le chemin réel** (aucun mock) :
   - Registre : construit une chaîne légitime à 2 entrées avec `scripts/registre.py` réel, puis
     simulé un attaquant à accès écriture FS qui réécrit le fichier entier depuis la genèse avec
     un payload falsifié et des hash recalculés correctement. `registre.verify()` retourne
     `None` (aucune détection) — preuve rouge archivée dans cette story (§ voir ADR §2.1).
   - Catalogue : même reproduction contre `forgeai.catalogue.loader.verify_catalogue` — réécrit
     `catalogue.json` ET son `.sha256` co-localisé ; `verify_catalogue` accepte silencieusement
     le nouveau digest (ADR §2.2).
   - **Découverte additionnelle non documentée par le finding original** : le gate CI
     `registres` (`.github/workflows/gates.yml:21-26`) exécute uniquement
     `registre.py verify Registres/*.jsonl` — comme prouvé ci-dessus, cette commande retourne
     succès sur une réécriture totale cohérente. Le gate obligatoire de la protection de branche
     `main` ne détecte donc PAS ce cas, contrairement à ce qu'un reviewer humain pourrait
     supposer en voyant `registres ✓` sur une PR (ADR §2.3).
8. Vérifié la configuration réelle de protection de branche `main` via l'API GitHub
   (`gh api repos/.../branches/main/protection`) : `allow_force_pushes: false`,
   `allow_deletions: false`, mais **`enforce_admins: false`** (un compte admin contourne ces
   protections) et `required_signatures: false` (pas de vérification de signature de commit).
   Confirmé aussi que `Registres/*.jsonl` sont normalement suivis par git (`git log --
   Registres/mission.jsonl` montre l'historique complet) — cette observation devient le
   fondement du Tier 2 (ancrage externe) recommandé dans l'ADR.
9. **Rédigé `CANON/adr/ADR-TRUST-019A-registres-modele-de-menace-racine-confiance.md`**
   (structure réutilisant le format éprouvé de `ADR-SECRET-020A`) couvrant : contexte,
   reproduction empirique, modèle de menace en tableau (couverts/non couverts, limite
   root/local explicite — critère d'acceptation), 5 alternatives (statu quo rejeté ; HMAC local
   Tier 1 retenue pour packages dépendants ; ancrage Git/GitHub Tier 2 retenue, coût zéro
   nouvelle dépendance ; immudb rejetée en défaut/retenue en option avancée ; signature ed25519
   T3 Tier 3 retenue pour les décisions Nathan), tableau racine de confiance par tier, tableau
   rotation/récupération/sauvegarde/offline par tier (critère d'acceptation explicite),
   classification des opérations exigeant T3 vs tiers inférieurs, décision recommandée (incluant
   une correction de configuration dépôt sans code : activer `enforce_admins`), contrat
   d'implémentation pour `TRUST-019B`/`REG-029B`, et preuves à l'appui.
10. Vérifié le scope avant commit : diff limité à `CANON/**`, `stories/TRUST-019A.md` — **zéro
    fichier `src/forgeai/**` modifié** (conforme au mandat `DESIGN_FIRST`).
11. Gates exécutés : `no_stub_scan.py --all` OK, `gitleaks detect` (aucune fuite),
    `git diff --stat origin/main -- src/forgeai/` (vide).
12. **Revue aveugle scellée round 1** (`reviews/TRUST-019A/civ/*.verdict.json`,
    `prompt_sha256=fbd6394e5110bd15acfbc32286072cd6f92ae3f8f2df2ecdbb7322d6df97dde8`) :
    **REJECT tally (2/3 APPROVE, 1 REJECT)**. `DeepSeek-V4-Pro` a soulevé une objection
    `majeure` : `reviews/TRUST-019A/civ/*.verdict.json` et `Registres/PATCH-TRUST-019A.jsonl`
    sont référencés dans `FILES_CHANGED` du rapport final mais absents du diff soumis à la
    revue. `Gemini-3.1-Pro` et `LongCat-2.0` : APPROVE, zéro objection. Proof appended au ledger
    (`Registres/PATCH-TRUST-019A.jsonl`, seq 1). **Root cause identique à celle déjà rencontrée
    et résolue pour `SECRET-020A` round 2** : ces fichiers sont délibérément exclus du diff
    transmis au pack de revue (`git diff origin/main...HEAD -- CANON/ stories/TRUST-019A.md`)
    car ce sont les artefacts de preuve du PROCESSUS de revue lui-même (verdicts scellés +
    ledger horodaté qui les référence), pas des artefacts de CONCEPTION à juger — les inclure
    créerait une auto-révision circulaire. Corrigé en ajoutant la note explicative ci-dessous
    (§ Note sur le périmètre du diff), sans changer l'approche de construction du diff. Un
    round 2 de confirmation a été lancé après cet ajout.
13. **Revue aveugle scellée round 2** — **APPROVE 3/3** (DeepSeek-V4-Pro, Gemini-3.1-Pro,
    LongCat-2.0), vendors distincts `['deepseek', 'google', 'meituan']`, `prompt_sha256`
    identique aux trois : `1931f16d61657c32e7f711fd2d17d3e1d7ed7cd6aebfe84c90d45e5552332443`.
    Une seule objection, **mineure et non bloquante** (DeepSeek-V4-Pro) : les références de
    lignes exactes et l'affirmation « vault.py déjà revue/approuvée » ne sont pas vérifiables
    depuis le diff seul. Root cause analysée : affirmation factuelle exacte mais son ancrage
    (commits `36ec4f0`/`7a2406b`/`6b4e265`) n'était pas cité — corrigé en ajoutant ces références
    de commits vérifiables (`git log --oneline -- src/forgeai/models/vault.py`) directement
    dans l'ADR §10, sans changer le fond de l'analyse. Preuve : `Registres/PATCH-TRUST-019A.jsonl`
    seq 2, `reviews/TRUST-019A/civ2/*.verdict.json`.
14. Vérifié le scope avant chaque commit : diff limité à `CANON/**`, `stories/TRUST-019A.md`,
    `reviews/TRUST-019A/**`, `Registres/PATCH-TRUST-019A.jsonl` — **zéro fichier
    `src/forgeai/**` modifié** (conforme au mandat `DESIGN_FIRST`).
15. Gates exécutés à chaque étape : `no_stub_scan.py --all` OK, `gitleaks detect` (aucune fuite),
    `git diff --stat origin/main -- src/forgeai/` (vide).

## Note sur le périmètre du diff soumis à la revue aveugle (objection majeure round 1,
DeepSeek-V4-Pro)

Le `FILES_CHANGED` du rapport final ci-dessous liste `reviews/TRUST-019A/**` et
`Registres/PATCH-TRUST-019A.jsonl` comme faisant partie de cette PR — **exact**, ces fichiers
sont bien committés sur la branche. Ils sont **délibérément exclus** du diff transmis au pack
de revue (`git diff origin/main...HEAD -- CANON/ stories/TRUST-019A.md`), pour une raison
structurelle et non une omission : ce sont les **artefacts de preuve du processus de revue
lui-même** (verdicts scellés d'un round antérieur + ledger horodaté qui les référence) — les
inclure dans le pack reviendrait à demander aux reviewers de juger, en partie, leur propre
processus ou celui d'un round précédent, ce qui est hors du périmètre du jugement demandé
(« analyse l'ARTEFACT pour sa correction et sa sécurité », `CANON/revue-template.md`). Seul le
contenu de conception (`CANON/adr/**`, `stories/*.md`) est soumis au jugement des reviewers ;
`reviews/**`/`Registres/PATCH-*.jsonl` sont des PREUVES DU processus, pas des ARTEFACTS À JUGER
PAR le processus. Ce même pattern a déjà été rencontré et résolu de façon identique pour
`SECRET-020A` (round 2) — précédent directement applicable ici.

## Root cause (analysée, pas seulement supprimée — critère d'acceptation)

Le registre et le catalogue utilisent tous deux un hash SHA-256 **non gardé par un secret** :
n'importe quel acteur ayant un accès en écriture au fichier protégé (et, pour le catalogue, à
son `.sha256` co-localisé) peut recalculer une chaîne/un digest parfaitement cohérent après
altération, rendant la vérification `verify()`/`verify_catalogue()` aveugle à ce cas précis —
alors même qu'elle détecte correctement une altération *partielle* ou *accidentelle*. C'est un
manque structurel de garantie *authenticated* (pas de secret) et *anti-rollback* (pas d'ancre
externe), pas un bug d'implémentation du hash-chain lui-même (l'algorithme est correct pour son
objectif documenté).

## Défaut additionnel découvert pendant l'analyse (hors périmètre strict de `FAI-U-019` mais
requis par l'objectif « quelles opérations exigent T3 »)

Le gate CI obligatoire `registres` ne détecte pas une réécriture totale cohérente (§7 ci-dessus)
— documenté dans l'ADR §2.3 comme un faux sentiment de sécurité à corriger par le package
d'implémentation dépendant, pas par cette ADR (`DESIGN_FIRST`, aucun code).

## Limites / non fait dans cette branche

- Aucune implémentation de code n'a été effectuée (mandat `DESIGN_FIRST` strict) — le HMAC à
  clé locale (Tier 1), la signature ed25519 T3 (Tier 3) et la correction du gate CI sont
  délégués à un package d'implémentation séparé (`TRUST-019B`/`REG-029B`), créé après
  approbation de l'ADR.
- La recommandation de configuration dépôt (`enforce_admins: true` sur `main`) est une action
  hors-code que Nathan peut appliquer indépendamment, dès approbation de l'ADR — non exécutée
  dans cette branche (aucun accès admin dépôt disponible depuis cette session, et changement de
  configuration GitHub hors périmètre `allowed_paths` de ce package).

## Rapport final

```text
PACKAGE: TRUST-019A
REPOSITORY: https://github.com/leon36000/ForgeAI-Toolkit
BRANCH: docs/TRUST-019A-ledger-trust-model
BASE_COMMIT: 1f00076 (origin/main, post-PR #162)
MERGE_SHA: (à renseigner après fusion)
FILES_CHANGED: CANON/adr/ADR-TRUST-019A-registres-modele-de-menace-racine-confiance.md,
  stories/TRUST-019A.md, reviews/TRUST-019A/**, Registres/PATCH-TRUST-019A.jsonl
ROOT_CAUSE: Hash SHA-256 non gardé par un secret (registre + catalogue) : tamper-evident contre
  l'altération accidentelle/partielle, mais pas authenticated (pas de clé) ni anti-rollback (pas
  d'ancre externe) contre un attaquant à accès écriture FS. Gate CI `registres` ne détecte pas
  non plus une réécriture totale cohérente (découverte additionnelle).
REPRODUCTION_BEFORE: FAI-U-019/FND-SEC-TAMPER-1 confirmé LIVE ; reproduit empiriquement avec
  scripts/registre.py et forgeai.catalogue.loader réels — réécriture totale cohérente non
  détectée dans les deux cas (voir ADR §2.1/§2.2).
IMPLEMENTATION: Aucune (DESIGN_FIRST — ADR uniquement, implémentation déléguée).
FOCUSED_TESTS: N/A (aucun code modifié). tests/test_registre.py lu intégralement (confirmé :
  ne couvre pas la réécriture totale, angle mort documenté dans l'ADR).
NEGATIVE_TESTS: N/A — justifié : package ADR-only, aucun code testable produit.
FULL_GATES: no_stub_scan.py --all OK ; gitleaks detect OK (0 fuite) ; git diff --stat
  origin/main -- src/forgeai/ vide (0 changement produit) ; validate_coordination.py PASS.
SECURITY_SCANS: gitleaks OK ; analyse manuelle de la surface de menace documentée dans l'ADR
  (y compris vérification réelle de la protection de branche GitHub via l'API).
EVIDENCE_PATH: CANON/adr/ADR-TRUST-019A-registres-modele-de-menace-racine-confiance.md,
  AUDIT-REFERENCE/ORIGINAL-ISSUES/FAI-U-019.md, reviews/TRUST-019A/civ/*.verdict.json,
  reviews/TRUST-019A/civ2/*.verdict.json, Registres/PATCH-TRUST-019A.jsonl (seq 1-2)
ROLLBACK_RESULT: Revert du commit — aucune donnée/schéma modifié (ADR pur), rollback trivial.
LIMITATIONS: Implémentation du HMAC Tier 1, de la signature ed25519 T3 et de la correction du
  gate CI hors périmètre de ce package, à assigner séparément après approbation de l'ADR. La
  recommandation de configuration dépôt (`enforce_admins`) reste une action humaine hors-code.
REVIEW_STATUS: Round 1 REJECT tally (2/3, objection majeure de périmètre de diff, résolue sans
  changement de fond) → Round 2 **APPROVE 3/3** (0 objection bloquante, 1 objection mineure
  résolue par ajout de références de commits vérifiables). Revue aveugle scellée **CLOSE**.
OPEN_RISKS: Approbation explicite de Nathan requise avant que l'ADR soit considérée DONE
  (critère d'acceptation distinct de la revue aveugle, **désormais close en APPROVE 3/3** —
  reste uniquement l'approbation humaine explicite avant fusion).
READY_FOR_PR: YES
```
