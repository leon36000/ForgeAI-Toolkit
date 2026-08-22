#!/usr/bin/env python3
"""Gate CI `reviews-sealed` — ferme la déviation D9 de l'audit de dérive.

Rien n'empêchait structurellement un merge sans revue aveugle scellée passante (les stories
models/ ont été mergées puis trouvées défectueuses). Ce gate rend la revue OBLIGATOIRE et
BLOQUANTE côté CI pour les revues déclarées LIANTES.

Modèle : `evidence/reviews/BINDING.txt` liste les dossiers de revue qui DOIVENT actuellement
dépouiller en APPROVE (un par ligne ; # = commentaire). Une story ajoute son dossier quand elle
passe ; une revue superseded (ex. code remédié + re-revu) est retirée du manifeste (les dossiers
historiques/legacy restent au dépôt pour la traçabilité mais ne sont PAS liants).

Le dépouillement réutilise `scripts/revue.py` (fonction pure `tally`, invariant #10 : aucun
LLM n'écrit un score). Le gate échoue (exit 1) si un dossier liant n'est pas APPROVE, est
absent, ou n'a pas ses verdicts.

#434 — deux modes supplémentaires, OPT-IN par drapeau; le quorum multi_vendor par défaut
#reste inchangé, tandis qu'un reçu sol_blind actif doit conserver sa forme et sa fraîcheur :

  --exiger-recu-courant --base-ref <ref>   (mode PR) : en plus du dépouillement legacy
    habituel, exige qu'AU MOINS UNE entrée liante porte un evidence/reviews/<ID>/RECU.json qui
    se vérifie contre l'état git RÉEL de la PR courante (commit, arbre, diff canonique hors
    evidence/reviews/**). Sans reçu valide couvrant le changement courant : échec explicite.
    Depuis #578, un reçu COURANT n'est admissible que si son round respecte le coupe-circuit
    partagé de `scripts/coordination/scope_guard.py` (1-2 automatiques, 3 maximum après replan ;
    >3 interdit). Les reçus historiques restent lisibles et ne sont pas réécrits.

  --mode archive : dépouillement legacy habituel pour toutes les entrées ; en plus, pour
    chaque entrée qui porte un RECU.json, vérifie que son commit est un ANCÊTRE du HEAD
    courant (post-merge, sur main). Un reçu pointant un commit jamais fusionné échoue.

Les 150+ entrées historiques de BINDING.txt n'ont PAS de RECU.json : leur comportement dans
LES DEUX modes reste identique à aujourd'hui — "archivées sans être rattachées aux nouveaux
changements".

Usage : reviews_gate.py [--manifest evidence/reviews/BINDING.txt]
                        [--reviews-root evidence/reviews]
                        [--exiger-recu-courant --base-ref <ref>] [--mode archive]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Callable

REPO = Path(__file__).resolve().parent.parent
GitRunner = Callable[[list[str]], str]


def _load_revue():
    spec = importlib.util.spec_from_file_location("revue", REPO / "scripts" / "revue.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_scope_guard():
    path = REPO / "scripts" / "coordination" / "scope_guard.py"
    spec = importlib.util.spec_from_file_location("scope_guard", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _current_receipt_round_allowed(receipt: object) -> tuple[bool, str]:
    """Applique prospectivement le coupe-circuit #578 au reçu qui couvre la PR courante.

    Le mode archive ne passe jamais ici : un historique ancien peut donc conserver fidèlement
    ses rounds élevés sans être réécrit. Le reçu doit porter explicitement `replanned: true`
    pour le round 3 ; le gate ne déduit jamais ce fait du seul numéro de round.
    """
    if not isinstance(receipt, dict):
        return False, "INVALID_RECEIPT"
    round_number = receipt.get("round")
    if not isinstance(round_number, int) or isinstance(round_number, bool):
        return False, "INVALID_ROUND"
    replanned = receipt.get("replanned", False)
    if not isinstance(replanned, bool):
        return False, "INVALID_REPLAN"
    guard = _load_scope_guard()
    return guard.review_round_policy(round_number, replanned=replanned)


def _receipt_round_chain_allowed(
    receipt: object,
    current_entry: str,
    binding: list[str],
    reviews_root: Path,
) -> tuple[bool, str]:
    """Refuse un rollback de round pour une même issue.

    Le round ne doit pas être un compteur que l'orchestrateur peut réinitialiser en changeant
    de dossier. Les reçus antérieurs versionnés dans le manifeste, pour la même issue et le même
    merge-base, forment la chaîne de référence; une première revue est round 1, puis chaque
    tentative suivante doit être exactement le round précédent + 1. Un même numéro d'issue peut
    légitimement avoir plusieurs PR successives après rebase de main : leur merge-base distingue
    ces lignées.
    """
    if not isinstance(receipt, dict):
        return False, "INVALID_RECEIPT"
    issue = receipt.get("issue")
    round_number = receipt.get("round")
    if isinstance(issue, bool) or not isinstance(issue, int):
        return False, "INVALID_ISSUE"
    if isinstance(round_number, bool) or not isinstance(round_number, int):
        return False, "INVALID_ROUND"

    prior_max = 0
    for entry in binding:
        if entry == current_entry:
            continue
        candidate = (reviews_root / entry).resolve() / "RECU.json"
        if not candidate.is_file():
            continue
        try:
            prior = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False, "PRIOR_RECEIPT_UNREADABLE"
        if (
            not isinstance(prior, dict)
            or prior.get("issue") != issue
            or prior.get("base_commit") != receipt.get("base_commit")
        ):
            continue
        prior_round = prior.get("round")
        if isinstance(prior_round, int) and not isinstance(prior_round, bool):
            prior_max = max(prior_max, prior_round)

    expected = prior_max + 1
    if round_number != expected:
        return False, "ROUND_NOT_MONOTONIC"
    return True, "CHAIN"


def _default_runner(command: list[str]) -> str:
    return subprocess.run(
        command,
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def read_manifest(path: Path) -> list[str]:
    if not path.exists():
        return []
    lines = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            lines.append(line)
    return lines


def _is_ancestor(commit: str, runner: GitRunner) -> bool:
    try:
        runner(["git", "merge-base", "--is-ancestor", commit, "HEAD"])
    except subprocess.CalledProcessError:
        return False
    return True


def check(
    manifest: Path,
    reviews_root: Path,
    *,
    exiger_recu_courant: bool = False,
    base_ref: str | None = None,
    expected_issue: int | None = None,
    mode: str | None = None,
    runner: GitRunner | None = None,
    now: datetime | None = None,
) -> tuple[bool, list[str]]:
    revue = _load_revue()
    execute = _default_runner if runner is None else runner
    report: list[str] = []
    ok = True
    binding = read_manifest(manifest)

    if exiger_recu_courant and not base_ref:
        return False, ["ECHEC : --base-ref est obligatoire avec --exiger-recu-courant"]
    if mode not in (None, "archive"):
        return False, [f"ECHEC : mode inconnu {mode!r}"]

    etat_git = None
    git_state_error: Exception | None = None
    current_receipt_mode = None
    if exiger_recu_courant:
        try:
            current_receipt_mode = revue.load_autonomy_policy()["review"]["default_mode"]
        except (OSError, TypeError, ValueError, KeyError) as error:
            return False, [f"ECHEC : politique de revue courante invalide : {error}"]

    def current_git_state() -> dict:
        """Resolve the PR state only after local receipt coherence has passed."""
        nonlocal etat_git, git_state_error
        if etat_git is not None:
            return etat_git
        if git_state_error is not None:
            raise git_state_error
        try:
            etat_git = revue._etat_git_reel(base_ref, "HEAD", runner=execute)
        except (OSError, ValueError, subprocess.CalledProcessError) as error:
            git_state_error = error
            raise
        return etat_git

    if not binding:
        ok = False
        report.append(
            f"ECHEC : manifeste {manifest} vide ou absent — aucune revue liante vérifiée"
        )

    root_resolved = reviews_root.resolve()
    received_current = False
    for entry in binding:
        candidate = reviews_root / entry
        try:
            inside_root = candidate.resolve().is_relative_to(root_resolved)
        except OSError:
            inside_root = False
        if not inside_root:
            ok = False
            report.append(f"ECHEC {entry} : chemin hors de la racine de revues ({reviews_root})")
            continue
        directory = candidate.resolve()
        verdict_files = sorted(directory.glob("*.verdict.json"))
        if not verdict_files:
            ok = False
            report.append(f"ECHEC {entry} : aucun verdict scellé (dossier absent/vide)")
            continue

        try:
            verdicts = [
                json.loads(path.read_text(encoding="utf-8")) for path in verdict_files
            ]
        except (OSError, json.JSONDecodeError) as error:
            ok = False
            report.append(f"ECHEC {entry} : verdict illisible : {error}")
            continue

        receipt_path = directory / "RECU.json"
        receipt = None
        if receipt_path.is_file():
            try:
                receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                if exiger_recu_courant:
                    ok = False
                    report.append(f"ECHEC {entry} : reçu illisible : {error}")
                    continue

        # Receipt mode is the dispatch contract: legacy multi_vendor keeps its 3/3 tally;
        # active sol_blind is delegated to the exact-one-Sol validator without weakening legacy.
        receipt_mode = receipt.get("mode", "multi_vendor") if isinstance(receipt, dict) else "multi_vendor"
        sol_covers_current = False
        sol_shape_error: Exception | None = None
        sol_freshness_error: Exception | None = None
        sol_git_error: Exception | None = None
        historical_sol = False
        historical_sol_valid = True
        if receipt_mode == "sol_blind" and exiger_recu_courant:
            # The local receipt/prompt/verdict contract is intentionally checked before the
            # first Git command. A malformed or forged claim must not get to choose what Git
            # object the gate resolves (SOL603-B01).
            try:
                revue._sol_expected_from_receipt_shape(
                    receipt,
                    verdicts,
                    directory,
                    enforce_freshness=False,
                )
                revue._validate_sol_temporal_claim(receipt, verdicts, now=now)
            except (
                OSError,
                json.JSONDecodeError,
                KeyError,
                TypeError,
                ValueError,
                subprocess.CalledProcessError,
            ) as error:
                sol_shape_error = error
            if sol_shape_error is None:
                try:
                    current_state = current_git_state()
                except (
                    OSError,
                    ValueError,
                    subprocess.CalledProcessError,
                ) as error:
                    sol_git_error = error
                else:
                    historical_sol = not revue._sol_receipt_binding_matches_current(
                        receipt, current_state
                    )
                    if not historical_sol:
                        try:
                            revue._sol_expected_from_receipt_shape(
                                receipt,
                                verdicts,
                                directory,
                                enforce_freshness=True,
                                freshness_now=now,
                            )
                        except (
                            OSError,
                            json.JSONDecodeError,
                            KeyError,
                            TypeError,
                            ValueError,
                            subprocess.CalledProcessError,
                        ) as error:
                            sol_freshness_error = error
        if historical_sol:
            # A historical receipt may stop covering the current diff, but that status must not
            # turn an intrinsically malformed/tampered receipt into informational noise. Validate
            # its own immutable contract against the reviewed Git objects and stored prompt first;
            # only the later current-state mismatch is exempted.
            try:
                revue._validate_sol_archive_receipt(
                    receipt,
                    execute,
                    verdicts=verdicts,
                    review_dir=directory,
                    now=now,
                )
            except (
                OSError,
                json.JSONDecodeError,
                KeyError,
                TypeError,
                ValueError,
                subprocess.CalledProcessError,
            ) as error:
                historical_sol_valid = False
                historical_sol = False
                ok = False
                report.append(
                    f"ECHEC {entry} : preuve Sol historique intrinsèquement invalide = {error}"
                )
        if receipt_mode not in ("multi_vendor", "sol_blind"):
            result = {"result": "INVALIDE", "reason": f"mode de reçu inconnu : {receipt_mode!r}"}
        elif receipt_mode == "sol_blind":
            try:
                if sol_shape_error is not None:
                    raise sol_shape_error
                if sol_freshness_error is not None:
                    raise sol_freshness_error
                if sol_git_error is not None:
                    raise sol_git_error
                if exiger_recu_courant or mode == "archive":
                    # Validate all local receipt/verdict/prompt bindings before touching any
                    # Git object. This keeps malformed claims cheap and deterministic to reject.
                    freshness_now = revue._aware_timestamp(receipt.get("date_heure"))
                    if exiger_recu_courant and not historical_sol:
                        freshness_now = now
                    revue._sol_expected_from_receipt_shape(
                        receipt,
                        verdicts,
                        directory,
                        enforce_freshness=True,
                        freshness_now=freshness_now,
                    )
                    if mode == "archive":
                        # Archive freshness is evaluated at its sealing timestamp, but a
                        # future-dated seal is never admissible against the real validation
                        # clock (SOL603-B03).
                        receipt_time = revue._aware_timestamp(receipt.get("date_heure"))
                        if receipt_time > revue._validation_time(now):
                            raise ValueError("date_heure du reçu futur")
                    expected = revue._sol_expected_from_git(
                        receipt,
                        etat_git,
                        directory,
                        verdicts,
                        runner=execute,
                    )
                    sol_covers_current = bool(expected.pop("_covers_current", False))
                else:
                    # The legacy/default gate validates the receipt's complete local shape and
                    # prompt binding, but does not require the shallow CI checkout to resolve
                    # every frozen Git object. PR/archive modes perform the stronger Git proof.
                    # Keep the intrinsic order/future checks even though this compatibility path
                    # deliberately does not expire old receipts against the current wall clock.
                    revue._validate_sol_temporal_claim(receipt, verdicts, now=now)
                    expected = revue._sol_expected_from_receipt_shape(
                        receipt,
                        verdicts,
                        directory,
                        # The flagless gate is the compatibility/shape path. It must not
                        # expire an already sealed receipt against the wall clock; current
                        # freshness belongs to the explicit PR proof path above, while
                        # archive mode evaluates age at the receipt's sealing timestamp.
                        enforce_freshness=False,
                    )
                result = revue.tally_sol_blind(
                    verdicts,
                    expected=expected,
                    codeurs=receipt.get("codeur", []),
                    allow_retired_codeurs=(mode == "archive"),
                )
                historical_sol = exiger_recu_courant and not sol_covers_current
            except (OSError, TypeError, ValueError, subprocess.CalledProcessError) as error:
                result = {"result": "INVALIDE", "reason": f"preuve Git/prompt Sol invalide : {error}"}
        else:
            result = revue.tally(verdicts)
        if result.get("result") != "APPROVE":
            if sol_shape_error is not None:
                ok = False
                report.append(
                    f"ECHEC {entry} : preuve Sol intrinsèquement invalide = "
                    f"{result.get('reason', '')}"
                )
            elif historical_sol:
                report.append(
                    f"info  {entry} : revue Sol historique non couvrante = "
                    f"{result.get('result')} ({result.get('reason', '')})"
                )
            else:
                ok = False
                report.append(
                    f"ECHEC {entry} : dépouillement = {result.get('result')} "
                    f"({result.get('reason', '')})"
                )
        else:
            prefix = "info  " if historical_sol else "OK    "
            report.append(
                f"{prefix}{entry} : APPROVE {result.get('reason', '')} "
                f"vendors {result.get('vendors')}"
            )

        if exiger_recu_courant and receipt_path.is_file():
            if receipt_mode == "sol_blind" and (
                sol_shape_error is not None or sol_git_error is not None or etat_git is None
            ):
                reason = sol_shape_error or sol_git_error or git_state_error
                receipt_result = {
                    "result": "INVALIDE",
                    "reason": f"preuve Sol locale/inaccessible : {reason}",
                }
            else:
                try:
                    if etat_git is None:
                        etat_git = current_git_state()
                    receipt_result = revue.verifier_recu(
                        receipt,
                        verdicts,
                        etat_git,
                        review_dir=directory,
                        runner=execute,
                        now=now,
                    )
                except (
                    OSError,
                    TypeError,
                    ValueError,
                    subprocess.CalledProcessError,
                ) as error:
                    receipt_result = {"result": "INVALIDE", "reason": str(error)}
            if receipt_result.get("result") == "APPROVE":
                if receipt_mode != current_receipt_mode:
                    ok = False
                    report.append(
                        f"ECHEC {entry} : reçu courant mode={receipt_mode!r} refusé ; "
                        f"mode de politique requis = {current_receipt_mode!r}"
                    )
                    continue
                if expected_issue is not None and (
                    not isinstance(receipt, dict) or receipt.get("issue") != expected_issue
                ):
                    ok = False
                    actual_issue = receipt.get("issue") if isinstance(receipt, dict) else None
                    report.append(
                        f"ECHEC {entry} : reçu issue={actual_issue!r} différent de la PR "
                        f"courante issue={expected_issue}"
                    )
                    continue
                round_allowed, round_mode = _current_receipt_round_allowed(receipt)
                if not round_allowed:
                    ok = False
                    round_value = receipt.get("round") if isinstance(receipt, dict) else None
                    report.append(
                        f"ECHEC {entry} : reçu courant round={round_value!r} refusé "
                        f"par le coupe-circuit #578 ({round_mode}); maximum prospectif = 3"
                    )
                    continue
                chain_allowed, chain_mode = _receipt_round_chain_allowed(
                    receipt, entry, binding, reviews_root
                )
                if not chain_allowed:
                    ok = False
                    round_value = receipt.get("round") if isinstance(receipt, dict) else None
                    report.append(
                        f"ECHEC {entry} : reçu courant round={round_value!r} refusé "
                        f"par la chaîne monotone des reçus ({chain_mode})"
                    )
                    continue
                received_current = True
                report.append(
                    f"OK    {entry} : reçu couvre le changement courant ({chain_mode})"
                )
            else:
                # PAS un ECHEC de cette entrée : un reçu qui ne valide plus contre l'état git
                # COURANT est l'état normal et permanent de toute entrée HISTORIQUE (déjà
                # mergée) une fois qu'origin/main a avancé — son base_commit ne correspondra
                # plus jamais. Seule l'ABSENCE de tout reçu couvrant est un échec (vérifié plus
                # bas via received_current). Régression #439/PR500 : le mode PR faisait
                # échouer le gate sur CHAQUE reçu historique déjà mergé, bloquant toute PR
                # future dès qu'une entrée liante antérieure portait un RECU.json.
                if receipt_mode == "sol_blind" and not historical_sol_valid:
                    ok = False
                    report.append(
                        f"ECHEC {entry} : reçu Sol historique intrinsèquement invalide = "
                        f"{receipt_result.get('result')} ({receipt_result.get('reason', '')})"
                    )
                else:
                    report.append(
                        f"info  {entry} : reçu invalide = {receipt_result.get('result')} "
                        f"({receipt_result.get('reason', '')}) — ignoré si un autre reçu couvre "
                        f"le changement courant"
                    )

        if mode == "archive" and receipt_path.is_file():
            reviewed_commit = None
            try:
                receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                if isinstance(receipt, dict) and receipt.get("mode") == "sol_blind":
                    revue._validate_sol_archive_receipt(
                        receipt,
                        execute,
                        verdicts=verdicts,
                        review_dir=directory,
                        now=now,
                    )
                    commit = receipt["head_commit"]
                    reviewed_commit = receipt["reviewed_head_commit"]
                else:
                    commit = receipt["head_commit"]
                    # Legacy receipts retain their historical ref validation; only the Sol
                    # schema requires exact object IDs for every commit/tree field.
                    revue._validate_git_ref(commit)
            except (
                OSError,
                json.JSONDecodeError,
                KeyError,
                ValueError,
                TypeError,
                subprocess.CalledProcessError,
            ) as error:
                # TypeError : RECU.json valide en JSON mais pas un objet (ex. liste/null) —
                # receipt["head_commit"] lèverait sinon une exception non gérée (objection
                # mineure round 3, DeepSeek-V4-Pro).
                ok = False
                report.append(f"ECHEC {entry} : reçu archive illisible : {error}")
                continue
            if not _is_ancestor(commit, execute):
                ok = False
                report.append(f"ECHEC {entry} : reçu pointe un commit jamais fusionné")
            if reviewed_commit is not None and not _is_ancestor(reviewed_commit, execute):
                ok = False
                report.append(
                    f"ECHEC {entry} : reçu Sol reviewed_head_commit jamais fusionné"
                )

    if exiger_recu_courant and not received_current:
        ok = False
        report.append("ECHEC : aucun reçu ne couvre le changement courant")
    return ok, report


def main(argv: list[str] | None = None, *, runner: GitRunner | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default=str(REPO / "evidence" / "reviews" / "BINDING.txt"))
    ap.add_argument("--reviews-root", default=str(REPO / "evidence" / "reviews"))
    ap.add_argument("--exiger-recu-courant", action="store_true")
    ap.add_argument("--base-ref")
    ap.add_argument("--issue", type=int)
    ap.add_argument("--mode", choices=("archive",))
    args = ap.parse_args(argv)

    ok, report = check(
        Path(args.manifest),
        Path(args.reviews_root),
        exiger_recu_courant=args.exiger_recu_courant,
        base_ref=args.base_ref,
        expected_issue=args.issue,
        mode=args.mode,
        runner=runner,
    )
    print("REVIEWS-SEALED GATE (déviation D9)")
    for line in report:
        print("  " + line)
    if not ok:
        print("GATE ECHOUÉ : une revue liante n'est pas APPROVE — merge bloqué.")
        return 1
    print("GATE OK : toutes les revues liantes sont APPROVE 3/3.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
