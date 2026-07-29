"""Tests du module de gestion des budgets de tokens."""

import pytest

from forgeai.models.budget import BudgetError, BudgetState, BudgetTracker


def test_set_puis_record_accumule(tmp_path):
    tracker = BudgetTracker(tmp_path)
    tracker.set_budget("a", 1000)
    assert tracker.record("a", 100) == "OK"
    assert tracker.record("a", 100) == "OK"
    assert tracker.status("a").used_tokens == 200


def test_alerte_au_seuil(tmp_path):
    tracker = BudgetTracker(tmp_path)
    tracker.set_budget("a", 100, 0.8)
    assert tracker.record("a", 80) == "ALERTE"


def test_coupure_au_quota(tmp_path):
    tracker = BudgetTracker(tmp_path)
    tracker.set_budget("a", 100)
    assert tracker.record("a", 100) == "COUPURE"
    assert tracker.record("a", 50) == "COUPURE"


def test_agent_inconnu(tmp_path):
    tracker = BudgetTracker(tmp_path)
    with pytest.raises(BudgetError):
        tracker.record("x", 1)
    with pytest.raises(BudgetError):
        tracker.status("x")


def test_validation(tmp_path):
    tracker = BudgetTracker(tmp_path)
    with pytest.raises(BudgetError):
        tracker.set_budget("a", -1)
    with pytest.raises(BudgetError):
        tracker.set_budget("a", 100, alert_ratio=1.5)

    tracker.set_budget("a", 100)
    with pytest.raises(BudgetError):
        tracker.record("a", -5)


def test_persistance(tmp_path):
    tracker = BudgetTracker(tmp_path)
    tracker.set_budget("a", 1000)
    tracker.record("a", 123)

    tracker2 = BudgetTracker(tmp_path)
    assert tracker2.status("a").used_tokens == 123


def test_report(tmp_path):
    tracker = BudgetTracker(tmp_path)
    tracker.set_budget("beta", 200)
    tracker.set_budget("alpha", 100)
    tracker.record("beta", 50)
    tracker.record("alpha", 10)

    report = tracker.report()
    assert len(report) == 2
    assert [state.agent for state in report] == ["alpha", "beta"]
    assert all(isinstance(state, BudgetState) for state in report)
    assert report[0].used_tokens == 10
    assert report[1].used_tokens == 50


from forgeai.cli import main


def test_cli_budget_set_status(tmp_path, capsys):
    home = tmp_path
    registre_path = tmp_path / "r.jsonl"
    assert main(["budget", "set", "--agent", "coder", "--quota", "1000",
                 "--home", str(home), "--registre", str(registre_path)]) == 0
    assert main(["budget", "status", "--agent", "coder",
                 "--home", str(home)]) == 0
    captured = capsys.readouterr()
    assert "coder" in captured.out


def test_budgets_json_corrompu_leve_budgeterror(tmp_path):
    from forgeai.models.budget import BudgetTracker, BudgetError
    (tmp_path / "budgets.json").write_text("{ pas du json valide", encoding="utf-8")
    with pytest.raises(BudgetError) as exc:
        BudgetTracker(tmp_path).status("x")
    assert str(tmp_path / "budgets.json") in str(exc.value)


def test_set_budget_message_alert_ratio_reflete_intervalle(tmp_path):
    from forgeai.models.budget import BudgetTracker, BudgetError
    with pytest.raises(BudgetError) as exc:
        BudgetTracker(tmp_path).set_budget("a", 100, alert_ratio=1.5)
    assert "]0, 1]" in str(exc.value)


# --- B-20a : durcissement (verrou, QuotaAtteint, extraire_tokens) ---
# === Imports supplémentaires pour B-20a (cible 2) ===
import json
import multiprocessing as mp
from pathlib import Path

from forgeai.models.budget import (
    BudgetError,
    BudgetTracker,
    QuotaAtteint,
    extraire_tokens,
)


