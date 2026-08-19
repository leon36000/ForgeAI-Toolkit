# AUDIT-WEB #589 — Ne jamais tenir le verrou de déploiement pendant les écritures SSE bloquantes

## Constat vérifié (ne pas re-dériver)

`src/forgeai/web/server.py::ForgeAIHandler._deploy_events_stream()` (lignes 1100-1126) exécute
`self.wfile.write(...)` et `self.wfile.flush()` **à l'intérieur** du bloc
`with _DEPLOY_STATE["lock"]:` (ouvert ligne 1103). `_deploy_resume()` (ligne 187, source de
`/api/status`) acquiert le **même** `threading.Lock()` (non réentrant, `_DEPLOY_STATE["lock"]`)
pour lire l'état. Un client SSE lent (backpressure réseau, socket bloquant) qui ralentit
`self.wfile.write()` retient donc le verrou, bloquant `_deploy_resume()` — et par extension
`/api/status` et tout autre lecteur de `_DEPLOY_STATE` — pendant toute la durée du blocage
réseau, potentiellement indéfiniment.

Vérifié empiriquement AVANT cette story (ROUGE reproduit) : un faux `wfile.write()` bloquant
(simulant un client SSE lent) fait `_deploy_resume()` échouer à terminer sous 1 seconde
pendant que le stream reste bloqué en écriture — confirmé via un thread `_deploy_events_stream`
et un thread `_deploy_resume()` concurrents, `wfile` remplacé par un faux objet dont `write()`
attend un événement.

## Livrable attendu

### `src/forgeai/web/server.py`

Remplacer EXACTEMENT ce bloc (méthode `_deploy_events_stream`) :
```python
    def _deploy_events_stream(self) -> None:
        idx = 0
        while True:
            with _DEPLOY_STATE["lock"]:
                lines = _DEPLOY_STATE["lines"]
                done = _DEPLOY_STATE["done"]
                exit_code = _DEPLOY_STATE["exit_code"]
                nettoyage_incertain = _DEPLOY_STATE["nettoyage_incertain"]
                while idx < len(lines):
                    try:
                        self.wfile.write(f"data: {lines[idx]}\n\n".encode("utf-8"))
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        return
                    idx += 1
                if done:
                    fin = {"exit_code": exit_code}
                    if nettoyage_incertain:
                        fin["nettoyage_incertain"] = True
                    payload = json.dumps(fin, ensure_ascii=False)
                    try:
                        self.wfile.write(f"event: end\ndata: {payload}\n\n".encode("utf-8"))
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                    return
            time.sleep(0.2)
```
par :
```python
    def _deploy_events_stream(self) -> None:
        # #589 : le verrou protège UNIQUEMENT la capture d'un instantané cohérent de
        # _DEPLOY_STATE — jamais l'E/S réseau. Un client SSE lent (backpressure) qui
        # ralentit self.wfile.write() retenait auparavant le verrou, bloquant
        # _deploy_resume() (/api/status) et le thread _reader pendant toute la durée du
        # blocage réseau. `list(...)` copie la liste : un `.clear()` concurrent (nouveau
        # déploiement démarré pendant qu'on écrit encore l'ancien flux) ne peut plus
        # corrompre l'itération en cours, contrairement à une référence directe.
        idx = 0
        while True:
            with _DEPLOY_STATE["lock"]:
                lines = list(_DEPLOY_STATE["lines"])
                done = _DEPLOY_STATE["done"]
                exit_code = _DEPLOY_STATE["exit_code"]
                nettoyage_incertain = _DEPLOY_STATE["nettoyage_incertain"]
            while idx < len(lines):
                try:
                    self.wfile.write(f"data: {lines[idx]}\n\n".encode("utf-8"))
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    return
                idx += 1
            if done:
                fin = {"exit_code": exit_code}
                if nettoyage_incertain:
                    fin["nettoyage_incertain"] = True
                payload = json.dumps(fin, ensure_ascii=False)
                try:
                    self.wfile.write(f"event: end\ndata: {payload}\n\n".encode("utf-8"))
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass
                return
            time.sleep(0.2)
```
Propriétés garanties (ne PAS en dévier) : (a) le verrou est acquis UNIQUEMENT pour capturer
`lines`/`done`/`exit_code`/`nettoyage_incertain`, jamais pendant `wfile.write`/`flush` ; (b)
`lines = list(_DEPLOY_STATE["lines"])` (copie), PAS une référence directe à la liste vivante —
un `.clear()` concurrent (nouveau déploiement) ne doit jamais pouvoir corrompre l'itération en
cours ; (c) l'ORDRE d'envoi des lignes et le comportement de fin (`event: end`) restent
identiques au caractère près ; (d) `_deploy_events_replay()` (méthode voisine, hors périmètre)
n'est PAS modifiée.

