# AUDIT-WEB #587 — Erreur HTTP normalisée si le processus de déploiement ne démarre pas

## Constat vérifié (ne pas re-dériver)

`src/forgeai/web/server.py::ForgeAIHandler._lancer_deploiement()` (méthode appelée par
`_post_deploy`, elle-même appelée par `do_POST` pour la route `/api/deploy`) construit `cmd` puis
appelle `subprocess.Popen(cmd, **popen_kwargs)` (ligne ~1682) **à l'intérieur** du bloc
`with _DEPLOY_STATE["lock"]:`, **sans aucune frontière `try/except`**. Si `Popen` lève `OSError`
(exécutable absent, ressource processus/FD épuisée, permission refusée), l'exception remonte hors
du handler HTTP : le client ne reçoit ni `202` ni `500`, seulement une déconnexion brutale
(`http.client.RemoteDisconnected: Remote end closed connection without response`).

Vérifié empiriquement AVANT cette story (ROUGE reproduit sur le vrai code, avec un vrai
`ThreadingHTTPServer` via `build_server`, `subprocess.Popen` monkeypatché pour lever `OSError`) :
un `POST /api/deploy` valide (`stack=agentique`, `backend=compose`, `confirm=FORCER`) déclenche
exactement `http.client.RemoteDisconnected: Remote end closed connection without response` côté
client, avec la traceback serveur `do_POST → _post_deploy → _lancer_deploiement → subprocess.Popen`
— collision confirmée avec la reproduction de l'audit (#587).

**Piège de verrouillage à respecter absolument** : `_persist_deploy_state()` (ligne ~533) acquiert
elle-même `_DEPLOY_STATE["lock"]`, qui est un `threading.Lock()` **non réentrant** (ligne ~419).
L'appeler depuis l'intérieur du `with _DEPLOY_STATE["lock"]:` existant provoquerait un deadlock.
Le correctif ci-dessous respecte scrupuleusement cette contrainte : `_persist_deploy_state()`
reste appelée APRÈS la sortie du `with`, exactement comme le fait déjà le chemin de succès actuel.

## Livrable attendu

### 1. `src/forgeai/web/server.py`

Remplacer EXACTEMENT ce bloc (dans `_lancer_deploiement`, entre la construction de `popen_kwargs`
et la définition de `_reader`) :

```python
            new_proc = subprocess.Popen(cmd, **popen_kwargs)
            _DEPLOY_STATE["proc"] = new_proc

        _persist_deploy_state()

        def _reader() -> None:
```

par :

```python
            try:
                new_proc = subprocess.Popen(cmd, **popen_kwargs)
            except OSError as exc:
                # WEB-015 (#587) : un spawn qui échoue (exécutable absent, ressource système
                # épuisée, permission) ne doit jamais laisser le handler HTTP sans réponse ni
                # l'état de déploiement faussement « en cours » — aucun `_reader` n'existe alors
                # pour jamais marquer `done` à True.
                new_proc = None
                _DEPLOY_STATE["exit_code"] = -1
                _DEPLOY_STATE["done"] = True
                _DEPLOY_STATE["lines"].append(
                    "avertissement: échec du démarrage du processus de déploiement : "
                    f"{str_exc_sur(exc)}"
                )
            else:
                _DEPLOY_STATE["proc"] = new_proc

        _persist_deploy_state()

        if new_proc is None:
            self._send_json(500, {"error": "erreur interne lors du démarrage du déploiement"})
            return

        def _reader() -> None:
```

Propriétés garanties par cette construction (ne PAS en dévier) :
(a) le corps de `_reader` et tout ce qui suit (`threading.Thread(target=_reader,
daemon=True).start()`, `self._send_json(202, {"started": True})`) restent **STRICTEMENT
INCHANGÉS** — ne pas les recopier, ne pas les toucher ;
(b) `_persist_deploy_state()` reste appelée une seule fois, hors du `with`, qu'il y ait échec ou
succès du spawn — aucun risque de deadlock ;
(c) en cas d'échec, `_DEPLOY_STATE["proc"]` n'est jamais réassigné (reste `None` ou sa valeur
précédente, jamais un process invalide) ;
(d) `str_exc_sur` est déjà importé en tête de fichier (`from forgeai.core.safe_repr import
str_exc_sur`, ligne 31) — ne pas ajouter d'import.

### 2. `tests/test_web_deploy.py` (ajout uniquement, ne modifier aucun test existant)

Ajouter ces deux tests à la fin du fichier (après `test_non_regression`), en import-ant `forgeai.web.server`
comme module en tête de fichier (`from forgeai.web import server as srv_mod`, à ajouter avec les
imports existants) :

```python
def test_deploy_popen_echoue_renvoie_500_generique(server, fake_deploy, monkeypatch):
    def fake_popen(*a, **k):
        raise OSError("spawn impossible")

    monkeypatch.setattr(srv_mod.subprocess, "Popen", fake_popen)

    payload = json.dumps({"stack": "agentique", "backend": "compose", "confirm": "FORCER"}).encode("utf-8")
    status, body = _request(f"{server}/api/deploy", data=payload, method="POST")

    assert status == 500
    data = json.loads(body)
    assert "error" in data
    assert "spawn impossible" not in data["error"]  # WEB-015 : pas de détail interne au client

    with _DEPLOY_STATE["lock"]:
        assert _DEPLOY_STATE["proc"] is None
        assert _DEPLOY_STATE["done"] is True
        assert _DEPLOY_STATE["exit_code"] == -1


def test_deploy_popen_echoue_puis_nouveau_deploy_reussit(server, fake_deploy, monkeypatch):
    real_popen = srv_mod.subprocess.Popen

    def fake_popen(*a, **k):
        raise OSError("spawn impossible")

    monkeypatch.setattr(srv_mod.subprocess, "Popen", fake_popen)
    payload = json.dumps({"stack": "agentique", "backend": "compose", "confirm": "FORCER"}).encode("utf-8")
    status, _ = _request(f"{server}/api/deploy", data=payload, method="POST")
    assert status == 500

    # Ré-applique setattr (pas monkeypatch.undo()) : `fake_deploy` partage la même instance
    # `monkeypatch` (fixture function-scoped) et a déjà patché `_DEPLOY_CMD` — un `.undo()`
    # global annulerait aussi CE patch et ferait fuir la vraie commande wizard dans le test.
    monkeypatch.setattr(srv_mod.subprocess, "Popen", real_popen)
    status2, body2 = _request(f"{server}/api/deploy", data=payload, method="POST")
    assert status2 == 202
    assert json.loads(body2)["started"] is True
```

## Contraintes

- Ne PAS modifier `_valider_requete_deploy`, `_post_deploy`, `do_POST`, ni aucune autre route.
- Ne PAS modifier le corps de `_reader` ni le code après son appel (`threading.Thread(...)`,
  `self._send_json(202, ...)`) — ils restent identiques au caractère près.
- Ne PAS modifier `tests/test_web_deploy.py` au-delà de l'ajout des deux tests et de l'import
  `from forgeai.web import server as srv_mod`.
- Ne PAS modifier `_persist_deploy_state`, `_DEPLOY_STATE`, ni le mécanisme de verrou.
- Zéro nouvelle dépendance.
- Catch ciblé sur `OSError` (ce que `subprocess.Popen` documente lever pour un échec de spawn) —
  pas un `except Exception` générique qui masquerait des bugs sans rapport.
