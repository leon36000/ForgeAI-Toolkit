# SAST-042 — Trier les signaux SAST résiduels sans créer un patch omnibus

## Identité

- **Owner/repo** : `leon36000/ForgeAI-Toolkit`
- **Branche cible** : `main`
- **Branche de travail** : `audit/SAST-042-residual-triage`
- **Exécuteur** : `COPILOT`
- **Lane** : `governance`
- **Statut** : `TRIAGE_ONLY` (aucun code produit modifié)
- **Priorité/Sévérité** : `P4_LOW` / `S3_LOW`
- **Finding source** : `FAI-U-042`
- **Dépendance** : `ORCH-001` — fusionné dans `main` (`f8928ab0`, PR #155 ; archivage `1b09b399`, PR #156).

## Procédure exécutée

1. Lu `00-LIRE-MOI-EN-PREMIER.md`, contrat commun, `ISSUES/SAST-042.md` en intégralité (déjà fait
   lors des étapes précédentes de cette session).
2. Vérifié via `list_next_tasks.py --repo /home/pc1/ForgeAI-Toolkit` : `ORCH-001` = `COMPLETED`,
   `SAST-042` = premier package `ELIGIBLE_TRIAGE`.
3. Vérifié `coordination/active-claims.json` : `claims: []` — aucun claim concurrent sur la lane
   `governance` ni sur les chemins `AUDIT-OUTPUT/**`, `Docs/audit/**`, `Registres/PATCH-SAST-042.jsonl`.
4. Créé la branche `audit/SAST-042-residual-triage` depuis le dernier `origin/main`
   (`1b09b3966be41440f023d92c82208b0a741939d9`) dans le worktree existant.
5. Vérifié la baseline avant modification : `no_stub_scan.py --all` OK (261 fichiers, 0 violation),
   `registre.py verify Registres/mission.jsonl` OK (255 entrées, chaîne intègre).
6. Ré-exécuté les scanners exacts prescrits par l'issue :
   - `python -m bandit -r src/forgeai -f json -o AUDIT-OUTPUT/sast/bandit.json` → 37 signaux.
   - `semgrep scan --config auto --json --output AUDIT-OUTPUT/sast/semgrep.json src/forgeai`
     → 23 signaux.
7. Classifié les 60 signaux en 7 clusters (voir `AUDIT-OUTPUT/sast/classification.json` et
   `Docs/audit/SAST-042.md` pour le détail complet, cause racine et preuve par cluster) :
   pour chaque site, code source lu intégralement, appelants tracés jusqu'à l'origine de la
   donnée (config opérateur vs entrée non fiable), commentaires de justification existants
   vérifiés.
8. **Résultat : 0 signal `CONFIRMED`.** Répartition : 1 cluster `DUPLICATE+ACCEPTED_RISK`
   (20 signaux urllib B310/dynamic-urllib, 10 sites, confirme `FAI-U-042` `ACCEPTED_EVIDENCE`
   toujours valide sans régression), 3 clusters `FALSE_POSITIVE` (insecure-file-permissions —
   la règle recommande une régression de sécurité pour des répertoires de secrets ;
   python37-compat — hors cible du projet `>=3.10` ; B105 chemin KV/nom Secret K8s/chaîne vide),
   1 cluster mixte B105 (2 `FALSE_POSITIVE` + 1 `ACCEPTED_RISK` immudb dev déjà documenté),
   2 clusters `ACCEPTED_RISK` (subprocess B404/B603/B607 — forme liste uniquement, jamais
   `shell=True`, secrets jamais en argv ; B110 try/except/pass — 4 sites de résilience
   opérationnelle non sécuritaires).
9. Aucune issue de correction distincte requise (aucun signal `CONFIRMED`).
10. Gates exécutés : `no_stub_scan.py --all` (post-changement), `gitleaks detect` (aucune fuite),
    `git diff --stat origin/main -- src/forgeai/` (vide — preuve qu'aucun fichier produit n'a
    été modifié).
11. **Revue aveugle scellée (round 1)** — `civ_review.py --story reviews/SAST-042/civ --pack
    /tmp/sast042-pack.md`, modèles `DeepSeek-V4-Pro, Gemini-3.1-Pro, LongCat-2.0` (3 vendors
    distincts, aucun n'est le codeur) → **APPROVE 3/3**, `prompt_sha256=3b405453929d5856...`,
    0 objection bloquante. 1 objection mineure (Gemini) : le rapport bandit compressé
    (`bandit.json.gz`) empêche une vérification directe ligne-à-ligne dans le diff. Corrigée
    par l'ajout de `AUDIT-OUTPUT/sast/bandit-summary.txt` (37 lignes `test_id\tfichier:ligne`,
    en clair, triable et diffable) sans réintroduire le déclenchement du filtre grep secondaire.

## Tests négatifs

Non applicable : ce package ne modifie aucun comportement de code (TRIAGE_ONLY). Il n'existe
pas de « défaut » à reproduire en rouge — l'issue elle-même prévoit l'option `ALREADY_FIXED`/
triage pur lorsque les signaux sont déjà bornés, ce qui est le cas ici pour les 60/60 signaux.

## Tests de sécurité

- `gitleaks detect --source .` → `no leaks found`.
- Scanners SAST eux-mêmes constituent le test de sécurité de ce package (bandit + semgrep,
  voir rapports bruts `AUDIT-OUTPUT/sast/*.json`).

## Tests de performance

Non applicable — aucune modification de code produit, aucun chemin d'exécution changé.

## SonarQube Pro

Non disponible depuis cet environnement (projet SonarCloud privé, aucun jeton d'API accessible ;
vérifié par requête anonyme sur `sonarcloud.io/api/components/show` → `Project doesn't exist`).
Non bloquant selon le texte de l'issue (« dès qu'ils sont disponibles »).

