# SECRET-020A — ADR T3 : modèle de permission et unseal OpenBao

## Identité

- **Owner/repo** : `leon36000/ForgeAI-Toolkit`
- **Branche cible** : `main`
- **Branche de travail** : `docs/SECRET-020A-openbao-unseal-permissions`
- **Exécuteur** : `COPILOT`
- **Lane** : `openbao-permission-design`
- **Statut** : `DESIGN_FIRST` (aucun code produit — ADR uniquement, arrêt après fusion)
- **Priorité/Sévérité** : `P2_HIGH` / `S2_MEDIUM`
- **Finding source** : `FAI-U-020`
- **Dépendance** : `ORCH-001` — fusionné dans `main` (`f8928ab0`, PR #155 ; archivage `1b09b399`,
  PR #156).

## Procédure exécutée

1. Lu `00-LIRE-MOI-EN-PREMIER.md`, contrat commun, `ISSUES/SECRET-020A.md` et
   `AUDIT-REFERENCE/ORIGINAL-ISSUES/FAI-U-020.md` en intégralité.
2. Vérifié via `list_next_tasks.py --repo .` : `completed_count: 2` (ORCH-001, SAST-042),
   `eligible: [SECRET-020A]`.
3. Vérifié `coordination/active-claims.json` : `claims: []` — aucun claim concurrent.
4. Créé la branche `docs/SECRET-020A-openbao-unseal-permissions` depuis le dernier `origin/main`
   (`c144300...`, PR #159 fusionnée) — après `git reset --hard origin/main` pour garantir un
   état propre du worktree.
5. Vérifié la baseline : `no_stub_scan.py --all` OK (261 fichiers, 0 violation),
   `registre.py verify Registres/mission.jsonl` OK (256 entrées, chaîne intègre).
6. Lu intégralement `src/forgeai/deploy/openbao_flow.py` (`FileKeyStore`, `FileSecretStore`,
   `_write_file`, `prepare_key_store`, `KubectlKeyStore`), `src/forgeai/renderers/compose.py`
   (bloc `openbao-unsealer`, bind-mount `./openbao-keys:/keys:ro`), `src/forgeai/renderers/k3s.py`
   (bloc sidecar S3, volume `Secret` `openbao-keys`, `items: [unseal_key]`), et
   `src/forgeai/models/vault.py` (motif d'écriture atomique de référence).
7. **Confirmé que le défaut est toujours LIVE** sur `origin/main` actuel :
   `_write_file(self._unseal_path, data["unseal_key"], 0o644)` à
   `deploy/openbao_flow.py:53` — pas d'`ALREADY_FIXED`.
8. Vérifié par recherche externe l'UID/GID fixe de l'image officielle `openbao/openbao:2.6.0`
   (utilisateur `openbao`, `UID:GID = 1000:1000`, convention Alpine `adduser -S`) — preuve
   nécessaire pour évaluer la faisabilité d'un modèle par groupe (`0640`).
9. **Reproduit empiriquement la fenêtre de course "avant chmod"** évoquée dans l'objectif de
   l'issue : script Python exécuté dans cette session démontrant que `Path.write_text()` crée
   le fichier à `0o664` (umask hérité `0o002`) AVANT que `os.chmod(path, mode)` ne durcisse à la
   cible — fenêtre TOCTOU affectant `root_token`/jeton applicatif (cible `0600`), motif
   structurellement présent dans TOUT appelant de `_write_file()`. Confirmé que
   `models/vault.py` utilise déjà le motif atomique correct (`os.open(mode=...)` +
   `os.fdopen`) — établit qu'une correction cohérente est faisable sans nouveau risque.
10. Rédigé l'ADR complet : `CANON/adr/ADR-SECRET-020A-openbao-unseal-permissions.md` — contexte,
    modèle de menace (surface hôte vs surface Pod k8s), analyse de la raison actuelle du 0644,
    5 alternatives considérées (dont 3 rejetées avec justification), décision recommandée
    (0640 + GID vérifié à l'exécution + garde de repli, motif d'écriture atomique, aucune
    régression sur la séparation root/unseal déjà conforme), contrat d'implémentation pour le
    package dépendant, et preuves à l'appui (citations exactes de fichiers/lignes).
11. Toutes les affirmations factuelles de l'ADR (lignes de code, bind-mounts, absence de
    `fsGroup`/`defaultMode`, motif `vault.py`, digest d'image) ont été re-vérifiées ligne par
    ligne contre le code source réel après rédaction — aucune donnée inventée.
12. Vérifié le scope avant commit : diff limité à `CANON/**`, `Docs/**`,
    `stories/SECRET-020A.md`, `reviews/SECRET-020A/**`, `Registres/PATCH-SECRET-020A.jsonl` —
    **zéro fichier `src/forgeai/**` modifié** (conforme au mandat `DESIGN_FIRST`).
13. Gates exécutés : `no_stub_scan.py --all`, `gitleaks detect` (aucune fuite),
    `git diff --stat origin/main -- src/forgeai/` (vide).
14. **Revue aveugle scellée (round 1)** — voir `reviews/SECRET-020A/README.md` pour le détail
    (recommandation non-liante ; l'approbation finale requise reste celle de Nathan, distincte).

## Root cause (analysée, pas seulement supprimée — critère d'acceptation #1)

Le mode `0644` de `unseal_key` (backend Compose) est un choix documenté et fondé : le conteneur
`openbao-unsealer` tourne sous l'UID non-root fixe de l'image officielle, distinct de l'UID de
l'opérateur qui écrit le fichier via bind-mount — un `0600` classique serait illisible par le
conteneur (comportement prouvé e2e S6, cité dans le commentaire du code). Le défaut réel n'est
pas que `0644` soit injustifié, mais qu'il est **plus permissif que nécessaire** : `0644` ouvre
la lecture à tout compte du système hôte, alors que seul le groupe de l'utilisateur `openbao`
de l'image (GID `1000`, vérifiable à l'exécution) est réellement requis. Voir l'ADR pour
l'analyse complète et les alternatives.

## Défaut additionnel découvert (hors périmètre `FAI-U-020` mais requis par l'objectif de
l'issue — "récupération avant chmod")

`_write_file()` utilise `write_text()` puis `chmod()` — motif non atomique créant une fenêtre
de permissions temporairement plus larges que la cible (mesuré `0o664` dans cette session avec
umask hérité `0o002`). Documenté dans l'ADR §6 avec preuve de reproduction et recommandation de
correctif (motif `os.open(mode=...)` déjà utilisé dans `models/vault.py`).

## Root token / unseal key — déjà conforme (critère d'acceptation #2)

Confirmé dans le code actuel : `root_token` réside dans un fichier séparé (`root_path`), jamais
monté au sidecar/conteneur unsealer, ni en Compose (absent du bind-mount `./openbao-keys:/keys:ro`)
ni en K3s (le Secret k8s expose au sidecar uniquement l'item `unseal_key`). Aucun changement
requis sur ce point — préservation exigée pour toute implémentation future.

## Limites / non fait dans cette branche

- Aucune implémentation de code n'a été effectuée (mandat `DESIGN_FIRST` strict) — le
  correctif (chown/chmod runtime, motif d'écriture atomique, tests rouge/vert) est délégué à un
  package d'implémentation séparé, créé après approbation de l'ADR.
- Amélioration K3s `defaultMode: 0440` documentée comme optionnelle/non-bloquante (hors
  périmètre strict de `FAI-U-020`, qui cible uniquement le backend Compose).

## Rapport final

```text
PACKAGE: SECRET-020A
REPOSITORY: https://github.com/leon36000/ForgeAI-Toolkit
BRANCH: docs/SECRET-020A-openbao-unseal-permissions
BASE_COMMIT: c144300 (origin/main, post-PR #159)
MERGE_SHA: (à renseigner après fusion)
FILES_CHANGED: CANON/adr/ADR-SECRET-020A-openbao-unseal-permissions.md, stories/SECRET-020A.md,
  reviews/SECRET-020A/**, Registres/PATCH-SECRET-020A.jsonl
ROOT_CAUSE: unseal_key 0644 world-readable sur le backend Compose (raison documentée mais plus
  permissive que nécessaire) ; fenêtre de course write_text+chmod dans _write_file() découverte
  pendant l'analyse (affecte root_token/jeton applicatif, cible 0600).
REPRODUCTION_BEFORE: FAI-U-020 confirmé LIVE (deploy/openbao_flow.py:53) ; fenêtre de course
  reproduite empiriquement (0o664 mesuré avant chmod, umask 0o002).
IMPLEMENTATION: Aucune (DESIGN_FIRST — ADR uniquement, implémentation déléguée).
FOCUSED_TESTS: N/A (aucun code modifié).
NEGATIVE_TESTS: N/A — justifié : package ADR-only, aucun code testable produit.
FULL_GATES: no_stub_scan.py --all OK ; gitleaks detect OK (0 fuite) ; git diff --stat
  origin/main -- src/forgeai/ vide (0 changement produit).
SECURITY_SCANS: gitleaks OK ; analyse manuelle de la surface de menace documentée dans l'ADR.
EVIDENCE_PATH: CANON/adr/ADR-SECRET-020A-openbao-unseal-permissions.md,
  AUDIT-REFERENCE/ORIGINAL-ISSUES/FAI-U-020.md, reviews/SECRET-020A/civ/*.verdict.json
ROLLBACK_RESULT: Revert du commit — aucune donnée/schéma modifié (ADR pur), rollback trivial.
LIMITATIONS: Implémentation du correctif recommandé (chown/chmod + motif atomique) hors
  périmètre de ce package, à assigner séparément après approbation de l'ADR.
OPEN_RISKS: Approbation explicite de Nathan requise avant que l'ADR soit considéré DONE
  (critère d'acceptation distinct de la revue aveugle 3/3, non encore obtenue au moment de la
  rédaction de ce rapport).
READY_FOR_PR: YES
```
