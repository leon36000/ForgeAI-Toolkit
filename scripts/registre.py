#!/usr/bin/env python3
"""Interface CLI/CI du registre hash-chaîné ForgeAI."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from forgeai.core.registre_completude import anomalies, charger  # noqa: E402
from forgeai.core.registre_ancrage import (  # noqa: E402
    anomalies_ancrage,
    anomalies_seq,
    checkpoint_de,
)
from forgeai.core.registre import (  # noqa: E402,F401
    GENESIS,
    _entry_hash,
    _read_entries,
    append,
    main,
    verify,
)


def _lire_entrees(fichier: str | Path) -> list[dict]:
    """Lit un registre et transforme toute lecture invalide en erreur explicite."""
    try:
        entrees = _read_entries(Path(fichier))
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as erreur:
        raise ValueError(f"registre illisible {str(fichier)!r} : {erreur}") from erreur

    if not isinstance(entrees, list):
        raise ValueError(
            f"registre invalide {str(fichier)!r} : une liste d'entrees est requise"
        )

    return entrees


def _charger_reference_git(ref: str, dossier: str) -> dict[str, list[dict]]:
    """Charge les registres JSONL d'une reference git sans utiliser de shell."""
    resultat_liste = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", ref, "--", dossier],
        check=True,
        capture_output=True,
        text=True,
    )

    chemins = sorted(
        chemin
        for chemin in resultat_liste.stdout.splitlines()
        if chemin.endswith(".jsonl")
    )

    reference: dict[str, list[dict]] = {}
    for chemin in chemins:
        resultat_show = subprocess.run(
            ["git", "show", f"{ref}:{chemin}"],
            check=True,
            capture_output=True,
            text=True,
        )

        entrees: list[dict] = []
        for numero_ligne, ligne in enumerate(resultat_show.stdout.splitlines(), start=1):
            try:
                entree = json.loads(ligne)
            except json.JSONDecodeError as erreur:
                raise ValueError(
                    f"registre de reference illisible {chemin!r}, "
                    f"ligne {numero_ligne} : {erreur.msg}"
                ) from erreur
            entrees.append(entree)

        reference[Path(chemin).name] = entrees

    return reference


def _cmd_append(arguments: argparse.Namespace) -> int:
    try:
        payload = json.loads(arguments.payload)
    except json.JSONDecodeError as erreur:
        print(f"payload JSON invalide : {erreur.msg}", file=sys.stderr)
        return 1

    try:
        entree = append(
            Path(arguments.fichier),
            arguments.type,
            arguments.actor,
            payload,
            key_path=Path(arguments.key) if arguments.key else None,
        )
    except (OSError, ValueError, TypeError, KeyError) as erreur:
        print(f"append impossible : {erreur}", file=sys.stderr)
        return 1

    print(json.dumps(entree, ensure_ascii=False, sort_keys=True))
    return 0


def _cmd_verify(arguments: argparse.Namespace) -> int:
    anomalies_trouvees: list[str] = []

    for fichier in arguments.fichier:
        try:
            erreurs = verify(
                Path(fichier), key_path=Path(arguments.key) if arguments.key else None
            )
        except (OSError, ValueError, TypeError, KeyError) as erreur:
            anomalies_trouvees.append(f"{fichier} : verification impossible : {erreur}")
            continue

        # `verify` renvoie UN message d'erreur ou None — jamais une liste. L'itérer
        # levait un TypeError avalé par le `except` ci-dessus, ce qui rendait le gate
        # `gates.yml:55` rouge en permanence pour la mauvaise raison.
        # Format de sortie HISTORIQUE, préservé à la lettre : `tests/test_guard_fs.py` assertionne
        # sur la chaîne « chaîne intègre ». Une réécriture de CLI doit conserver la sortie
        # OBSERVABLE, pas seulement le code de retour — sinon elle casse des appelants muets.
        if erreurs is not None:
            anomalies_trouvees.append(f"{fichier} : {erreurs}")
            print(f"ECHEC {fichier}: {erreurs}")
        else:
            print(f"OK {fichier}: {len(_lire_entrees(fichier))} entrées, chaîne intègre")

    return 1 if anomalies_trouvees else 0


