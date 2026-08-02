# PORT-TESTPROC — `tests/test_proc.py` échoue sur tout chemin contenant un espace

- **Issue** : à ouvrir par le cockpit (Copilot) — ID définitif `PORT-<numéro>` avant merge.
- **Tier** : T1 (correctif de tests seuls ; aucune surface produit modifiée).
- **Dépend de** : CLI-036 (a créé `tests/test_proc.py`, issue #243).
- **Périmètre fichiers** : `tests/test_proc.py`, `stories/PORT-TESTPROC.md`.
- **Hors périmètre STRICT** : `src/forgeai/core/proc.py` — voir §3.

## 1. Problème (mesuré, non supposé)

`tests/test_proc.py` compose des chaînes de commande en interpolant `sys.executable` **sans
guillemets**, puis les passe à `timed_runner`, qui applique `shlex.split` (proc.py:41). Dès que le
chemin de checkout ou de venv contient un espace, `shlex.split` coupe l'interpréteur en deux.

```
$ python3 -c "import shlex; print(shlex.split('/media/pc1/Storage/Repo/ForgeAI Toolkit/.venv/bin/python'))"
['/media/pc1/Storage/Repo/ForgeAI', 'Toolkit/.venv/bin/python']
```

Reproduction, depuis un checkout dont le chemin contient un espace :

```
$ .venv/bin/python -m pytest tests/test_proc.py -q --deselect tests/test_proc.py::test_cancellation
FAILED tests/test_proc.py::test_kill_tree_real        - FileNotFoundError: [Errno 2] ... '/media/pc1/Storage/Repo/ForgeAI'
FAILED tests/test_proc.py::test_happy_path            - FileNotFoundError: [Errno 2] ...
FAILED tests/test_proc.py::test_timeout               - FileNotFoundError: [Errno 2] ...
FAILED tests/test_proc.py::test_timeout_none_short_step - FileNotFoundError: [Errno 2] ...
FAILED tests/test_proc.py::test_cli_loop_timeout      - assert 1 == 14
```

**6 tests cassent** (les 5 ci-dessus + `test_cancellation`, désélectionné ici pour la lisibilité).

Deux constats qui ne se voient pas dans un relevé naïf :

1. **`test_cli_loop_timeout` (l.214-215) est atteint mais invisible.** Il interpole `sys.executable`
   dans `--step`/`--until`, qui repartent dans `timed_runner`. Il échoue en `assert 1 == 14` : le
   `FileNotFoundError` est absorbé par la frontière d'erreurs CLI (CLI-013) et mappé sur le code 1
   au lieu du code timeout 14. Il n'apparaît pas dans un run complet parce que le `SIGINT` de
   `test_cancellation` avorte la session pytest avant qu'il ne soit atteint — **le bug masque une
   partie de ses propres symptômes**.
2. **Le défaut est confiné à ce fichier.** Suite complète relancée depuis le chemin espacé :
   `tests/test_proc.py` est le seul fichier en échec. Les autres usages de `sys.executable`
   (`test_web_deploy.py`, `test_deploy_reel.py`, `test_registre_concurrence.py`,
   `web/server.py`) passent une **liste** à `Popen` — immunisés par construction, aucune
   analyse shell n'a lieu.

**Lignes fautives** : 61, 75, 86, 104, 146, 214, 215.

## 2. Directive applicable

« Universel, pas ma config » : le logiciel doit fonctionner pour n'importe qui, y compris sous
`C:\Program Files\ForgeAI` ou `/home/me/My Projects/`. Un test qui ne passe que sur un chemin sans
espace n'est pas une preuve — c'est une preuve conditionnée à la config du développeur.

## 3. Décision : corriger les tests, PAS `proc.py`

`shlex.split` dans `timed_runner` est le **comportement voulu**, pas le défaut. Son API publique
reçoit une commande *tapée par l'utilisateur* via `forgeai loop --step "..."` : une chaîne de shell,
dont l'analyse POSIX est le contrat. Le devoir de citer ses arguments incombe à l'**appelant**.
Les tests sont ici des appelants fautifs qui ne respectent pas ce contrat.

Modifier `proc.py` (p. ex. tenter `Path(cmd).exists()` avant de découper) casserait des commandes
légitimes et transformerait un contrat clair en heuristique. Rejeté.

> Note : le `skipif` de `posix_only` (l.20-27) consigne un écart distinct — la portabilité **Windows**
> de l'analyse de commande de `proc.py`. Cet écart reste ouvert et hors périmètre ici ; il ne
> concerne pas les espaces, qui sont un défaut d'appelant sur toutes les plateformes.

## 4. Correctif

Constante de module pour l'interpréteur (7 sites), `shlex.quote` en ligne pour les chemins
`tmp_path` qui varient par test :

```python
PY = shlex.quote(sys.executable)
...
cmd = f"{PY} {shlex.quote(str(script))} {shlex.quote(str(orphan_pid_file))}"
ret = runner(f'{PY} -c "exit(0)"')
```

*Justif de la constante* : point de vérité unique. Le prochain test écrit réutilise `PY`
naturellement, ce qui rend la régression structurellement plus difficile à réintroduire qu'avec
`shlex.quote(sys.executable)` recopié sept fois.

## 5. Preuve de non-régression (deux couches)

Une couche seule est insuffisante — l'e2e ne tourne pas partout, l'unitaire ne démarre aucun process.

**Couche 1 — unitaire, universelle (tourne sur toute plateforme, Windows inclus).**
Compose la commande avec des chemins synthétiques espacés (dont une forme
`C:\Program Files\...`) et vérifie le round-trip : `shlex.split(cmd)[0]` rend le chemin **intact**.
C'est la garde qui échoue si quelqu'un réintroduit l'interpolation nue, y compris là où le
symlink est indisponible.

**Couche 2 — e2e POSIX, exécution réelle.**
Symlink de l'interpréteur dans `tmp_path/"dir with space"/"py thon"`, passé au **vrai**
`timed_runner`, avec un code de sortie non trivial pour prouver que le process a réellement tourné.
Faisabilité vérifiée avant conception : l'interpréteur résout son `prefix` à travers le symlink et
démarre normalement. `pytest.skip` explicite si le symlink est refusé (Windows sans mode
développeur) — jamais un échec silencieux.

## 6. Critères d'acceptation (testables)

1. Les **6** tests passent depuis un checkout dont le chemin contient un espace.
2. Les 6 tests passent aussi depuis un chemin **sans** espace (non-régression).
3. `shlex.quote` est appliqué à **toute** interpolation de chemin dans les chaînes de commande du
   fichier — plus aucune interpolation nue de `sys.executable`, `script` ou `orphan_pid_file`.
4. La couche 1 échoue (RED démontré) si l'on retire `shlex.quote` de la composition.
5. `src/forgeai/core/proc.py` est **inchangé** (`git diff` vide sur ce fichier).
6. Gates verts : `pytest`, `python3 scripts/no_stub_scan.py --all`.
7. Revue aveugle scellée APPROVE 3/3, 3 vendors distincts ≠ vendor du codeur.

## 7. Cousin signalé, délibérément exclu

`src/forgeai/ide/guard_fs.py:593` compose `f'"{python}" "{script_path}"'` — guillemets naïfs.
Résiste aux espaces mais casse sur un chemin contenant `"` ou `$`. Défaut **différent** (code
produit, consommé par le shell des hooks Claude Code, pas par `shlex.split`) et déjà exclu
explicitement par `PORT-286` (« Hors périmètre : `ide/guard_fs.py` (contrat assumé, inchangé) »).
Story séparée requise — ne pas l'embarquer ici.
