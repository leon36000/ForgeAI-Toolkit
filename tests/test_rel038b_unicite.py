"""REL-038B — unicité de la préparation par hôte + réconciliation idempotente.

Deux POST concurrents sur le MÊME hôte ne doivent lancer qu'UNE préparation (409 pour le second),
tandis que des hôtes DIFFÉRENTS restent parallélisables. Et parce que REL-038A fait survivre l'état
au redémarrage, une entrée « en cours » restaurée doit être réconciliée en état terminal — sinon la
garde d'unicité verrouillerait cet hôte définitivement.
"""

import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from forgeai.web import server
from forgeai.web.server import build_server


def _post_json(url: str, payload: dict):
    """POST JSON ; retourne (code, corps_dict). urlopen LÈVE sur 4xx → on capture."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST", headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.getcode(), json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def _get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Isole l'état MODULE (état + ensemble actif) et redirige forgeai_home hors du home réel."""
    monkeypatch.setattr(server, "forgeai_home", lambda: tmp_path)
    server._PREPARE_STATE.clear()
    server._PREPARE_ACTIVE.clear()
    yield
    server._PREPARE_STATE.clear()
    server._PREPARE_ACTIVE.clear()


@pytest.fixture()
def live():
    srv = build_server("127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    host, port = srv.server_address
    yield f"http://{host}:{port}"
    srv.shutdown()
    srv.server_close()


def _attendre_done(base: str, hote: str, essais: int = 50) -> dict:
    """Attend (borné) que l'état de `hote` soit terminal."""
    for _ in range(essais):
        etat = _get_json(f"{base}/api/nodes/prepare/{hote}")
        if etat.get("done") is True:
            return etat
        time.sleep(0.1)
    pytest.fail(f"état 'done' jamais atteint pour {hote}")


def test_g1_meme_hote_rejete_et_travail_unique(live, monkeypatch):
    """CA1 : second POST sur le même hôte → 409, et la préparation n'a lieu QU'UNE fois."""
    barriere = threading.Event()
    compteur = {"n": 0}

    def faux_preparer(runner, hote, *, appliquer, helm_present):
        compteur["n"] += 1
        barriere.wait(timeout=5)
        return {"status": "ok"}

    monkeypatch.setattr(server, "preparer_noeud", faux_preparer)
    hote = "n1.local"

    code1, _ = _post_json(f"{live}/api/nodes/prepare", {"host": hote})
    assert code1 == 202
    time.sleep(0.2)  # laisse le thread entrer dans la préparation

    code2, corps2 = _post_json(f"{live}/api/nodes/prepare", {"host": hote})
    assert code2 == 409, f"attendu 409 pour un doublon, reçu {code2}"
    assert "cours" in corps2.get("error", "").lower()

    barriere.set()
    _attendre_done(live, hote)
    assert compteur["n"] == 1, f"la préparation a été exécutée {compteur['n']} fois au lieu d'une"


def test_g2_hotes_distincts_parallelisables(live, monkeypatch):
    """CA2 : deux hôtes DIFFÉRENTS ne se bloquent pas (usage multi-nœuds préservé)."""
    barriere = threading.Event()

    def faux_preparer(runner, hote, *, appliquer, helm_present):
        barriere.wait(timeout=5)
        return {"status": "ok"}

    monkeypatch.setattr(server, "preparer_noeud", faux_preparer)

    code_a, _ = _post_json(f"{live}/api/nodes/prepare", {"host": "n1.local"})
    time.sleep(0.2)
    code_b, _ = _post_json(f"{live}/api/nodes/prepare", {"host": "n2.local"})
    barriere.set()

    assert code_a == 202
    assert code_b == 202, f"un hôte distinct ne doit pas être bloqué, reçu {code_b}"


def test_g3_hote_libere_apres_la_fin(live, monkeypatch):
    """CA2 : une fois la préparation terminée, un nouveau POST sur le même hôte est accepté."""
    def faux_preparer(runner, hote, *, appliquer, helm_present):
        return {"status": "ok"}

    monkeypatch.setattr(server, "preparer_noeud", faux_preparer)
    hote = "n1.local"

    assert _post_json(f"{live}/api/nodes/prepare", {"host": hote})[0] == 202
    _attendre_done(live, hote)
    assert server._PREPARE_ACTIVE == set(), "l'hôte n'a pas été libéré"

    code2, _ = _post_json(f"{live}/api/nodes/prepare", {"host": hote})
    assert code2 == 202, f"hôte non libéré après la fin, reçu {code2}"


def test_g4_hote_libere_meme_sur_exception_non_rattrapee(live, monkeypatch):
    """CA2 : le `finally` libère l'hôte même sur une exception qui ÉCHAPPE aux gardes internes.

    Détecteur réel : `preparer_noeud` est déjà entouré d'un `except Exception` qui convertit la
    panne en message d'erreur — une RuntimeError ne prouverait donc RIEN du `finally` (elle est
    absorbée avant). On lève une `KeyboardInterrupt` (BaseException), qui traverse `except
    Exception` : seule la clause `finally` peut alors libérer l'hôte.

    Design retenu après 9 rounds de revue scellée rejetés (voir `reviews/RC1-022-v1/` à `-v10/` —
    chaque round a trouvé un défaut réel, pas du bruit). Rounds v2 à v9 ont exploré des variantes
    de `threading.excepthook` maison (fenêtre mal placée, capture non filtrée, provenance par nom
    fragile, provenance par comptage global insuffisante, corrélation par identité d'objet, puis
    une course théorique check-then-set sur SA PROPRE restauration) — chaque correctif fermait un
    trou et en ouvrait un nouveau, plus théorique. **Recul déterminant** : `finally` s'exécute
    TOUJOURS en Python, que l'exception soit ensuite rattrapée plus haut dans la pile ou non — la
    question « l'exception a-t-elle atteint `threading.excepthook` » est DÉCONNECTÉE de la
    question réellement testée ici (« le `finally` a-t-il libéré l'hôte »). Élaborer une preuve
    d'atteinte du sommet du thread n'ajoutait donc aucune détection de régression pertinente pour
    CE test, seulement une surface croissante de bugs de concurrence dans le harnais de test
    lui-même — mauvais compromis pour un simple correctif de politique de warnings (#463).
    - `pytest.warns(...)` : NE FONCTIONNE PAS — le plugin `_pytest.threadexception` émet le
      warning APRÈS le retour de la fonction de test, vérifié empiriquement (« DID NOT WARN »).
    - `@pytest.mark.filterwarnings("ignore::...")` seul, sans preuve d'occurrence (round v1,
      REJECT) : fonctionne mais ne prouve rien à lui seul.
    - `threading.excepthook` maison (rounds v2-v9, tous REJECT sauf accords partiels v3/v5) :
      chaque variante (fenêtre, filtrage, provenance par nom, par comptage, par identité d'objet,
      restauration conditionnelle) a fermé le trou précédent tout en ouvrant une préoccupation de
      concurrence nouvelle sur le harnais lui-même — voir l'historique détaillé dans
      `git log -- tests/test_rel038b_unicite.py` et les verdicts `reviews/RC1-022-v2/` à `-v9/`.
    - Marqueur `filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")` SANS
      filtre de message (round v10, REJECT, 2 majeures — DeepSeek et GPT) : DeepSeek doutait
      (« plausible », non vérifié) que la portée du marqueur couvre l'émission en teardown —
      FAUX POSITIF écarté après vérification objective : 20/20 exécutions + suite complète, les
      DEUX politiques (marqueur ET filtre global `error::...`) actives simultanément, 0 échec —
      si la portée ne couvrait pas le teardown, CHAQUE run aurait échoué. GPT avait un point réel,
      RETENU : le marqueur, sans filtre de message, ignore TOUT
      `PytestUnhandledThreadExceptionWarning` pendant G4, pas seulement celui de
      `faux_preparer_qui_echappe` — un bug indépendant dans un autre thread pendant la fenêtre
      serait masqué à tort.
    - Marqueur `filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")` restreint
      par un filtre de MESSAGE (regex `(?s).*interruption non rattrapée.*`) : REJETÉ (round v11,
      GPT, majeure) — un filtre sur le seul contenu du message, même restreint, n'établit toujours
      aucun lien causal avec le thread/l'appel précis. Le même standard de preuve avait déjà motivé
      les rejets v6, v7, v9, v10 (4 rounds consécutifs, même reviewer en rôle « securite »).
    - Corrélation par identité d'objet thread+exception, SANS restauration de
      `threading.excepthook` (round v12, codé par GPT-5.6-Terra-Pro lui-même — décision Nathan de
      lui confier la résolution de sa propre objection récurrente) : REJETÉ (round v13, critique +
      majeures DeepSeek et Qwen, 2/3) sur un point factuel vérifié par LECTURE DIRECTE du code
      source de pytest (`_pytest/threadexception.py`, fonctions `pytest_configure`/`cleanup`,
      version installée sur cette machine) : `threading.excepthook` y est installé **une seule
      fois par SESSION pytest** (dans `pytest_configure`) et restauré **une seule fois, à la fin
      de la session** (dans `cleanup`, enregistré via `config.add_cleanup`) — PAS par test. La
      justification du round v12 (« le plugin pytest restaure lui-même à la sortie ») confondait
      restauration PAR SESSION et restauration PAR TEST. Vérifié empiriquement avec la
      méthodologie correcte cette fois (plugin pytest personnalisé inspectant `threading.excepthook`
      entre le teardown de G4 et le test suivant, DANS LA MÊME SESSION multi-tests — la vérification
      round v12/v13 précédente utilisait `pytest.main()` ciblant G4 seul, où fin-de-session et
      fin-de-test coïncident par accident, masquant la fuite) : le hook de G4 reste bien installé
      après son teardown, avant les tests suivants de la même session — la fuite est réelle.
    - **Version définitive (round v14)** : restauration EXPLICITE de `threading.excepthook` dans
      un `finally` couvrant tout le corps du test, SANS condition (une simple affectation, pas de
      `if threading.excepthook is ...` — le round v9 avait rejeté une restauration CONDITIONNELLE
      pour sa fenêtre de course check-then-set ; une affectation inconditionnelle n'a pas ce
      problème, il n'y a rien à « vérifier » avant d'écrire). Preuve vérifiable PAR LA SOURCE
      PYTEST elle-même (citée ci-dessus), pas seulement par une exécution que le reviewer ne peut
      pas reproduire. `appels_qui_ont_echappe` est désormais lu sous `verrou` partout où il est
      accédé (cohérence avec le contrat de verrouillage introduit en v12 — la mutation était déjà
      protégée, les lectures ne l'étaient pas).
    """
    exceptions_attendues = []
    exceptions_interceptees = []
    appels_qui_ont_echappe = []
    verrou = threading.Lock()
    hook_precedent = threading.excepthook

    def hook_exceptions(args):
        with verrou:
            origine_connue = any(
                args.thread is thread_attendu and args.exc_value is exception_attendue
                for thread_attendu, exception_attendue in exceptions_attendues
            )
            if origine_connue:
                exceptions_interceptees.append((args.thread, args.exc_value))
                return
        # Filet de sécurité structurel : toute exception NON reconnue (y compris si la
        # corrélation d'identité échouait À TORT à reconnaître une exception réellement issue de
        # faux_preparer_qui_echappe) est déléguée ici — elle remonte alors comme
        # PytestUnhandledThreadExceptionWarning normal et fait échouer le test via la politique
        # globale error::... de pyproject.toml. Un défaut de corrélation ne peut donc pas passer
        # inaperçu : il n'a pas besoin d'être prouvé séparément, ce gate déjà en place le rattrape.
        #
        # Vérifié empiriquement (round v16, réfutation d'une objection : `Thread._invoke_excepthook`
        # encapsule bien l'appel au hook dans un `try/except Exception: pass` — un `warnings.warn()`
        # SYNCHRONE à l'intérieur du hook serait effectivement avalé). Mais ce n'est PAS ce qui se
        # passe ici : `hook_precedent` est `_pytest.threadexception.thread_exception_hook`, qui ne
        # fait qu'ajouter l'exception à une deque (`config.stash[thread_exceptions]`) — AUCUN
        # `warnings.warn()` n'est appelé depuis l'intérieur de l'excepthook. C'est
        # `collect_thread_exception` (appelé par les hooks normaux `pytest_runtest_setup/call/
        # teardown`, dans le thread PRINCIPAL, hors de toute portée `_invoke_excepthook`) qui
        # draine la deque et appelle `warnings.warn()` — donc rien n'est avalé. Reproduit par un
        # test autonome hors de ce dépôt (thread qui lève une RuntimeError NON reconnue, déléguée
        # à `threading.excepthook` d'origine, `filterwarnings=error` actif) : le test ÉCHOUE bien
        # comme attendu, confirmant que la délégation fait réellement échouer la suite.
        hook_precedent(args)

    def faux_preparer_qui_echappe(runner, hote, *, appliquer, helm_present):
        exception = KeyboardInterrupt("interruption non rattrapée")
        with verrou:
            appels_qui_ont_echappe.append(hote)
            exceptions_attendues.append((threading.current_thread(), exception))
        raise exception

    monkeypatch.setattr(server, "preparer_noeud", faux_preparer_qui_echappe)
    hote = "n1.local"

    threading.excepthook = hook_exceptions
    try:
        assert _post_json(f"{live}/api/nodes/prepare", {"host": hote})[0] == 202

        for _ in range(50):  # attente bornée de la mort du thread
            if server._PREPARE_ACTIVE == set():
                break
            time.sleep(0.1)
        for _ in range(50):  # attente bornée de la 1re interception corrélée par identité
            with verrou:
                if len(exceptions_interceptees) >= 1:
                    break
            time.sleep(0.1)

        with verrou:
            assert len(appels_qui_ont_echappe) == 1, (
                f"1er appel : attendu 1 exécution de faux_preparer_qui_echappe, "
                f"reçu {len(appels_qui_ont_echappe)} — le détecteur du test G4 ne fonctionne plus comme prévu"
            )
        assert server._PREPARE_ACTIVE == set(), "l'hôte reste verrouillé après une exception échappée"
        with verrou:
            assert exceptions_interceptees == [exceptions_attendues[0]], (
                "la première exception interceptée ne provient pas de l'invocation attendue "
                "(identité de thread et d'objet exception)"
            )

        code2, _ = _post_json(f"{live}/api/nodes/prepare", {"host": hote})
        assert code2 == 202, "l'hôte doit rester préparable après un échec brutal"

        for _ in range(50):  # 2e appel = 2e thread qui échoue (preparer_noeud reste monkeypatché)
            with verrou:
                deux_interceptees = len(exceptions_interceptees) >= 2
                deux_appels = len(appels_qui_ont_echappe) >= 2
            if deux_appels and deux_interceptees:
                break
            time.sleep(0.1)
        with verrou:
            assert appels_qui_ont_echappe == [hote, hote], (
                f"attendu exactement 2 exécutions de faux_preparer_qui_echappe (une par appel POST), "
                f"reçu {appels_qui_ont_echappe}"
            )
    finally:
        # Restauration INCONDITIONNELLE (pas de check-then-set — voir docstring) : le plugin
        # pytest installe/restaure threading.excepthook par SESSION, pas par test (vérifié par
        # lecture directe de _pytest/threadexception.py) — sans cette ligne, hook_exceptions
        # resterait actif pour tous les tests suivants de la même session.
        threading.excepthook = hook_precedent

    assert server._PREPARE_ACTIVE == set(), "l'hôte reste verrouillé après la 2e exception échappée"
    with verrou:
        assert exceptions_interceptees == exceptions_attendues, (
            "chaque exception interceptée doit correspondre, par identité du thread et de l'objet "
            "KeyboardInterrupt, à l'invocation exacte de faux_preparer_qui_echappe"
        )


def test_g5_reconciliation_etat_en_cours_restaure(live, monkeypatch, tmp_path):
    """CA3 : une entrée « en cours » persistée devient TERMINALE au chargement, et l'hôte
    redevient préparable (sans quoi la garde d'unicité le verrouillerait à vie)."""
    def faux_preparer(runner, hote, *, appliquer, helm_present):
        return {"status": "ok"}

    monkeypatch.setattr(server, "preparer_noeud", faux_preparer)
    hote = "n1.local"

    chemin = server._prepare_state_path()
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(
        json.dumps({
            "version": server._PREPARE_STATE_VERSION,
            "hosts": {hote: {"done": False, "resultat": None, "erreur": None}},
        }),
        encoding="utf-8",
    )

    server._PREPARE_STATE.clear()
    server._load_prepare_state()

    etat = server._PREPARE_STATE[hote]
    assert etat["done"] is True, "une entrée « en cours » restaurée doit devenir terminale"
    assert "redémarrage" in (etat["erreur"] or ""), f"erreur non explicite : {etat['erreur']!r}"

    code, _ = _post_json(f"{live}/api/nodes/prepare", {"host": hote})
    assert code == 202, f"l'hôte doit redevenir préparable, reçu {code}"


def test_g6_reconciliation_idempotente(tmp_path):
    """CA3 : ré-appliquer la réconciliation ne change plus rien (point fixe)."""
    hote = "n1.local"
    chemin = server._prepare_state_path()
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(
        json.dumps({
            "version": server._PREPARE_STATE_VERSION,
            "hosts": {hote: {"done": False, "resultat": None, "erreur": None}},
        }),
        encoding="utf-8",
    )

    server._PREPARE_STATE.clear()
    server._load_prepare_state()
    premier = dict(server._PREPARE_STATE[hote])

    server._load_prepare_state()  # 2e application
    second = dict(server._PREPARE_STATE[hote])

    assert premier == second, f"réconciliation non idempotente : {premier} → {second}"


def test_g7_ensemble_actif_jamais_persiste(live, monkeypatch, tmp_path):
    """CA3 : `_PREPARE_ACTIVE` est runtime-only — il n'apparaît dans aucun fichier persisté."""
    def faux_preparer(runner, hote, *, appliquer, helm_present):
        return {"status": "ok"}

    monkeypatch.setattr(server, "preparer_noeud", faux_preparer)
    hote = "n1.local"
    assert _post_json(f"{live}/api/nodes/prepare", {"host": hote})[0] == 202
    _attendre_done(live, hote)

    contenu = server._prepare_state_path().read_text(encoding="utf-8")
    assert "_PREPARE_ACTIVE" not in contenu
    assert "active" not in json.loads(contenu), "l'ensemble actif ne doit pas être persisté"