def _resoudre_base_reference(ref: str, chemin_base: str) -> tuple[dict | None, str]:
    """Résout une base de référence depuis un commit git déjà accessible."""
    try:
        subprocess.run(
            ["git", "rev-parse", "--verify", f"{ref}^{{commit}}"],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as erreur:
        raise RuntimeError(
            f"git indisponible : impossible de résoudre la référence {ref!r} ; "
            "le job CI doit utiliser fetch-depth: 0."
        ) from erreur
    except subprocess.CalledProcessError as erreur:
        raise RuntimeError(
            f"référence git {ref!r} inaccessible : le job CI doit utiliser "
            "fetch-depth: 0 pour disposer de l'historique."
        ) from erreur

    try:
        resultat = subprocess.run(
            ["git", "show", f"{ref}:{chemin_base}"],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as erreur:
        raise RuntimeError(
            "git indisponible : impossible de lire la base de référence ; "
            "le job CI doit utiliser fetch-depth: 0."
        ) from erreur
    except subprocess.CalledProcessError:
        return (
            None,
            f"base de référence {chemin_base!r} absente de {ref!r} : la base est "
            "introduite pour la première fois, le contrôle de non-croissance "
            "est inapplicable.",
        )

    try:
        base = json.loads(resultat.stdout)
    except (json.JSONDecodeError, UnicodeError) as erreur:
        raise RuntimeError(
            f"base de référence git invalide {chemin_base!r} sur {ref!r} : {erreur}"
        ) from erreur

    if not isinstance(base, dict):
        raise RuntimeError(
            f"base de référence git invalide {chemin_base!r} sur {ref!r} : "
            "la base doit être un objet JSON."
        )

    return base, ""


def _cmd_completude(arguments: argparse.Namespace) -> int:
    from forgeai.core.registre_ancrage import anomalies_base

    chemin_base = getattr(arguments, "base", None)
    chemin_reference = getattr(arguments, "base_reference", None)
    reference_base_git: dict | None = None

    if (
        chemin_base
        and not chemin_reference
        and getattr(arguments, "base_ref_git", None)
    ):
        try:
            reference_base_git, message_reference = _resoudre_base_reference(
                arguments.base_ref_git,
                chemin_base,
            )
        except RuntimeError as erreur:
            print(str(erreur), file=sys.stderr)
            return 1

        if message_reference:
            print(message_reference)

    anomalies_reelles: list[dict[str, Any]] = []
    rapport_total: list[dict[str, Any]] = []

    for fichier in arguments.fichier:
        try:
            rapport = anomalies(charger(fichier))
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as erreur:
            print(f"registre illisible {fichier!r} : {erreur}", file=sys.stderr)
            return 1

        for anomalie in rapport:
            print(
                f"[{anomalie['type']}] seq={anomalie['seq']} "
                f"story={anomalie['story']}: {anomalie['raison']}"
            )
            rapport_total.append(anomalie)

            champ = anomalie.get("champ")
            if champ is None:
                champ = anomalie.get("raison")

            anomalies_reelles.append(
                {
                    "fichier": Path(fichier).name,
                    "seq": anomalie.get("seq"),
                    "type": anomalie.get("type"),
                    "champ": champ,
                }
            )

    if not chemin_base:
        print(f"— {len(rapport_total)} anomalie(s) de completude")
        return 1 if rapport_total else 0

    def charger_base(chemin: str | Path, libelle: str) -> Any:
        try:
            with Path(chemin).open("r", encoding="utf-8") as fichier_base:
                return json.load(fichier_base)
        except (OSError, UnicodeError, ValueError, TypeError) as erreur:
            raise ValueError(
                f"{libelle} illisible {str(chemin)!r} : {erreur}"
            ) from erreur

    try:
        base = charger_base(chemin_base, "base")
        if not isinstance(base, dict):
            raise ValueError("la base doit etre un objet JSON")
        identites_base = base.get("identites")
        if not isinstance(identites_base, list):
            raise ValueError("la base doit contenir une liste 'identites'")

        reference_base = (
            charger_base(chemin_reference, "base de reference")
            if chemin_reference
            else reference_base_git
        )
        messages_base = anomalies_base(
            base,
            reference_base,
            anomalies_reelles,
        )
    except (OSError, UnicodeError, ValueError, TypeError, KeyError) as erreur:
        print(f"validation de la base impossible : {erreur}", file=sys.stderr)
        return 1

    for message in messages_base:
        print(message)

    anomalies_nouvelles: list[tuple[dict[str, Any], dict[str, Any]]] = []
    anomalies_couvertes = 0
    for anomalie_reelle, anomalie_affichage in zip(
        anomalies_reelles, rapport_total
    ):
        if anomalie_reelle in identites_base:
            anomalies_couvertes += 1
        else:
            anomalies_nouvelles.append((anomalie_reelle, anomalie_affichage))

    for _, anomalie in anomalies_nouvelles:
        print(
            f"[{anomalie['type']}] seq={anomalie['seq']} "
            f"story={anomalie['story']}: {anomalie['raison']}"
        )

    print(
        f"— {anomalies_couvertes} anomalie(s) couvertes par la base, "
        f"{len(anomalies_nouvelles)} nouvelle(s)"
    )
    return 1 if messages_base or anomalies_nouvelles else 0


def _cmd_checkpoint(arguments: argparse.Namespace) -> int:
    try:
        entrees = _lire_entrees(arguments.fichier)
        checkpoint = checkpoint_de(entrees, arguments.registre)
    except (OSError, ValueError, TypeError, KeyError) as erreur:
        print(f"checkpoint impossible : {erreur}", file=sys.stderr)
        return 1

    print(json.dumps(checkpoint, ensure_ascii=False, sort_keys=True))
    return 0


def _cmd_ancrage(arguments: argparse.Namespace) -> int:
    dossier = Path(arguments.dossier)

    try:
        courant = {
            chemin.name: _lire_entrees(chemin)
            for chemin in sorted(dossier.glob("*.jsonl"))
        }
    except ValueError as erreur:
        print(str(erreur), file=sys.stderr)
        return 1

    try:
        reference = _charger_reference_git(arguments.ref, arguments.dossier)
    except (subprocess.CalledProcessError, FileNotFoundError):
        if not arguments.permettre_reference_absente:
            print(
                f"reference git {arguments.ref!r} inaccessible : le job CI doit "
                "utiliser fetch-depth: 0 pour disposer de l'historique.",
                file=sys.stderr,
            )
            return 1
        print(
            f"reference git {arguments.ref!r} inaccessible, bootstrap local "
            "autorise par --permettre-reference-absente.",
            file=sys.stderr,
        )
        reference = {}
    except ValueError as erreur:
        print(str(erreur), file=sys.stderr)
        return 1

    rapport = anomalies_ancrage(reference, courant)
    for registre in sorted(courant):
        for anomalie in anomalies_seq(courant[registre]):
            rapport.append(f"{registre} : {anomalie}")

    for anomalie in rapport:
        print(anomalie)
    print(f"— {len(rapport)} anomalie(s) d'ancrage")
    return 1 if rapport else 0


def main_cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog=Path(sys.argv[0]).name,
        description="Outils CLI/CI des registres hash-chaines ForgeAI.",
    )
    sous_commandes = parser.add_subparsers(dest="commande", required=True)

    parser_append = sous_commandes.add_parser(
        "append",
        help="ajoute une entree au registre",
    )
    parser_append.add_argument("fichier", help="chemin du registre JSONL")
    parser_append.add_argument("--type", required=True, help="type de l'entree")
    parser_append.add_argument("--actor", required=True, help="acteur de l'entree")
    # Nom historique EXACT : `tests/test_registre_concurrence.py` invoque `--payload-json`,
    # et `--payload` continue de fonctionner comme abreviation non ambigue d'argparse.
    parser_append.add_argument(
        "--payload-json", dest="payload", default="{}", help="payload JSON (defaut: {})"
    )
    parser_append.add_argument("--key", help="cle HMAC optionnelle")
    parser_append.set_defaults(fonction=_cmd_append)

    parser_verify = sous_commandes.add_parser(
        "verify",
        help="verifie l'integrite d'un ou plusieurs registres",
    )
    parser_verify.add_argument("fichier", nargs="+", help="registre(s) JSONL")
    parser_verify.add_argument("--key", help="cle HMAC optionnelle")
    parser_verify.set_defaults(fonction=_cmd_verify)

    parser_completude = sous_commandes.add_parser(
        "completude",
        help="rapporte les anomalies de completude",
    )
    parser_completude.add_argument("fichier", nargs="+", help="registre(s) JSONL")
    parser_completude.add_argument(
        "--base",
        help="fichier JSON de base de reference des anomalies",
    )
    parser_completude.add_argument(
        "--base-reference",
        help="fichier JSON de la base telle qu'elle existe sur origin/main",
    )
    parser_completude.add_argument(
        "--base-ref-git",
        metavar="REF",
        help=(
            "resout la base de reference depuis git (ex. origin/main) pour verifier la "
            "non-croissance ; echec dur si la reference est inaccessible"
        ),
    )
    parser_completude.set_defaults(fonction=_cmd_completude)

    parser_checkpoint = sous_commandes.add_parser(
        "checkpoint",
        help="produit le checkpoint du dernier etat d'un registre",
    )
    parser_checkpoint.add_argument("fichier", help="chemin du registre JSONL")
    parser_checkpoint.add_argument("--registre", required=True, help="nom du registre")
    parser_checkpoint.set_defaults(fonction=_cmd_checkpoint)

    parser_ancrage = sous_commandes.add_parser(
        "ancrage",
        help="controle la conservation des registres contre une reference git",
    )
    parser_ancrage.add_argument(
        "--dossier",
        default="evidence/registres",
        help="dossier contenant les registres JSONL (defaut : evidence/registres)",
    )
    parser_ancrage.add_argument(
        "--ref",
        default="origin/main",
        help="reference git deja mergee (defaut : origin/main)",
    )
    parser_ancrage.add_argument(
        "--permettre-reference-absente",
        action="store_true",
        help="autorise le bootstrap local sans reference git ; jamais en CI",
    )
    parser_ancrage.set_defaults(fonction=_cmd_ancrage)

    arguments = parser.parse_args(argv)
    return arguments.fonction(arguments)


if __name__ == "__main__":
    raise SystemExit(main_cli())
