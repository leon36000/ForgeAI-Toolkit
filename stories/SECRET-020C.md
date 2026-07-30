# SECRET-020C — Preuve d'import réel de `openbao_flow` sur la matrice CI 3 OS

## Contexte

Suite directe de SECRET-020B (PR #292, mergée le 2026-07-30). SECRET-020B a introduit
un import conditionnel de `grp` (POSIX-only) dans `src/forgeai/deploy/openbao_flow.py`,
sur le modèle de PORT-286, avec repli documenté quand `grp` est absent (Windows) :
`resolve_openbao_gid()` renvoie `None` et tous les appelants basculent sur le comportement
historique prouvé e2e S6.

Trois revues aveugles scellées successives ont relevé la MÊME objection MINEURE
(DeepSeek tour 1, Gemini tours 2 et 3, archivée dans
`reviews/SECRET-020B-t3/Gemini-3.1-Pro-OR.verdict.json`, sévérité `mineure`, verdict
APPROVE) : la portabilité de l'import conditionnel est prouvée par monkeypatch sous Linux
(`tests/test_openbao_flow.py::test_resolve_openbao_gid_none_sans_grp`) + audit AST, MAIS
`openbao_flow.py` n'est PAS exécuté dans la matrice CI multi-OS `guard-fs-multi-os` — qui
ne lance que `test_guard_fs.py`, `test_portable_lock.py`, `test_registre_concurrence.py`.
Contrairement au verrou `msvcrt` de PORT-286, qui tourne sur `windows-latest` réel via
`test_portable_lock.py`, la portabilité de `openbao_flow` n'a jamais d'exécution réelle
hors Linux.

C'est une amélioration de NIVEAU DE PREUVE (le code est correct et déjà mergé), pas un
défaut : elle transforme « portabilité prouvée par mock Linux » en « import réel prouvé
sur runners Windows/macOS ».

## Décision

1. Ajouter `tests/test_openbao_flow_import.py` — un test d'import PUR :
   - importe `forgeai.deploy.openbao_flow` et appelle `resolve_openbao_gid()` ;
   - n'importe RIEN hors stdlib + le module sous test (interdit : `yaml` et le reste de la
     chaîne de `tests/test_openbao_flow.py`), afin de rester dans le mandat étroit du job
     `guard-fs-multi-os` qui n'installe que `pytest` ;
   - assertions renforcées par-OS (voir Critères d'acceptation).
2. Câbler ce fichier dans la ligne `run:` du job `guard-fs-multi-os` de
   `.github/workflows/gates.yml`, aux côtés des trois fichiers existants.

Invariant préservé : `import forgeai.deploy.openbao_flow` tire tout le graphe
`deploy → compose → core` (le `__init__` de `deploy` importe `compose` de façon eager),
graphe prouvé stdlib-pur (aucun paquet tiers). L'ajout ne peut donc pas faire échouer le
job qui n'installe que `pytest`. Résolution de `forgeai` : assurée par
`pythonpath = ["src", "scripts"]` déjà présent dans `[tool.pytest.ini_options]`
(`pyproject.toml`), comme pour `test_portable_lock.py`.

## Critères d'acceptation

- [ ] `test_openbao_flow_import` : `import forgeai.deploy.openbao_flow` réussit ;
      `gid = resolve_openbao_gid()` ; `assert gid is None or isinstance(gid, int)`.
- [ ] Jambe Windows (`os.name == "nt"`) : `assert flow.grp is None` ET `assert gid is None`
      — repli réel prouvé sur le runner Windows (cœur de l'objection récurrente).
- [ ] Jambe POSIX (`os.name != "nt"`, Linux/macOS) : `assert flow.grp is not None`
      — assertion non-tautologique côté POSIX (le module `grp` y est présent).
- [ ] Le fichier n'importe aucun paquet non-stdlib : l'import réussit sous `python3 -S`
      (site-packages désactivé) et avec `pip install pytest` seul.
- [ ] `guard-fs-multi-os` liste `tests/test_openbao_flow_import.py` et reste vert sur
      `ubuntu-latest`, `macos-latest` et `windows-latest`.
- [ ] Aucune duplication du masquage `grp` déjà couvert Linux par
      `test_resolve_openbao_gid_none_sans_grp` : la valeur ajoutée est l'exécution réelle
      multi-OS, pas un second mock.

## Preuves associées

- [ ] Preuve d'isolation locale : `import forgeai.deploy.openbao_flow` sous `python3 -S`
      (contrôle : `import yaml` y échoue par `ModuleNotFoundError`) → succès, et
      énumération du diff `sys.modules` = « third-party modules pulled: NONE (stdlib-pure) ».
- [ ] Preuve CI définitive : le run `gates / guard-fs-multi-os (windows-latest)` de la PR
      passe au vert en exécutant le nouveau fichier (import réel, `grp` réellement absent).
      Preuve à VÉRIFIER sur la PR (`gh run`), jamais présumée.
- [ ] Dents du test : une régression vers `import grp` inconditionnel ferait échouer
      l'import sur `windows-latest` (grp absent) → le job vire au rouge. Démonstration
      locale par simulation (`grp` masqué + import inconditionnel en copie hors-dépôt).

## Portabilité (héritée de PORT-286 / SECRET-020B)

`grp` est POSIX-only ; son import reste conditionnel dans le code produit (inchangé par
cette story). Ce test AJOUTE la preuve d'exécution réelle sur les 3 OS ; il ne modifie
aucun code produit.

## Frontière T3

Aucune. Le test n'écrit rien, n'appelle aucun réseau, ne manipule aucun secret ni aucune
clé réelle. SECRET-020C n'est pas une nouvelle décision de sécurité mais une preuve CI
additive fermant une objection `mineure` récurrente. Tier T1.