### `tests/test_web_deploy.py` (ajout uniquement, ne modifier aucun test existant)

Ajouter en tête de fichier les imports manquants (`time`, `types`), puis ces 2 tests à la fin
du fichier :

```python
class _WfileBloquant:
    """wfile factice : write() bloque jusqu'à ce que l'événement soit levé — simule un
    client SSE lent (backpressure) sans dépendre d'un vrai socket réseau."""
    def __init__(self, event_debloque):
        self.event_debloque = event_debloque
        self.ecrits = []

    def write(self, data):
        self.event_debloque.wait(timeout=5)
        self.ecrits.append(data)

    def flush(self):
        pass


def test_sse_ecriture_bloquante_ne_bloque_pas_deploy_resume():
    """#589 — reproduction exacte du défaut : _deploy_resume() (/api/status) doit terminer
    rapidement MÊME si le flux SSE est encore bloqué en écriture réseau."""
    with _DEPLOY_STATE["lock"]:
        _DEPLOY_STATE["proc"] = None
        _DEPLOY_STATE["lines"] = ["etape 1"]
        _DEPLOY_STATE["done"] = True
        _DEPLOY_STATE["exit_code"] = 0
        _DEPLOY_STATE["nettoyage_incertain"] = False

    event_debloque = threading.Event()
    fake_self = types.SimpleNamespace(wfile=_WfileBloquant(event_debloque))

    thread_stream = threading.Thread(
        target=srv_mod.ForgeAIHandler._deploy_events_stream, args=(fake_self,), daemon=True
    )
    thread_stream.start()
    time.sleep(0.2)  # laisse le stream entrer dans write() (bloqué)

    resume_termine = threading.Event()
    resultat = {}

    def _appeler_resume():
        resultat["valeur"] = srv_mod._deploy_resume()
        resume_termine.set()

    thread_resume = threading.Thread(target=_appeler_resume, daemon=True)
    thread_resume.start()

    try:
        assert resume_termine.wait(timeout=1.0), (
            "_deploy_resume() est resté bloqué par le verrou SSE"
        )
        assert resultat["valeur"]["done"] is True
    finally:
        event_debloque.set()
        thread_stream.join(timeout=5)
        thread_resume.join(timeout=5)


def test_sse_stream_envoie_toutes_les_lignes_et_termine(fake_deploy):
    """Non-régression : le contenu et l'ordre du flux SSE restent inchangés après le
    déplacement de l'écriture hors du verrou (même scénario que test_deploy_et_sse)."""
    with _DEPLOY_STATE["lock"]:
        _DEPLOY_STATE["proc"] = None
        _DEPLOY_STATE["lines"] = ["ligne 1", "ligne 2", "ligne 3"]
        _DEPLOY_STATE["done"] = True
        _DEPLOY_STATE["exit_code"] = 0
        _DEPLOY_STATE["nettoyage_incertain"] = False

    fake_self = types.SimpleNamespace(wfile=_WfileBloquant(threading.Event()))
    fake_self.wfile.event_debloque.set()  # jamais bloqué dans ce test

    srv_mod.ForgeAIHandler._deploy_events_stream(fake_self)

    sortie = b"".join(fake_self.wfile.ecrits).decode("utf-8")
    assert "data: ligne 1" in sortie
    assert "data: ligne 2" in sortie
    assert "data: ligne 3" in sortie
    assert sortie.index("ligne 1") < sortie.index("ligne 2") < sortie.index("ligne 3")
    assert "event: end" in sortie
    assert '"exit_code": 0' in sortie
```

## Contraintes

- Ne PAS modifier `_deploy_resume()`, `_deploy_events_replay()`, `_lancer_deploiement`, ni
  aucune autre méthode.
- Ne PAS modifier `_DEPLOY_STATE`, ni le mécanisme de verrou lui-même.
- Ne PAS modifier `tests/test_web_deploy.py` au-delà de l'ajout des imports manquants et des
  2 tests (+ la classe `_WfileBloquant`).
- Zéro nouvelle dépendance.
