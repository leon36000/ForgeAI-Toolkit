# Story HEALTH-030 — le repli hérité du healthcheck Compose vise encore le port hôte

Tier: T2

<!-- Fiabilité opérationnelle : un healthcheck Docker qui ne peut jamais passer casse tout
`depends_on: condition: service_healthy` et toute supervision qui lit l'état Docker — pas de
paiement/secret prod/suppression/publication/engagement externe, donc NON irréversible.
⇒ T2 (3 vendors distincts, TDAD/TDD strict, human_required=False). -->

## 0. Filiation — risque déjà signalé, jamais couvert

`stories/HEALTH-029.md` §8 (« Reste à traiter, signalé explicitement (hors de ce correctif) ») :

> Le **repli hérité** (`:46`) construit toujours sa cible depuis le port hôte. Aucun test ne le
> couvrait, et il n'est plus atteint par les stacks livrées.

Vrai à l'écriture de HEALTH-029 (seules `ollama`/`vector-store`, sondées en `EXEC` déclaré,
étaient livrées par défaut). Faux dès qu'une brique de `deploy-specs.json` est ajoutée via
`extra_bricks`/`stack` (RAG durci, rerank...) : **aucune** de ces briques ne déclare `probe_type`,
donc **toutes** retombent sur ce repli non couvert.

## 1. État mesuré (signalé par Nathan, déploiement réel)

Stack RAG durci avec `text-embeddings-inference-tei` et `text-embeddings-inference-reranker` :

```
$ curl http://127.0.0.1:8100/health                        # depuis l'HÔTE
200 OK
$ docker inspect <conteneur> --format '{{json .State.Health.Log}}'
curl: (7) Failed to connect to 127.0.0.1:8100                # sonde DANS le conteneur
```

Conteneur étiqueté `unhealthy` en permanence bien que le service réponde correctement.

## 2. Cause racine

`planner/assemble.py` construit `healthcheck_url = f"http://127.0.0.1:{host_port}{health_path}"`
pour toute brique de `deploy-specs.json` sans `probe_type` déclaré (TEI, reranker, litellm,
redis, qdrant, immudb, postgres, langfuse, llama-cpp-vulkan, cpu-zendnn, intel-openvino — aucune
n'en déclare). `renderers/compose.py::_healthcheck_lines`, branche de repli (probe_type=None,
healthcheck_url renseigné), réutilisait cette URL **telle quelle** dans le `test:` du
`healthcheck:` Docker — or cette sonde s'exécute **dans** le conteneur, où seul `container_port`
est joignable. Même défaut D1 que HEALTH-029, sur le chemin de code que cette story-là avait
identifié mais explicitement laissé hors périmètre.

`renderers/k3s.py` n'a jamais ce défaut : son repli équivalent (`elif health_url:`) n'extrait que
le **chemin** de l'URL et cible toujours `container_port` — le kubelet exécute la sonde, jamais
le conteneur, donc le port hôte dans l'URL brute était déjà sans conséquence côté K3s.

## 3. TDD (ROUGE → VERT)

- **RED** — `tests/test_wizard_health.py::test_renderer_compose_repli_healthcheck_url_vise_le_port_conteneur` :
  `ServiceSpec(host_port=8100, container_port=80, healthcheck_url="http://127.0.0.1:8100/health")`
  (aucun `probe_type`) → sur le code d'avant correctif, `_healthcheck_lines` émettait
  `curl -fsS http://127.0.0.1:8100/health` (port hôte) ⇒ rouge, symptôme reproduit à l'identique.
- **Correctif** — `renderers/compose.py::_healthcheck_lines`, branche de repli : extraction du
  chemin via `urlsplit(healthcheck_url).path`, reconstruction avec `container_port`. Stratégie
  identique à celle déjà en place dans `renderers/k3s.py`. `healthcheck_url` lui-même **inchangé**
  (le consommateur hôte `deploy/compose.py` continue de sonder le port hôte, comme voulu).
- **GREEN** — le même test passe désormais.

## 4. Critères d'acceptation

- **CA1** le `test:` du bloc `healthcheck:` généré pour toute brique sans `probe_type` déclaré
  cible `container_port`, jamais `host_port`.
- **CA2** `healthcheck_url` (consommateur hôte, `deploy/compose.py`) reste inchangé — les deux
  points de vue restent servis séparément, comme établi par HEALTH-029 CA2.
- **CA3** rendu K3s inchangé ; suites `test_wizard_health.py`, `test_health029_sondes_executables.py`,
  `test_chassis_deploiement.py`, `test_openbao_unsealer_compose.py` vertes.
- **CA4** preuve d'exécution réelle via le pipeline complet (pas seulement le test unitaire) :
  `assemble_plan(profile="hardened", extra_bricks=(tei, reranker, litellm))` + `render_compose()`
  → YAML généré, sonde des deux bricks TEI vérifiée port-conteneur.
- **CA5** suite complète verte hors l'échec de collecte préexistant et non lié de
  `tests/test_data002b_wal_idempotent.py` (pollution d'environnement — paquet `tests` fantôme
  dans `~/.local/lib/python3.12/site-packages/tests/`, confirmé antérieur à ce correctif via
  `git stash`).

## 5. Preuve

| | Avant | Après |
|---|---|---|
| `test:` (TEI, host_port=8100, container_port=80) | `curl -fsS http://127.0.0.1:8100/health` | `curl -fsS http://127.0.0.1:80/health` |
| `pytest -q --ignore=tests/test_data002b_wal_idempotent.py` | — | 1920 passed, 7 skipped, 0 failed, exit 0 |
| `no_stub_scan.py --all` | — | OK, 330 fichiers, 0 violation |

Registre : `Registres/mission.jsonl` seq 422 (type=correction, story=HEALTH-030).

## 6. Reste à traiter, signalé explicitement (hors de ce correctif)

Le correctif est appliqué au niveau du renderer (racine commune) : il couvre structurellement
**toutes** les briques de `deploy-specs.json` sans `probe_type` déclaré, pas seulement TEI/reranker.
Mais seul le cas signalé (TEI/reranker) a un test nommé qui l'exerce explicitement ; les autres
(litellm, redis, qdrant, immudb, postgres, langfuse, llama-cpp-vulkan, cpu-zendnn, intel-openvino)
n'ont pas de test individuel dans cette passe. Une déclaration explicite de `probe_type` par brique
(à la manière de HEALTH-029 pour `ollama`/`vector-store`) resterait la couverture la plus forte —
non faite ici pour rester chirurgical sur le défaut signalé.
