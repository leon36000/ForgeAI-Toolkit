# ERR-041C — Rédiger stderr et diagnostics SSH

- **Issue** : #271 · **Tier** : T2 (sécurité — fuite de secret dans les diagnostics SSH)
- **Dépend de** : ERR-041A (`forgeai.core.redaction`), SSH-021 (bootstrap durci) — tous deux mergés.
- **Reprise lane CODEX** · **Périmètre** : `src/forgeai/network/node_add.py`,
  `tests/test_err041c_ssh_diag.py` (nouveau), `stories/ERR-041C.md`.

## 1. Problème (code réel)
`network/node_add.py` interpole la sortie brute d'un sous-processus SSH dans un `NodeAddError` :
- `install_key` (l.60) : `NodeAddError(f"ssh-copy-id échec: {proc.stderr.strip()}")` — le stderr de
  `ssh-copy-id` peut contenir un fragment sensible.
- `key_fingerprint` (l.109) : `NodeAddError(f"...la sortie: {output}")` — sortie brute de `ssh-keygen`.
Déjà sûrs : `SshRunner.run` (SSH-007) ne met pas le stderr dans un message ; `enroll_hostkey` n'interpole rien.

## 2. Décision
Envelopper les deux fragments par `redact_text(...)` de `forgeai.core.redaction` (import à ajouter en
tête de `node_add.py`). Texte fixe conservé ; seul le fragment sous-processus est rédigé. Même modèle
éprouvé qu'ERR-041B (compose/k3s).

## 3. TDAD (RED d'abord)
Mock du bootstrap : `install_key` échoue avec un `stderr` porteur d'un faux-secret (jeton Bearer, clé d'API)
→ `NodeAddError` levée, secret ABSENT (fenêtres 8 car.), `REDACTED` présent, texte fixe conservé.
`key_fingerprint` avec une sortie porteuse d'un faux-secret → rédigée. Mutation : retirer `redact_text`
d'un site → le test tombe. Non-régression : tests node_add/SSH-021 verts.

## 4. Critères d'acceptation
- **CA1** les 2 sites : stderr/sortie SSH rédigés (secret + fenêtres absents, `REDACTED` présent).
- **CA2** non-régression node_add/SSH-021 ; suite complète verte, no-stub, couverture ≥ 85 %.