# ---------------------------------------------------------------------------
# 1. check() : agent OK -> None ; agent inconnu -> BudgetError
# ---------------------------------------------------------------------------
def test_check_agent_ok_et_inconnu(tmp_path):
    """check() ouvre le pré-dispatch quand l'agent est OK et refuse un inconnu."""
    tracker = BudgetTracker(tmp_path)
    tracker.set_budget("x", 1000)
    # Agent connu et sous quota : aucun signal, l'appel peut partir.
    assert tracker.check("x") is None
    # Agent non déclaré : BudgetError (saisie invalide), pas QuotaAtteint.
    with pytest.raises(BudgetError):
        tracker.check("inconnu")


# ---------------------------------------------------------------------------
# 2. check() après dépassement -> QuotaAtteint au message contractuel exact
# ---------------------------------------------------------------------------
def test_check_quota_atteint_message_exact(tmp_path):
    """Le message d'erreur est chiffré, agent et compteurs inclus."""
    tracker = BudgetTracker(tmp_path)
    tracker.set_budget("alpha", 100)
    tracker.record("alpha", 100)  # -> COUPURE

    with pytest.raises(QuotaAtteint) as exc:
        tracker.check("alpha")
    assert str(exc.value) == (
        "COUPURE: agent 'alpha' a dépassé son budget (100/100 tokens)"
    )


# ---------------------------------------------------------------------------
# 3. QuotaAtteint hérite de BudgetError (compatibilité handlers existants)
# ---------------------------------------------------------------------------
def test_quota_atteint_herite_de_budget_error():
    """Les handlers qui capturent BudgetError doivent aussi voir QuotaAtteint."""
    assert issubclass(QuotaAtteint, BudgetError)
    assert isinstance(QuotaAtteint("x"), BudgetError)


# ---------------------------------------------------------------------------
# 4. Concurrence réelle : deux trackers, ordre d'instanciation croisé
# ---------------------------------------------------------------------------
def test_concurrence_deux_trackers_meme_home(tmp_path):
    """tracker_b, créé AVANT le set_budget, ne doit pas écraser la valeur posée par A.

    Sans la relecture sous verrou à chaque opération, tracker_b.record()
    opérerait sur un état vide en mémoire et écraserait l'écriture de A.
    La relecture sous verrou garantit que la somme 100+50=150 est préservée
    quel que soit l'ordre d'instanciation.
    """
    tracker_a = BudgetTracker(tmp_path)
    tracker_b = BudgetTracker(tmp_path)  # créé AVANT set_budget

    tracker_a.set_budget("x", 1000)   # A pose le quota
    tracker_b.record("x", 100)        # B consomme 100
    tracker_a.record("x", 50)         # A consomme 50

    # Les deux instances voient le même total (le disque est l'unique vérité)
    assert tracker_a.status("x").used_tokens == 150
    assert tracker_b.status("x").used_tokens == 150

    # Et le fichier sur disque reflète bien 150 (pas 50, pas 100)
    on_disk = json.loads((tmp_path / "budgets.json").read_text(encoding="utf-8"))
    assert on_disk["x"]["used_tokens"] == 150


# ---------------------------------------------------------------------------
# 5. Concurrence multi-process : 4 process × 25 × 10 = 1000, sans perte
# ---------------------------------------------------------------------------
def _record_in_worker(home_str, agent, tokens, count, barrier):
    """Worker picklable : barrier pour aligner les départs, puis N records."""
    barrier.wait()
    tracker = BudgetTracker(Path(home_str))
    for _ in range(count):
        tracker.record(agent, tokens)


