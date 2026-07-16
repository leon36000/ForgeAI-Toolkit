# BC-models — Remédiation des défauts de la revue scellée 3/3 (models/)

Origine : revue aveugle scellée (civ_review + revue.py tally) des stories B-08/09/10/11.
Registre `revue_scellee` seq 88–91. Corriger les 6 défauts RÉELS. **TDD strict : un test
ROUGE reproduisant chaque défaut AVANT le correctif, puis VERT.** Aucun stub, no-fake.

## D1 — vault._save : race de permissions (CWE-732) — sévérité moyen
`Vault._save` fait `write_text` (fichier créé en 0644) PUIS `os.chmod(0o600)` → fenêtre où
le coffre chiffré est lisible par d'autres utilisateurs locaux.
- **Critère** : le fichier vault n'est JAMAIS créé avec des permissions plus larges que 0600.
  Créer avec `os.open(path, O_WRONLY|O_CREAT|O_TRUNC, 0o600)` (+ `os.chmod` défensif).
- **Test ROUGE→VERT** : après `put(...)`, `stat` du fichier = 0600 ; et (robustesse) un
  contrôle que la création ne passe pas par un mode par défaut large.

## D2 — strategy.resolve_spec : le nombre de slots n'est pas imposé — sévérité CRITIQUE
Avec `--roles`, `resolve_spec` accepte tout nombre de rôles pour equipe/hybride, alors que
« le choix de stratégie détermine le nombre de slots ».
- **Critère** : les rôles personnalisés RENOMMENT les slots mais ne changent pas leur NOMBRE.
  `equipe` exige exactement 4 rôles, `hybride` exactement 3, `cerveau-unique` exactement 1.
  Un nombre différent → `StrategyError` avec message clair.
- **Test** : `resolve_spec("equipe", ["a","b","c"])` → `StrategyError` ; `resolve_spec("equipe",
  4 rôles)` → ok, slots renommés ; `resolve_spec("hybride", 3 rôles)` → ok.

## D3 — gateway.assert_via_gateway : `continue` court-circuite les vérifs — sévérité CRITIQUE
Le `continue` après « pointe hors gateway » saute les vérifs *hôte-fournisseur* et
*clé-en-clair* — précisément le cas à détecter (brique vers un fournisseur avec clé en clair).
- **Critère** : chaque brique est évaluée sur TOUS les critères indépendamment ; toutes les
  violations applicables sont rapportées (pas de `continue` qui masque les autres). Une brique
  pointant un hôte fournisseur AVEC une clé en clair produit les DEUX violations spécifiques.
- **Test** : une brique câblée vers l'hôte fournisseur `api.openai.com` AVEC une clé littérale
  (valeur ne commençant pas par `${`) → les violations incluent l'hôte fournisseur ET la clé en
  clair (≥2 entrées ciblées).

## D4 — local.add_local : pas de nettoyage sur échec — sévérité ÉLEVÉ
Si `deploy()` ou `check_completion()` échoue après le téléchargement, le fichier reste sur
disque → viole « rien à demi-installé » (critère 4).
- **Critère** : toute exception après `download_verified` supprime le fichier téléchargé avant
  de propager (fail-fast propre, rien à demi-installé).
- **Test** : `deploy` échoue (runner code≠0) → le fichier `.bin` est absent après l'exception.

## D5 — local UrllibFetcher.fetch : urlopen sans timeout — sévérité moyen
Un serveur muet bloque le worker indéfiniment.
- **Critère** : `fetch` accepte/impose un `timeout` (défaut raisonnable, ex. 300 s) passé à `urlopen`.
- **Test** : la signature/appel passe un timeout (vérifiable par injection/inspection).

## D6 — local.download_verified : model.name non sanitizé (path traversal) — sévérité moyen
`model.name` concaténé au chemin sans contrôle → `../` peut écrire hors `dest_dir`.
- **Critère** : rejeter/neutraliser tout `model.name` contenant un séparateur de chemin ou `..`
  (le fichier résolu DOIT rester sous `dest_dir`).
- **Test** : `model.name="../evil"` → `LocalModelError` (ou chemin contraint sous dest_dir), pas
  d'écriture hors `dest_dir`.

## Portée & gates
Fichiers : `src/forgeai/models/{vault,strategy,gateway,local}.py` + tests associés. Ne PAS
toucher au comportement conforme existant. Gates : `python3 -m pytest -q` vert,
`python3 scripts/no_stub_scan.py --all` (après `git add`). Sortie attendue : `PREUVE:` avec
compte de tests + résultat, ou `BLOCKED:` avec raison.
