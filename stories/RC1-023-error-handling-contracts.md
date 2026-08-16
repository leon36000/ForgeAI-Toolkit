# RC1-023 — Contractualiser les handlers d'erreur à haut risque (lot 1/N)

Issue : #452 (campagne RC1, vague 2, orchestrée par #481). Priorité P2_HIGH, reliability.
Dépend de #430 (DONE).

## Problème (issue #452)

Le scan AST a relevé des captures larges et des handlers silencieux dans `src/forgeai/`.
Plusieurs sont intentionnels et ne doivent pas être convertis automatiquement en bugs — mais
chaque site à haut risque doit posséder un contrat observable (disposition explicite, pas
d'exception avalée sans trace).

## Mesure (reconnaissance, cette story)

182 blocs `except` réels dans `src/forgeai/` (comptage AST indépendant). Répartition par
comportement du corps du handler : 87 `return_default`, 42 `re_raise` (déjà conformes — la cause
est propagée, pas « avalée »), 29 `autre`, 18 `pass`, 6 `continue`.

## Scope de ce lot (1/N — campagne à la RC1-010/#440)

**Les 24 sites `pass`/`continue`** — les handlers les plus silencieux, cœur du problème décrit
par l'issue — **+ 1 site adjacent** découvert en traitant l'un d'eux (`web/server.py:1517`, même
fonction que le site `1523` déjà dans le lot, cause racine du même échec de thread). Triage réel
site par site (lecture du code, pas de classification automatique) :
- **16 JUSTIFIED** : comportement déjà correct et documenté (idiomes de nettoyage POSIX,
  boucles de parsing défensif à faible risque, motifs de scrutation, dégradation déjà
  contractualisée). Aucun changement de code.
- **9 FIXED** : dégradation silencieuse réelle sur des chemins sécurité/persistance/déploiement/
  rollback (ex. constat d'audit L07-002 : deux `except Exception: pass` avalaient des échecs de
  persistance de l'état de déploiement sans aucune trace). Correctif MINIMAL : rendre la
  dégradation visible (stderr ou ligne d'avertissement dans le flux de déploiement, selon le
  contexte), **aucun changement de comportement fonctionnel préexistant**.

Les 158 sites restants (`autre`, `return_default`, contrats docstring légers sur `re_raise`)
sont hors scope de ce lot — `governance/error-handling-contracts.json::coverage.note` documente
le plan des lots suivants.

## Livrables

1. `governance/error-handling-contracts.json` — inventaire machine des 25 sites (site, exception
   attendue, comportement, journalisation, propriétaire, justification, test compensatoire ou
   raison d'absence, échéance de révision à 180 jours, disposition).
2. `scripts/governance/validate_error_contracts.py` — validateur stdlib : schéma complet,
   plancher de couverture (`coverage.floor`), dates de révision, XOR test/raison, FIXED exige un
   test réel, **dérive AST** (le site existe toujours à la ligne indiquée, le type d'exception
   n'a pas changé) — sur les 25 sites inventoriés uniquement, pas sur les 157 autres (couverture
   volontairement progressive, pas un remplacement mécanique de tous les `except`).
3. `governance/ERROR-HANDLING-CONTRACTS.md` — rapport généré (`--render`).
4. `.github/workflows/error-handling-contracts.yml` — gate CI (validation + détection de
   mutation : un site déplacé doit faire échouer le gate).
5. 9 correctifs minimaux (sites FIXED) + 9 tests d'injection de faute prouvant (a) le nouveau
   signal apparaît, (b) le comportement observable préexistant est inchangé.
6. `manifests/roles.yaml` — 2 entrées ajoutées (`kimi-k3`, `gemini-3.7-flash`) : roster codeur
   périmé découvert en construisant le reçu D9 de cette story (vendors vérifiés à la source via
   `/v1/model/info`), bloquant pour toute lane utilisant `crew_dispatch.py --difficulty` — signalé
   sur #481.

## Critères de validation

- [x] `pytest` — suite complète verte (2224 tests collectés, 0 échec ; régression confirmée sur
      les fichiers modifiés ET sur l'ensemble du dépôt).
- [x] `python3 scripts/no_stub_scan.py --all` — 0 violation.
- [x] `python3 scripts/governance/validate_error_contracts.py --root . --render` — OK.
- [x] Mutation locale (site déplacé) → gate détecte "site introuvable" (vérifié en local avant
      CI).
- [x] Aucun changement de comportement observable sur les 9 sites FIXED (prouvé par les tests
      d'injection de faute : valeur de retour / absence d'exception propagée inchangée).
- [ ] Revue aveugle scellée 3 vendors distincts, APPROVE 3/3.
