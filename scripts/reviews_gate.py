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

#434 — deux modes supplémentaires, OPT-IN par drapeau (le comportement PAR DÉFAUT, sans
drapeau, reste STRICTEMENT identique à avant cette story) :

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
        try:
            prior = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
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
    mode: str | None = None,
    runner: GitRunner | None = None,
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
    if exiger_recu_courant:
        try:
            etat_git = revue._etat_git_reel(base_ref, "HEAD", runner=execute)
        except (OSError, ValueError, subprocess.CalledProcessError) as error:
            return False, [f"ECHEC : état git courant inaccessible : {error}"]

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

        result = revue.tally(verdicts)
        if result.get("result") != "APPROVE":
            ok = False
            report.append(
                f"ECHEC {entry} : dépouillement = {result.get('result')} "
                f"({result.get('reason', '')})"
            )
        else:
            report.append(
                f"OK    {entry} : APPROVE {result.get('reason', '')} "
                f"vendors {result.get('vendors')}"
            )

        receipt_path = directory / "RECU.json"

        if exiger_recu_courant and receipt_path.is_file():
            try:
                receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                ok = False
                report.append(f"ECHEC {entry} : reçu illisible : {error}")
                continue
            receipt_result = revue.verifier_recu(receipt, verdicts, etat_git)
            if receipt_result.get("result") == "APPROVE":
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
                report.append(
                    f"info  {entry} : reçu invalide = {receipt_result.get('result')} "
                    f"({receipt_result.get('reason', '')}) — ignoré si un autre reçu couvre "
                    f"le changement courant"
                )

        if mode == "archive" and receipt_path.is_file():
            try:
                receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                commit = receipt["head_commit"]
                # Anti-injection : commit vient d'un RECU.json lu au disque, même garde que
                # les refs de _diff_canonique/_etat_git_reel (objection mineure revue scellée
                # RC1-004-PR497-v2, DeepSeek-V4-Pro).
                revue._validate_git_ref(commit)
            except (OSError, json.JSONDecodeError, KeyError, ValueError, TypeError) as error:
                # TypeError : RECU.json valide en JSON mais pas un objet (ex. liste/null) —
                # receipt["head_commit"] lèverait sinon une exception non gérée (objection
                # mineure round 3, DeepSeek-V4-Pro).
                ok = False
                report.append(f"ECHEC {entry} : reçu archive illisible : {error}")
                continue
            if not _is_ancestor(commit, execute):
                ok = False
                report.append(f"ECHEC {entry} : reçu pointe un commit jamais fusionné")

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
    ap.add_argument("--mode", choices=("archive",))
    args = ap.parse_args(argv)

    ok, report = check(
        Path(args.manifest),
        Path(args.reviews_root),
        exiger_recu_courant=args.exiger_recu_courant,
        base_ref=args.base_ref,
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
