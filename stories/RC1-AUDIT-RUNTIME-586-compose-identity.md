# AUDIT-RUNTIME #586 — Identité de projet Docker Compose unifiée du rendu au health-check

## Constat vérifié (ne pas re-dériver)

`src/forgeai/renderers/compose.py::render_compose()` (ligne 145) écrit toujours
`name: forgeai-minimal` dans le YAML rendu (paramètre `project` avec une valeur par défaut
codée en dur, JAMAIS dérivée du plan). `src/forgeai/deploy/compose.py::_etats_docker()`
(ligne 132) interroge `docker compose -p <plan.plan_id> ps` — une identité DIFFÉRENTE,
puisque `plan.plan_id` est un UUID (`f"p1-{uuid.uuid4().hex[:8]}"`,
`src/forgeai/planner/assemble.py:239`), jamais égal à `"forgeai-minimal"`.

Traçage complet des appelants (aucun autre site à modifier) :
- `render_compose` : appelé UNE SEULE fois, `src/forgeai/cli.py:338`
  (`compose_file.write_text(render_compose(plan), ...)`), toujours sans second argument
  → toujours le défaut codé en dur.
- `compose_up`/`compose_down` (`src/forgeai/deploy/compose.py`) : appellent
  `docker compose -f <fichier> <args>` SANS `-p` — Docker Compose résout alors l'identité du
  projet depuis le champ `name:` du fichier rendu (comportement documenté et stable de
  Compose V2 : priorité `-p` > `COMPOSE_PROJECT_NAME` > `name:` du fichier > nom du
  répertoire). Corriger `render_compose` suffit donc à aligner `up`/`down` SANS toucher leur
  signature.
- `_etats_docker` (santé, lue par `wait_healthy`) : déjà correcte structurellement
  (`plan.plan_id`), juste désynchronisée du rendu.

Vérifié empiriquement AVANT cette story (ROUGE reproduit) : deux plans distincts
(`plan_a.plan_id="p1-aaaaaaaa"`, `plan_b.plan_id="p1-bbbbbbbb"`) produisent CHACUN
`name: forgeai-minimal` — collision confirmée, pas seulement un désaccord render/health-check
mais aussi une collision RÉELLE entre deux déploiements concurrents.

## Livrable attendu

### `src/forgeai/renderers/compose.py`

Remplacer EXACTEMENT cette ligne :
```python
def render_compose(plan: DeploymentPlan, project: str = "forgeai-minimal") -> str:
```
par :
```python
def render_compose(plan: DeploymentPlan, project: str | None = None) -> str:
    # #586 : l'identité de projet Compose DOIT dériver de plan.plan_id — un défaut codé en
    # dur ("forgeai-minimal") faisait collisionner tous les plans entre eux (rendu) ET
    # divergeait de `_etats_docker()` qui interroge déjà `-p plan.plan_id` (health-check).
    # `project` reste surchageable explicitement (tests, cas d'usage futurs), mais son défaut
    # est maintenant l'identité canonique du plan, jamais une constante.
    if project is None:
        project = plan.plan_id
```
Propriétés garanties (ne PAS en dévier) : (a) le paramètre `project` existe TOUJOURS et reste
surchageable — ne pas le supprimer ; (b) le reste du corps de la fonction (calcul de `lines`,
`f"name: {project}"` à la ligne `157`, tout ce qui suit) reste STRICTEMENT INCHANGÉ ; (c) ne
PAS toucher `_etats_docker`, `compose_up`, `compose_down`, ni aucun autre fichier —
`compose_up`/`compose_down` héritent automatiquement de la bonne identité via le champ `name:`
qu'ils lisent déjà dans le fichier rendu (aucune modification de signature nécessaire).

### `tests/test_renderers.py` (ajout uniquement, ne modifier aucun test existant)

Ajouter ces 4 tests à la fin du fichier, en réutilisant la fixture `_plan(gpu=True)` déjà
présente (accepte un `plan_id` optionnel — l'étendre si besoin sans changer son comportement
par défaut ni les tests existants qui l'appellent sans argument) :

```python
def test_compose_name_derive_du_plan_id():
    plan = _plan()
    out = render_compose(plan)
    assert f"name: {plan.plan_id}" in out
    assert "name: forgeai-minimal" not in out


def test_compose_deux_plans_identites_disjointes():
    plan_a = _plan()
    plan_b = DeploymentPlan(
        plan_id="p1-autre-plan", profile=plan_a.profile, target=plan_a.target,
        services=plan_a.services, model=plan_a.model, embed_model=plan_a.embed_model,
    )
    name_a = [l for l in render_compose(plan_a).splitlines() if l.startswith("name:")][0]
    name_b = [l for l in render_compose(plan_b).splitlines() if l.startswith("name:")][0]
    assert name_a != name_b


def test_compose_meme_plan_id_identite_stable():
    """Reprise sur état existant : re-rendre le MÊME plan (même plan_id) produit
    TOUJOURS la même identité — un `docker compose up` répété reconnecte la pile
    existante au lieu d'en créer une nouvelle sous un nom différent."""
    plan = _plan()
    name_1 = [l for l in render_compose(plan).splitlines() if l.startswith("name:")][0]
    name_2 = [l for l in render_compose(plan).splitlines() if l.startswith("name:")][0]
    assert name_1 == name_2


def test_compose_identite_rendu_correspond_a_celle_du_healthcheck():
    """Ferme la boucle rendu -> _etats_docker sans nécessiter de vrai daemon Docker :
    l'identité extraite du YAML rendu doit être EXACTEMENT celle que _etats_docker()
    interroge déjà via `-p str(plan.plan_id)` (#586)."""
    plan = _plan()
    name_line = [l for l in render_compose(plan).splitlines() if l.startswith("name:")][0]
    assert name_line == f"name: {plan.plan_id}"
```

## Contraintes

- Ne PAS modifier `src/forgeai/deploy/compose.py`, `src/forgeai/cli.py`, ni
  `src/forgeai/renderers/k3s.py` (son `NAMESPACE = "forgeai-minimal"` est un namespace K3s,
  concept séparé, hors périmètre de cette story Compose).
- Ne PAS modifier `_etats_docker`, `compose_up`, `compose_down` — déjà corrects/alignés
  automatiquement par le seul correctif de rendu.
- Ne PAS modifier les tests existants (`tests/test_renderers.py` et tout autre fichier) —
  aucun test existant n'asserte sur la valeur littérale du `name:` de niveau projet Compose
  (vérifié : les 6 occurrences de "forgeai-minimal" dans `tests/` concernent toutes le
  NAMESPACE K3s de `render_k3s`, jamais `render_compose`).
- Zéro nouvelle dépendance.
