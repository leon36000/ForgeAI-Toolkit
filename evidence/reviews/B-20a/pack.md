# Revue scellée — B-20a : fondation du metering (commit 4ffcfd2)

## Story et contexte
Première des deux stories du branchement metering (ADR de l'architecte en annexe).
Périmètre : fondation SEULE — durcissement de la persistance budgets.json,
extraire_tokens, QuotaAtteint + check() pré-appel. AUCUN chemin de production n'est
touché ; le câblage (hardened.py + MeteredTransport) est la story B-20b. Ne jugez
pas son absence.

## Critères d'acceptation (tous doivent être tenus)
CA-1 : deux instances concurrentes sur le même budgets.json ne perdent aucune
       écriture (file_lock + relecture SOUS le verrou + atomic_write_text, zéro
       cache mémoire) ; 4 process × 25 record(10) = total EXACTEMENT 1000.
CA-2 : extraire_tokens traite OpenAI (total_tokens — jamais une somme partielle,
       qui rate les tokens de reasoning), Ollama (prompt_eval_count+eval_count),
       et toute forme non reconnue -> (0, False), sans jamais lever.
CA-3 : check(agent) lève QuotaAtteint(BudgetError) sur COUPURE avec le message
       exact COUPURE: agent '<a>' a dépassé son budget (<used>/<quota> tokens) ;
       record() conserve son contrat (chaîne OK/ALERTE/COUPURE).
CA-4 : budgets.json corrompu -> BudgetError portant le CHEMIN complet.
CA-5 : les 10 tests hérités passent INTACTS ; stdlib uniquement.

## Ce qu'il faut chercher (adversarial)
- une fenêtre de course résiduelle (relecture HORS du verrou, écriture non atomique,
  verrou non partagé entre instances/process) ;
- un cas extraire_tokens qui lève ou renvoie un chiffre inventé ;
- un test qui semble couvrir mais ne détecte pas ;
- une incompatibilité avec les appelants existants de la CLI (_budget_set/_budget_status).

## Diff INTÉGRAL vs origin/main
```diff
diff --git a/src/forgeai/models/budget.py b/src/forgeai/models/budget.py
index 6f19f4b..ec17910 100644
--- a/src/forgeai/models/budget.py
+++ b/src/forgeai/models/budget.py
@@ -5,7 +5,9 @@ from __future__ import annotations
 import json
 from dataclasses import dataclass
 from pathlib import Path
-from typing import Any, Dict
+from typing import Any, Dict, Tuple
+
+from forgeai.models._locking import file_lock, atomic_write_text
 
 
 class BudgetError(Exception):
@@ -13,6 +15,18 @@ class BudgetError(Exception):
     pass
 
 
+class QuotaAtteint(BudgetError):
+    """Levée par ``BudgetTracker.check`` quand un agent est en état ``COUPURE``.
+
+    Hérite de ``BudgetError`` (compatibilité avec les handlers existants)
+    tout en restant capturable distinctement. Sert de signal dédié aux
+    points de mesure en pré-dispatch : l'appel réseau en cours, s'il y
+    en a un, finit normalement ; seuls les appels suivants sont bloqués
+    tant que le budget n'est pas ré-alimenté via ``set_budget``.
+    """
+    pass
+
+
 @dataclass(frozen=True)
 class BudgetState:
     """État courant du budget d'un agent.
@@ -46,11 +60,74 @@ class BudgetState:
         return "OK"
 
 
+def extraire_tokens(reponse: dict) -> Tuple[int, bool]:
+    """Extrait le nombre de tokens consommés d'une réponse LLM, sans lever.
+
+    Formats reconnus (premier match gagne) :
+
+    * OpenAI : ``reponse["usage"]["total_tokens"]`` est un entier
+      (à l'exclusion de ``bool``). Retourne ``(total_tokens, True)``.
+      Le champ est utilisé tel quel — jamais la somme
+      ``prompt_tokens + completion_tokens``, qui manquerait les
+      tokens de reasoning.
+    * Ollama : ``reponse["prompt_eval_count"]`` et
+      ``reponse["eval_count"]`` (à la racine du dict) sont tous deux
+      des entiers (à l'exclusion de ``bool``). Retourne
+      ``(prompt_eval_count + eval_count, True)``.
+
+    Toute autre forme — ``usage`` présent mais ``total_tokens`` absent
+    ou non entier, champs Ollama partiels, ``usage`` de type
+    incorrect, dictionnaire vide, entrée non-dict — produit
+    ``(0, False)``. **Aucune estimation n'est faite.**
+
+    Cette fonction ne lève jamais : une réponse mal formée ne doit pas
+    casser un appel réseau réussi.
+
+    Args:
+        reponse: Dictionnaire représentant la réponse brute d'un
+            fournisseur LLM.
+
+    Returns:
+        Couple ``(tokens_extraits, succes)``. ``succes`` vaut ``True``
+        si et seulement si un format complet et bien typé a été reconnu.
+    """
+    if not isinstance(reponse, dict):
+        return (0, False)
+
+    if "usage" in reponse:
+        usage = reponse["usage"]
+        if isinstance(usage, dict):
+            total = usage.get("total_tokens")
+            if isinstance(total, int) and not isinstance(total, bool):
+                return (total, True)
+        return (0, False)
+
+    prompt_count = reponse.get("prompt_eval_count")
+    eval_count = reponse.get("eval_count")
+    if (
+        isinstance(prompt_count, int)
+        and not isinstance(prompt_count, bool)
+        and isinstance(eval_count, int)
+        and not isinstance(eval_count, bool)
+    ):
+        return (prompt_count + eval_count, True)
+
+    return (0, False)
+
+
 class BudgetTracker:
     """Persistance et suivi des budgets de tokens par agent.
 
     Les données sont stockées dans ``<home>/budgets.json`` sous la forme
     ``{agent: {"quota_tokens": int, "used_tokens": int, "alert_ratio": float}}``.
+
+    La persistance est protégée par un verrou fichier dédié
+    (``<home>/budgets.lock``) : chaque opération publique acquiert le
+    verrou, **relit** l'état depuis le disque, le modifie, puis écrit
+    via ``atomic_write_text`` (création d'un temporaire + ``fsync`` +
+    ``os.replace``). Le fichier est l'unique source de vérité : aucun
+    cache mémoire n'est conservé entre opérations, ce qui rend deux
+    instances concurrentes sûres vis-à-vis des écritures perdues.
     """
 
     _FILENAME = "budgets.json"
@@ -59,7 +136,10 @@ class BudgetTracker:
         self._home = Path(home)
         self._home.mkdir(parents=True, exist_ok=True)
         self._path = self._home / self._FILENAME
-        self._data: Dict[str, Dict[str, Any]] = self._load()
+        # ``file_lock`` crée un fichier ``<arg>.lock`` ; on passe donc
+        # ``<home>/budgets`` pour obtenir le fichier dédié
+        # ``<home>/budgets.lock`` (sibling de ``budgets.json``).
+        self._lock_path = self._home / "budgets"
 
     def _load(self) -> Dict[str, Dict[str, Any]]:
         if not self._path.exists():
@@ -68,14 +148,16 @@ class BudgetTracker:
             try:
                 data = json.load(fh)
             except json.JSONDecodeError:
-                raise BudgetError("budgets.json corrompu")
+                raise BudgetError(f"budgets.json corrompu : {self._path}")
         if not isinstance(data, dict):
-            raise BudgetError("Fichier de budgets corrompu.")
+            raise BudgetError(f"budgets.json corrompu (structure inattendue) : {self._path}")
         return data
 
-    def _save(self) -> None:
-        with self._path.open("w", encoding="utf-8") as fh:
-            json.dump(self._data, fh, indent=2, ensure_ascii=False)
+    def _save(self, data: Dict[str, Dict[str, Any]]) -> None:
+        atomic_write_text(
+            self._path,
+            json.dumps(data, indent=2, ensure_ascii=False),
+        )
 
     def set_budget(self, agent: str, quota_tokens: int, alert_ratio: float = 0.8) -> None:
         """Crée ou réinitialise le budget d'un agent.
@@ -93,12 +175,14 @@ class BudgetTracker:
         if not (0 < alert_ratio <= 1):
             raise BudgetError("alert_ratio doit être dans l'intervalle ]0, 1]")
 
-        self._data[agent] = {
-            "quota_tokens": int(quota_tokens),
-            "used_tokens": 0,
-            "alert_ratio": float(alert_ratio),
-        }
-        self._save()
+        with file_lock(self._lock_path):
+            data = self._load()
+            data[agent] = {
+                "quota_tokens": int(quota_tokens),
+                "used_tokens": 0,
+                "alert_ratio": float(alert_ratio),
+            }
+            self._save(data)
 
     def record(self, agent: str, tokens: int) -> str:
         """Enregistre une consommation de tokens pour un agent.
@@ -113,35 +197,96 @@ class BudgetTracker:
         Raises:
             BudgetError: Si l'agent est inconnu ou si tokens est négatif.
         """
-        if agent not in self._data:
-            raise BudgetError(f"Agent inconnu : {agent}")
         if tokens < 0:
             raise BudgetError("La consommation de tokens ne peut pas être négative.")
 
-        self._data[agent]["used_tokens"] += int(tokens)
-        self._save()
-        return self.status(agent).etat
+        with file_lock(self._lock_path):
+            data = self._load()
+            if agent not in data:
+                raise BudgetError(f"Agent inconnu : {agent}")
+            data[agent]["used_tokens"] += int(tokens)
+            self._save(data)
+            entry = data[agent]
+            state = BudgetState(
+                agent=agent,
+                quota_tokens=entry["quota_tokens"],
+                used_tokens=entry["used_tokens"],
+                alert_ratio=entry["alert_ratio"],
+            )
+            return state.etat
 
     def status(self, agent: str) -> BudgetState:
         """Retourne l'état courant du budget d'un agent.
 
+        L'état est relu sous verrou pour garantir la fraîcheur de la
+        lecture vis-à-vis d'une écriture concurrente.
+
         Raises:
             BudgetError: Si l'agent est inconnu.
         """
-        if agent not in self._data:
-            raise BudgetError(f"Agent inconnu : {agent}")
-
-        entry = self._data[agent]
-        return BudgetState(
-            agent=agent,
-            quota_tokens=entry["quota_tokens"],
-            used_tokens=entry["used_tokens"],
-            alert_ratio=entry["alert_ratio"],
-        )
+        with file_lock(self._lock_path):
+            data = self._load()
+            if agent not in data:
+                raise BudgetError(f"Agent inconnu : {agent}")
+            entry = data[agent]
+            return BudgetState(
+                agent=agent,
+                quota_tokens=entry["quota_tokens"],
+                used_tokens=entry["used_tokens"],
+                alert_ratio=entry["alert_ratio"],
+            )
 
     def report(self) -> list[BudgetState]:
-        """Retourne le rapport de consommation trié par identifiant d'agent."""
-        return sorted(
-            (self.status(agent) for agent in self._data),
-            key=lambda state: state.agent,
-        )
+        """Retourne le rapport de consommation trié par identifiant d'agent.
+
+        L'état complet est relu sous verrou, puis projeté en une liste
+        de ``BudgetState`` triée par nom d'agent.
+        """
+        with file_lock(self._lock_path):
+            data = self._load()
+            return sorted(
+                (
+                    BudgetState(
+                        agent=agent_name,
+                        quota_tokens=entry["quota_tokens"],
+                        used_tokens=entry["used_tokens"],
+                        alert_ratio=entry["alert_ratio"],
+                    )
+                    for agent_name, entry in data.items()
+                ),
+                key=lambda state: state.agent,
+            )
+
+    def check(self, agent: str) -> None:
+        """Verrou pré-dispatch : refuse l'émission si l'agent est en COUPURE.
+
+        Re-lit l'état sous verrou pour fonder la décision sur la dernière
+        version persistée. Si l'état résultant est ``COUPURE``, lève
+        ``QuotaAtteint`` avec un message chiffrant l'agent, sa
+        consommation et son quota. Sinon (état ``OK`` ou ``ALERTE``),
+        retourne ``None`` — l'appel en cours finit normalement et les
+        appels suivants ne sont pas bloqués rétroactivement.
+
+        Args:
+            agent: Identifiant de l'agent à vérifier.
+
+        Raises:
+            QuotaAtteint: Si l'agent a atteint ou dépassé son quota.
+            BudgetError: Si l'agent est inconnu.
+        """
+        with file_lock(self._lock_path):
+            data = self._load()
+            if agent not in data:
+                raise BudgetError(f"Agent inconnu : {agent}")
+            entry = data[agent]
+            state = BudgetState(
+                agent=agent,
+                quota_tokens=entry["quota_tokens"],
+                used_tokens=entry["used_tokens"],
+                alert_ratio=entry["alert_ratio"],
+            )
+            if state.etat == "COUPURE":
+                raise QuotaAtteint(
+                    f"COUPURE: agent '{agent}' a dépassé son budget "
+                    f"({state.used_tokens}/{state.quota_tokens} tokens)"
+                )
diff --git a/tests/test_models_budget.py b/tests/test_models_budget.py
index e4f8a24..37fbb33 100644
--- a/tests/test_models_budget.py
+++ b/tests/test_models_budget.py
@@ -87,8 +87,9 @@ def test_cli_budget_set_status(tmp_path, capsys):
 def test_budgets_json_corrompu_leve_budgeterror(tmp_path):
     from forgeai.models.budget import BudgetTracker, BudgetError
     (tmp_path / "budgets.json").write_text("{ pas du json valide", encoding="utf-8")
-    with pytest.raises(BudgetError):
+    with pytest.raises(BudgetError) as exc:
         BudgetTracker(tmp_path).status("x")
+    assert str(tmp_path / "budgets.json") in str(exc.value)
 
 
 def test_set_budget_message_alert_ratio_reflete_intervalle(tmp_path):
@@ -96,3 +97,194 @@ def test_set_budget_message_alert_ratio_reflete_intervalle(tmp_path):
     with pytest.raises(BudgetError) as exc:
         BudgetTracker(tmp_path).set_budget("a", 100, alert_ratio=1.5)
     assert "]0, 1]" in str(exc.value)
+
+
+# --- B-20a : durcissement (verrou, QuotaAtteint, extraire_tokens) ---
+# === Imports supplémentaires pour B-20a (cible 2) ===
+import json
+import multiprocessing as mp
+from pathlib import Path
+
+from forgeai.models.budget import (
+    BudgetError,
+    BudgetTracker,
+    QuotaAtteint,
+    extraire_tokens,
+)
+
+
+# ---------------------------------------------------------------------------
+# 1. check() : agent OK -> None ; agent inconnu -> BudgetError
+# ---------------------------------------------------------------------------
+def test_check_agent_ok_et_inconnu(tmp_path):
+    """check() ouvre le pré-dispatch quand l'agent est OK et refuse un inconnu."""
+    tracker = BudgetTracker(tmp_path)
+    tracker.set_budget("x", 1000)
+    # Agent connu et sous quota : aucun signal, l'appel peut partir.
+    assert tracker.check("x") is None
+    # Agent non déclaré : BudgetError (saisie invalide), pas QuotaAtteint.
+    with pytest.raises(BudgetError):
+        tracker.check("inconnu")
+
+
+# ---------------------------------------------------------------------------
+# 2. check() après dépassement -> QuotaAtteint au message contractuel exact
+# ---------------------------------------------------------------------------
+def test_check_quota_atteint_message_exact(tmp_path):
+    """Le message d'erreur est chiffré, agent et compteurs inclus."""
+    tracker = BudgetTracker(tmp_path)
+    tracker.set_budget("alpha", 100)
+    tracker.record("alpha", 100)  # -> COUPURE
+
+    with pytest.raises(QuotaAtteint) as exc:
+        tracker.check("alpha")
+    assert str(exc.value) == (
+        "COUPURE: agent 'alpha' a dépassé son budget (100/100 tokens)"
+    )
+
+
+# ---------------------------------------------------------------------------
+# 3. QuotaAtteint hérite de BudgetError (compatibilité handlers existants)
+# ---------------------------------------------------------------------------
+def test_quota_atteint_herite_de_budget_error():
+    """Les handlers qui capturent BudgetError doivent aussi voir QuotaAtteint."""
+    assert issubclass(QuotaAtteint, BudgetError)
+    assert isinstance(QuotaAtteint("x"), BudgetError)
+
+
+# ---------------------------------------------------------------------------
+# 4. Concurrence réelle : deux trackers, ordre d'instanciation croisé
+# ---------------------------------------------------------------------------
+def test_concurrence_deux_trackers_meme_home(tmp_path):
+    """tracker_b, créé AVANT le set_budget, ne doit pas écraser la valeur posée par A.
+
+    Sans la relecture sous verrou à chaque opération, tracker_b.record()
+    opérerait sur un état vide en mémoire et écraserait l'écriture de A.
+    La relecture sous verrou garantit que la somme 100+50=150 est préservée
+    quel que soit l'ordre d'instanciation.
+    """
+    tracker_a = BudgetTracker(tmp_path)
+    tracker_b = BudgetTracker(tmp_path)  # créé AVANT set_budget
+
+    tracker_a.set_budget("x", 1000)   # A pose le quota
+    tracker_b.record("x", 100)        # B consomme 100
+    tracker_a.record("x", 50)         # A consomme 50
+
+    # Les deux instances voient le même total (le disque est l'unique vérité)
+    assert tracker_a.status("x").used_tokens == 150
+    assert tracker_b.status("x").used_tokens == 150
+
+    # Et le fichier sur disque reflète bien 150 (pas 50, pas 100)
+    on_disk = json.loads((tmp_path / "budgets.json").read_text(encoding="utf-8"))
+    assert on_disk["x"]["used_tokens"] == 150
+
+
+# ---------------------------------------------------------------------------
+# 5. Concurrence multi-process : 4 process × 25 × 10 = 1000, sans perte
+# ---------------------------------------------------------------------------
+def _record_in_worker(home_str, agent, tokens, count, barrier):
+    """Worker picklable : barrier pour aligner les départs, puis N records."""
+    barrier.wait()
+    tracker = BudgetTracker(Path(home_str))
+    for _ in range(count):
+        tracker.record(agent, tokens)
+
+
+@pytest.mark.skipif(
+    mp.get_start_method(allow_none=True) == "spawn",
+    reason=("Ce test de concurrence inter-process requiert la méthode fork : il TOURNE en CI Linux "
+            "(gate tests ; preuve B-20a au Registres/mission.jsonl) et ne skippe que sur une "
+            "plateforme spawn-only où fork n'existe pas."),
+)
+def test_concurrence_multi_process(tmp_path):
+    """4 process font chacun 25 record(x, 10) -> total final EXACTEMENT 1000."""
+    tracker = BudgetTracker(tmp_path)
+    tracker.set_budget("x", 2000)
+
+    barrier = mp.Barrier(4)
+    procs = [
+        mp.Process(
+            target=_record_in_worker,
+            args=(str(tmp_path), "x", 10, 25, barrier),
+        )
+        for _ in range(4)
+    ]
+    for p in procs:
+        p.start()
+    for p in procs:
+        p.join(timeout=20)
+        assert not p.is_alive(), "Un worker est resté bloqué."
+
+    assert tracker.status("x").used_tokens == 1000
+
+
+# ---------------------------------------------------------------------------
+# 6. extraire_tokens : tous les formats reconnus et leurs cas de rejet
+# ---------------------------------------------------------------------------
+def test_extraire_tokens_openai_complet():
+    """Usage OpenAI avec total_tokens entier -> (n, True)."""
+    assert extraire_tokens({"usage": {"total_tokens": 42}}) == (42, True)
+
+
+def test_extraire_tokens_ollama_complet():
+    """Ollama avec prompt_eval_count + eval_count entiers -> (somme, True)."""
+    assert extraire_tokens(
+        {"prompt_eval_count": 10, "eval_count": 20}
+    ) == (30, True)
+
+
+def test_extraire_tokens_usage_sans_total_tokens():
+    """usage présent mais total_tokens absent -> (0, False)."""
+    assert extraire_tokens({"usage": {}}) == (0, False)
+    assert extraire_tokens({"usage": {"prompt_tokens": 10}}) == (0, False)
+    assert extraire_tokens({"usage": {"completion_tokens": 5}}) == (0, False)
+
+
+def test_extraire_tokens_total_tokens_non_entier():
+    """total_tokens d'un type non-entier (str, float, bool, None) -> (0, False)."""
+    assert extraire_tokens({"usage": {"total_tokens": "42"}}) == (0, False)
+    assert extraire_tokens({"usage": {"total_tokens": 42.5}}) == (0, False)
+    assert extraire_tokens({"usage": {"total_tokens": True}}) == (0, False)
+    assert extraire_tokens({"usage": {"total_tokens": None}}) == (0, False)
+
+
+def test_extraire_tokens_dict_vide():
+    """Dictionnaire vide -> (0, False), sans estimation."""
+    assert extraire_tokens({}) == (0, False)
+
+
+def test_extraire_tokens_none():
+    """Entrée None -> (0, False), ne lève jamais."""
+    assert extraire_tokens(None) == (0, False)
+
+
+def test_extraire_tokens_ollama_partiel():
+    """Ollama avec un seul des deux champs -> (0, False)."""
+    assert extraire_tokens({"prompt_eval_count": 10}) == (0, False)
+    assert extraire_tokens({"eval_count": 20}) == (0, False)
+
+
+def test_extraire_tokens_openai_prioritaire_sur_ollama():
+    """Si usage OpenAI ET champs Ollama coexistent, OpenAI gagne (premier match)."""
+    reponse = {
+        "usage": {"total_tokens": 100},
+        "prompt_eval_count": 5,
+        "eval_count": 5,
+    }
+    assert extraire_tokens(reponse) == (100, True)
+
+
+# ---------------------------------------------------------------------------
+# 7. budgets.json corrompu : BudgetError CLAIRE (pas un JSONDecodeError nu)
+# ---------------------------------------------------------------------------
+def test_corruption_json_message_identifie_fichier(tmp_path):
+    """Un budgets.json tronqué lève un BudgetError qui identifie le fichier."""
+    (tmp_path / "budgets.json").write_text("{ pas du json", encoding="utf-8")
+    with pytest.raises(BudgetError) as exc:
+        BudgetTracker(tmp_path).status("x")
+    # Le nom du fichier (et a fortiori son chemin) doit apparaître dans
+    # le message pour permettre le diagnostic — jamais un JSONDecodeError
+    # brut qui laisserait l'appelant perplexe.
+    message = str(exc.value)
+    assert "budgets.json" in message
+    assert str(tmp_path / "budgets.json") in str(exc.value)
```

## Preuve d'exécution CAPTURÉE (rejouée après le commit 4ffcfd2)
```
$ python3 -m pytest tests/test_models_budget.py -q
........................                                                 [100%]
exit=0

# campagne de mutations (substitution vérifiée avant interprétation)
  check() neutralisé                         : ROUGE (exit 1)
  total_tokens -> prompt+completion          : ROUGE (exit 1)
  priorité OpenAI inversée                   : ROUGE (exit 1)
  verrou retiré de record()                  : ROUGE (exit 1)
  cache d'init réintroduit (l'ancien bug)    : ROUGE (exit 1)
  chemin retiré du message de corruption     : ROUGE (exit 1)
  restauration                               : VERT  (exit 0)

$ no_stub_scan (2 fichiers) : OK ; suite complète : exit=0
```

## Annexe — ADR B-20 (déjà tranché, ne pas re-juger)
# B-20 — Metering au gateway : décision d'architecture

Décision rendue par l'architecte (Kimi-K3) le 2026-07-29, appliquée telle quelle.
Périmètre de CETTE story (B-20a) : fondation seule — verrou budgets.json,
extraire_tokens, QuotaAtteint, check() pré-appel. AUCUN chemin de production
touché. B-20b (branchement hardened.py + MeteredTransport) suit et dépend de a.

# ADR B-20 — Brancher le metering au gateway

**Statut** : Proposé
**Portée** : `models/budget.py`, `rag/hardened.py`, `models/probe.py` (aucune signature existante cassée)

---

## 1. Où mesurer — les deux chemins, au point où la réponse existe

**Décision : on instrumente les deux chemins, chacun à l'endroit où le dict réponse est disponible, sans introduire de point commun.** Chemin B : le metering s'insère à l'appel de `_post_bearer` dans `hardened.py` (l.168), seul site à consommation significative. Chemin A : un `MeteredTransport(inner, tracker, agent)` implémentant le Protocol `Transport` (probe.py:15), injecté via le paramètre `transport` déjà prévu — les appelants existants passent `transport=None` et restent inchangés. Pas de point commun : les deux chemins sont disjoints par construction (testabilité du probe, bearer durci du RAG), et les forcer à converger refactorerait deux graphes d'appel pour zéro gain de mesure, puisque la mesure exige la réponse et que la réponse n'existe qu'à ces deux adresses.

## 2. Comment bloquer — verrou pré-appel, exception dédiée, l'appel en cours finit

**Décision : coupure en pré-dispatch uniquement.** Contrat exact : le point de mesure appelle `status(agent)` AVANT toute émission réseau ; si l'état est `COUPURE`, il lève `QuotaAtteint` — exception nouvelle héritant de `BudgetError` (compatibilité avec les handlers existants, capture distincte possible) — avec le message `COUPURE: agent '<agent>' a dépassé son budget (<consommé>/<quota> tokens)` ; `ALERTE` ne bloque jamais, elle journalise seulement. L'appel en cours quand le quota tombe finit normalement : la coupure est une porte à l'entrée, pas un disjoncteur en vol ; le dépassement est enregistré post-appel et bloque l'appel suivant. Justification : un blocage pré-appel est déterministe et testable en CI (transport espion = zéro appel émis), tandis qu'une interruption mid-stream est non déterministe et non prouvable.

## 3. Lire `usage` — parser unique, absence journalisée, jamais d'estimation

**Décision : une fonction pure unique `extraire_tokens(reponse: dict) -> tuple[int, bool]` vivant à côté de budget.py** : elle tente `usage.total_tokens` (format OpenAI — inclut les tokens de reasoning, voir §7), puis `prompt_eval_count + eval_count` (Ollama), et retourne `(tokens, exact)`. Si `usage` est absent : on compte 0 et on écrit une entrée de journal avec `tokens=0, exact=false, motif="usage_absent"` — jamais d'estimation inventée. Justification : un chiffre estimé corrompt silencieusement le registre, une absence journalisée reste prouvable et visible ; l'honnêteté du ledger prime sur sa complétude.

## 4. L'identité d'agent — paramètre constructeur optionnel, défauts stables, pas de variable d'env

**Décision : paramètre keyword optionnel au constructeur avec défaut documenté.** `HardenedRagClient` reçoit `agent: str = "rag"` ; `MeteredTransport` prend `agent` à la construction (c'est sa raison d'être), l'injection restant opt-in via le paramètre `transport` existant. Aucune variable d'environnement : un état global implicite diverge entre process web et CLI et n'est pas prouvable en CI. Justification : les défauts `"rag"`/`"probe"` préservent tous les appelants et tests existants (test_models_gateway.py:121 inclus) tout en produisant une comptabilité honnête dès le branchement, et la granularité fine devient disponible sans migration.

## 5. Le verrou de budgets.json — dans CETTE story

**Décision : correction incluse, motif routes.py : `file_lock` + relecture DANS le verrou + incrément + `atomic_write_text`, sans aucun cache en mémoire.** Justification : la story fait passer le nombre de writers de zéro à chaque appel modèle ; livrer le metering sur une persistance qui perd les écritures concurrentes rend le journal prouvablement faux, ce qui vide le critère « consommation mesurée et journalisée » — le motif existe déjà dans `models/_locking.py`, le coût est faible, le risque de ne rien faire est une perte certaine.

## 6. Découpage — deux stories ordonnées

**Décision : deux stories.**

- **B-20a (fondation, ne touche aucun chemin de production)** : verrou + écriture atomique + relecture sous verrou de `budget.py` ; `extraire_tokens` ; `QuotaAtteint` ; `check(agent)` pré-appel. *Critère testable* : deux instances concurrentes sur le même `budgets.json` ne perdent aucune écriture ; le parser traite OpenAI, Ollama, et l'absence (journalisée `exact=false`) ; `check` lève `QuotaAtteint` sur COUPURE avec agent/quota/consommé dans le message ; `record()` retourne toujours OK/ALERTE/COUPURE.
- **B-20b (branchement, dépend de B-20a)** : metering dans `hardened.py` (défaut `"rag"`) + `MeteredTransport`. *Critère testable* : un transport stub retournant `usage.total_tokens=N` incrémente le journal d'exactement N ; après dépassement, l'appel suivant lève AVANT toute émission (espion : zéro `post`) ; une réponse sans `usage` produit une entrée journalisée `exact=false` ; test_models_gateway.py:121 passe inchangé.

Justification : B-20a est prouvable sans toucher un seul chemin d'appel, et coupler dans une seule story le fix de persistance et le câblage mélangerait deux modes de défaillance dans une même revue.

## 7. Le piège — ce qui rendra ce metering faux en production

**Décision : on acte quatre trous concrets et leur traitement.**
1. **Retry/perte de réponse** : un POST qui timeout côté client mais facturé côté serveur n'est jamais compté — sous-comptage silencieux. Traitement : tout timeout produit une entrée `tokens=0, exact=false, motif="timeout"`, et l'enregistrement ne porte que sur la réponse effectivement consommée (jamais de double comptage en cas de retry applicatif).
2. **Tokens de reasoning** : c'est précisément pourquoi §3 lit `total_tokens` et jamais une somme partielle — un parser sur `prompt_tokens + completion_tokens` raterait les modèles dont le reasoning est facturé hors de ces champs.
3. **Ledger hôte-local** : budgets.json est partagé entre process web et CLI de la même machine (réglé par §5 : relecture sous verrou à chaque écriture, le fichier est la seule source de vérité), mais deux machines ou un conteneur avec son propre FS ont chacun leur ledger — la coupure est par hôte, à documenter comme telle, pas comme un quota global.
4. **Porte coopérative** : la coupure ne bloque que les chemins passant par le point de mesure ; tout futur appel HTTP direct contourne le verrou. Traitement : garde CI (grep) interdisant toute nouvelle émission `urllib`/`requests` hors des deux sites instrumentés, et identités `"probe"`/`"rag"` distinctes pour qu'une tempête de probes à 8 tokens ne coupe jamais la génération de production — ni l'inverse.
