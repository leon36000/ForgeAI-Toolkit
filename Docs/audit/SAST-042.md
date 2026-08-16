# SAST-042 — Triage des signaux SAST résiduels (rapport d'audit)

- **Commit de base analysé** : `1b09b3966be41440f023d92c82208b0a741939d9` (`origin/main`, post-merge ORCH-001)
- **Finding source** : `FAI-U-042` (statut original `ACCEPTED_EVIDENCE`, vague V6)
- **Scanners** : bandit 1.9.4 (`python -m bandit -r src/forgeai -f json -o evidence/audit-output/sast/bandit.json`),
  semgrep 1.168.0 (`semgrep scan --config auto --json --output evidence/audit-output/sast/semgrep.json src/forgeai`)
- **Statut du package** : `TRIAGE_ONLY` — **aucun fichier produit modifié dans cette branche**
  (`git diff --stat origin/main -- src/forgeai` est vide, voir preuve ci-dessous).
- **Rapport machine-lisible complet** : `evidence/audit-output/sast/classification.json`
- **Rapports bruts** : `evidence/audit-output/sast/bandit.json.gz` (compressé — voir note ci-dessous),
  `evidence/audit-output/sast/semgrep.json`

## Méthode

1. Ré-exécution intégrale de bandit et semgrep sur `src/forgeai` au commit courant (37 + 23 = 60 signaux).
2. Regroupement en 7 clusters par (règle, cause racine partagée) — un signal individuel par tuple
   (fichier, ligne, règle), jamais résumé sans preuve.
3. Pour chaque cluster : lecture intégrale du code source au site signalé, remontée jusqu'à
   l'origine de la donnée (config opérateur vs entrée non fiable), vérification de l'existence
   d'une justification déjà documentée en commentaire (`# nosec`, `# noqa: S310/S105 proof:allow`).
4. Classification stricte : `CONFIRMED` (nécessite un correctif → issue séparée), `FALSE_POSITIVE`
   (la règle ne s'applique pas ou sa recommandation serait elle-même une régression),
   `ACCEPTED_RISK` (risque réel mais borné/documenté, déjà accepté), `DUPLICATE` (même cause,
   plusieurs outils/règles).

## Résultat — 60/60 signaux classés, 0 CONFIRMED

| Cluster | Règles | Signaux | Sites | Statut |
|---|---|---|---|---|
| C1 | bandit B310 + semgrep dynamic-urllib | 20 | 10 | `DUPLICATE` + `ACCEPTED_RISK` |
| C2 | semgrep insecure-file-permissions | 4 | 4 | `FALSE_POSITIVE` |
| C3 | semgrep python37-compatibility-importlib2 | 9 | 9 | `FALSE_POSITIVE` |
| C4 | bandit B105 (cli.py) | 3 | 3 | `FALSE_POSITIVE` (x2) + `ACCEPTED_RISK` (x1) |
| C5 | bandit B105 (renderers/k3s.py) | 1 | 1 | `FALSE_POSITIVE` |
| C6 | bandit B404 + B603 + B607 (subprocess) | 19 | 9 fichiers | `ACCEPTED_RISK` |
| C7 | bandit B110 (try/except/pass) | 4 | 4 | `ACCEPTED_RISK` |
| **Total** | | **60** | | **0 CONFIRMED** |

### C1 — urllib B310 / dynamic-urllib (20 signaux, 10 sites)

Les 10 sites signalés identiquement par bandit ET semgrep correspondent à des appels
`urllib.request.urlopen` vers des services **auto-hébergés et configurés par l'opérateur**
(Ollama, Qdrant, TEI, Langfuse, OpenBao/Vault, immudb, gateway modèles cloud via
`forgeai route configure`) ou un téléchargement depuis `catalogue.json` (1577 briques vérifiées).
Aucune URL n'est dérivée d'une entrée réseau non authentifiée. Confirme que `FAI-U-042`
(`ACCEPTED_EVIDENCE`) reste valide sans régression sur le commit courant.

### C2 — insecure-file-permissions (4 signaux)

Faux positif : la règle recommande `0o644` (lecture pour tous) comme « plus sûr » que
`0o700`/`0o711`. Les 4 sites protègent des **répertoires de secrets** (coffre de clés API,
clé d'unseal OpenBao, clés ed25519 privées) : suivre la suggestion de la règle constituerait
une régression de sécurité, pas une correction.

### C3 — python37-compatibility-importlib2 (9 signaux)

Faux positif : règle de compatibilité Python 3.7, alors que `pyproject.toml` déclare
`requires-python = ">=3.10"`. Activée automatiquement par `--config auto`, non pertinente ici.

### C4/C5 — B105 hardcoded-password (4 signaux)

3 des 4 sont des faux positifs (chemin KV OpenBao, nom d'objet Kubernetes Secret, chaîne vide
d'initialisation — aucun n'est une valeur de mot de passe). Le 4ᵉ (constante `IMMUDB_PASSWORD`,
valeur `"immudb"`) est le identifiant public par défaut d'immudb en mode dev, déjà documenté en
commentaire — risque accepté, durcissement production hors périmètre.

### C6 — subprocess B404/B603/B607 (19 signaux, 9 fichiers)

Outil d'orchestration devant légitimement invoquer `docker`, `kubectl`, `ssh`/`ssh-copy-id`.
Vérification site par site : forme liste uniquement (jamais `shell=True`), pas de concaténation
de chaîne shell, secrets jamais en argv (invariant documenté dans `src/forgeai/deploy/openbao_flow.py`),
entrées provenant de la configuration opérateur (wizard d'ajout de nœud) ou de fichiers JSON
validés en amont. Le chemin partiel (`B607`) sur `docker`/`kubectl` est le comportement standard
attendu (portabilité multi-distribution via `PATH`).

### C7 — B110 try/except/pass (4 signaux)

4 sites dans `src/forgeai/web/server.py` : nettoyage best-effort d'un fichier temporaire, mise à jour d'un
état de déploiement sous verrou, arrêt défensif d'un sous-processus déjà terminé, ouverture
best-effort du navigateur. Aucun n'avale une exception liée à l'auth/l'autorisation/la
validation d'entrée.

## SonarQube Pro

Non disponible depuis cet environnement : le projet SonarCloud (`leon36000_ForgeAI-Toolkit`) est
privé et aucun jeton d'API n'est accessible ici (vérifié : `sonarcloud.io/api/components/show`
répond `Project doesn't exist` sans authentification). Le check CI `SonarCloud Code Analysis`
existant reste la source de vérité et est vert sur `origin/main`. À incorporer si un accès est
fourni ultérieurement — non bloquant selon le texte de l'issue (« dès qu'ils sont disponibles »).

## Preuve — aucun fichier produit modifié

```text
$ git diff --stat origin/main -- src/forgeai/
(vide)
```

## Conclusion

Aucun signal ne justifie la création d'une issue de correction distincte. Le triage confirme
que le code source est déjà dans un état sécurisé et documenté pour l'ensemble des 60 signaux
résiduels réexaminés.