@pytest.mark.skipif(
    mp.get_start_method(allow_none=True) == "spawn",
    reason=("Ce test de concurrence inter-process requiert la méthode fork : il TOURNE en CI Linux "
            "(gate tests ; preuve B-20a au Registres/mission.jsonl) et ne skippe que sur une "
            "plateforme spawn-only où fork n'existe pas."),
)
def test_concurrence_multi_process(tmp_path):
    """4 process font chacun 25 record(x, 10) -> total final EXACTEMENT 1000."""
    tracker = BudgetTracker(tmp_path)
    tracker.set_budget("x", 2000)

    barrier = mp.Barrier(4)
    procs = [
        mp.Process(
            target=_record_in_worker,
            args=(str(tmp_path), "x", 10, 25, barrier),
        )
        for _ in range(4)
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=20)
        assert not p.is_alive(), "Un worker est resté bloqué."

    assert tracker.status("x").used_tokens == 1000


# ---------------------------------------------------------------------------
# 6. extraire_tokens : tous les formats reconnus et leurs cas de rejet
# ---------------------------------------------------------------------------
def test_extraire_tokens_openai_complet():
    """Usage OpenAI avec total_tokens entier -> (n, True)."""
    assert extraire_tokens({"usage": {"total_tokens": 42}}) == (42, True)


def test_extraire_tokens_ollama_complet():
    """Ollama avec prompt_eval_count + eval_count entiers -> (somme, True)."""
    assert extraire_tokens(
        {"prompt_eval_count": 10, "eval_count": 20}
    ) == (30, True)


def test_extraire_tokens_usage_sans_total_tokens():
    """usage présent mais total_tokens absent -> (0, False)."""
    assert extraire_tokens({"usage": {}}) == (0, False)
    assert extraire_tokens({"usage": {"prompt_tokens": 10}}) == (0, False)
    assert extraire_tokens({"usage": {"completion_tokens": 5}}) == (0, False)


def test_extraire_tokens_total_tokens_non_entier():
    """total_tokens d'un type non-entier (str, float, bool, None) -> (0, False)."""
    assert extraire_tokens({"usage": {"total_tokens": "42"}}) == (0, False)
    assert extraire_tokens({"usage": {"total_tokens": 42.5}}) == (0, False)
    assert extraire_tokens({"usage": {"total_tokens": True}}) == (0, False)
    assert extraire_tokens({"usage": {"total_tokens": None}}) == (0, False)


def test_extraire_tokens_dict_vide():
    """Dictionnaire vide -> (0, False), sans estimation."""
    assert extraire_tokens({}) == (0, False)


def test_extraire_tokens_none():
    """Entrée None -> (0, False), ne lève jamais."""
    assert extraire_tokens(None) == (0, False)


def test_extraire_tokens_ollama_partiel():
    """Ollama avec un seul des deux champs -> (0, False)."""
    assert extraire_tokens({"prompt_eval_count": 10}) == (0, False)
    assert extraire_tokens({"eval_count": 20}) == (0, False)


def test_extraire_tokens_openai_prioritaire_sur_ollama():
    """Si usage OpenAI ET champs Ollama coexistent, OpenAI gagne (premier match)."""
    reponse = {
        "usage": {"total_tokens": 100},
        "prompt_eval_count": 5,
        "eval_count": 5,
    }
    assert extraire_tokens(reponse) == (100, True)


# ---------------------------------------------------------------------------
# 7. budgets.json corrompu : BudgetError CLAIRE (pas un JSONDecodeError nu)
# ---------------------------------------------------------------------------
def test_corruption_json_message_identifie_fichier(tmp_path):
    """Un budgets.json tronqué lève un BudgetError qui identifie le fichier."""
    (tmp_path / "budgets.json").write_text("{ pas du json", encoding="utf-8")
    with pytest.raises(BudgetError) as exc:
        BudgetTracker(tmp_path).status("x")
    # Le nom du fichier (et a fortiori son chemin) doit apparaître dans
    # le message pour permettre le diagnostic — jamais un JSONDecodeError
    # brut qui laisserait l'appelant perplexe.
    message = str(exc.value)
    assert "budgets.json" in message
    assert str(tmp_path / "budgets.json") in str(exc.value)