## Preuves obligatoires

- Versions des scanners et commande exacte : `AUDIT-OUTPUT/sast/scanner-versions.txt`.
- Rapports bruts complets : `AUDIT-OUTPUT/sast/bandit.json.gz` (compressé, voir
  `scanner-versions.txt` pour le motif), `AUDIT-OUTPUT/sast/semgrep.json`.
- Classification machine-lisible par signal : `AUDIT-OUTPUT/sast/classification.json`.
- Rapport narratif : `Docs/audit/SAST-042.md`.
- Preuve qu'aucun fichier produit n'a changé : `git diff --stat origin/main -- src/forgeai/`
  (vide, capturée dans `Docs/audit/SAST-042.md`).
- Aucune issue distincte à ouvrir (aucun signal `CONFIRMED`).

## Rollback

Revert du commit unique (aucune migration, aucun fichier produit touché — rollback trivial et
sans risque).

## Rapport final

```text
PACKAGE: SAST-042
REPOSITORY: https://github.com/leon36000/ForgeAI-Toolkit
BRANCH: audit/SAST-042-residual-triage
BASE_COMMIT: 1b09b3966be41440f023d92c82208b0a741939d9
MERGE_SHA: (à renseigner après fusion)
FILES_CHANGED: AUDIT-OUTPUT/sast/*.json, AUDIT-OUTPUT/sast/scanner-versions.txt,
  Docs/audit/SAST-042.md, stories/SAST-042.md, reviews/SAST-042/README.md,
  Registres/PATCH-SAST-042.jsonl
ROOT_CAUSE: N/A — triage pur, 60/60 signaux classés FALSE_POSITIVE/ACCEPTED_RISK/DUPLICATE,
  0 CONFIRMED
REPRODUCTION_BEFORE: N/A (TRIAGE_ONLY, pas de défaut de code à reproduire)
IMPLEMENTATION: N/A — aucun fichier src/forgeai modifié (preuve : diff vide)
FOCUSED_TESTS: no_stub_scan.py --all (OK, 261 fichiers, 0 violation)
NEGATIVE_TESTS: non applicable, justifié ci-dessus
FULL_GATES: no_stub_scan.py --all OK ; registre.py verify OK
SECURITY_SCANS: gitleaks detect — no leaks found ; bandit 1.9.4 (37 signaux) ;
  semgrep 1.168.0 --config auto (23 signaux)
EVIDENCE_PATH: AUDIT-OUTPUT/sast/, Docs/audit/SAST-042.md
ROLLBACK_RESULT: trivial (revert du commit unique, aucune migration)
LIMITATIONS: SonarQube Pro non accessible depuis cet environnement (projet privé)
OPEN_RISKS: aucun — 0 signal CONFIRMED
READY_FOR_PR: YES
```
