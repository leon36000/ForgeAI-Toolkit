# TRUST-019B — Tier 1 : HMAC-SHA256 à clé locale pour le registre (FAI-U-019)

Implémente la décision de l'ADR TRUST-019A §8.3 / contrat §9.

## Cause racine (prouvée)
`core/registre.py::verify` ne validait qu'une chaîne SHA-256 NUE : un attaquant capable d'écrire le
fichier réécrit TOUTE la chaîne de façon cohérente et `verify()` renvoie `None` (aucune erreur).
Le SHA-256 sans secret est tamper-EVIDENT, pas tamper-PROOF. Reproduit par exécution (preuve rouge).

## Changement (Tier 1, conforme au contrat §9)
- `init_key(path) -> key_id` : commande EXPLICITE (jamais implicite), clé 32 octets, permission 0600
  DÈS LA CRÉATION via `os.open(O_CREAT|O_EXCL, 0o600)` (aucune fenêtre write-puis-chmod), idempotente ;
  renvoie l'empreinte publique `key_id`, jamais la clé.
- `append(..., key_path=None)` : keyword-only, défaut = Tier 0 INCHANGÉ. Avec clé : ajoute `key_id`
  et le `hash` devient un HMAC-SHA256 (comparaison en temps constant via `hmac.compare_digest`).
- `verify(..., key_path=None)` : entrée avec `key_id` -> HMAC ; entrée SANS `key_id` alors qu'une clé
  est fournie -> **refus explicite de DÉCLASSEMENT Tier 1 -> Tier 0** (correction issue du test rouge :
  la 1re implémentation retombait silencieusement en SHA-256 nu = attaque par downgrade non détectée).
- `verify_status(...)` : `OK` / `UNVERIFIED` (key_id présent, aucune clé) / `INVALID`.
- Rétro-compatibilité STRICTE : `verify(reg)` sans clé sur une chaîne Tier 0 historique -> `None`.
  Aucune migration destructive.

## Preuves d'exécution
1. chaîne saine (clé) -> `None` / status `OK`
2. réécriture intégrale sans la clé -> `seq 1: entrée sans key_id alors qu'une clé est fournie
   (déclassement Tier 1 -> Tier 0 refusé)` / status `INVALID`  ← le défaut FAI-U-019 est CORRIGÉ
3. chaîne Tier 1 sans clé disponible -> status `UNVERIFIED` (jamais un OK silencieux)
4. chaîne Tier 0 historique -> `None` (rétro-compat)
Rouge : reviews/TRUST-019B/RED-reproduction.txt · Vert : reviews/TRUST-019B/GREEN-focused.txt (23/23).
Suite complète verte. no-stub-scan OK (264). gitleaks 0.

## Portée honnête (limites déclarées, ADR §3)
Tier 1 défend contre un attaquant qui peut ÉCRIRE le registre mais ne peut PAS LIRE la clé.
Il ne défend PAS contre root ni contre un attaquant sous le MÊME UID que l'écrivain (Tier 3 ed25519
et l'ancrage externe restent la réponse à ces tiers — hors périmètre de ce package).

## Rollback
`git revert` -> retour au Tier 0 ; les chaînes Tier 0 restent vérifiables (aucune migration destructive).
