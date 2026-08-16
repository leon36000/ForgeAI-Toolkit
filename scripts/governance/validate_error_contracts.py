#!/usr/bin/env python3
"""Valide l'inventaire des contrats de gestion d'erreurs et rend son rapport Markdown."""
from __future__ import annotations

import argparse
import ast
import datetime as dt
import json
import sys
from pathlib import Path

CHAMPS_OBLIGATOIRES = {
    "id",
    "site",
    "exception_types",
    "risk_paths",
    "disposition",
    "behavior_contract",
    "logging",
    "owner",
    "justification",
    "compensating_test",
    "compensating_test_reason",
    "review_due",
    "accepted_risk",
}

DISPOSITIONS_VALIDES = {
    "JUSTIFIED",
    "FIXED",
    "SPLIT_TO_NEW_ISSUE",
    "BLOCKED",
}


def _lire_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _date(value: str) -> dt.date:
    return dt.date.fromisoformat(value)


def _horizon(inventaire: dict) -> int:
    horizon = inventaire.get("review_horizon")
    if not isinstance(horizon, dict):
        raise ValueError("review_horizon absent ou invalide")
    jours = horizon.get("days")
    if not isinstance(jours, int) or isinstance(jours, bool) or jours < 0:
        raise ValueError("review_horizon.days doit être un entier positif ou nul")
    return jours


def _test_compensatoire_existe(root: Path, test_compensatoire: object) -> bool:
    if not isinstance(test_compensatoire, str):
        return False
    chemin = test_compensatoire.split("::", 1)[0]
    if not chemin:
        return False
    root_resolu = root.resolve()
    candidat = (root_resolu / chemin).resolve()
    try:
        candidat.relative_to(root_resolu)
    except ValueError:
        return False
    return candidat.is_file()


def _valider_structure_globale(inventaire: dict) -> tuple[list[str], int, int]:
    erreurs: list[str] = []
    if "schema" not in inventaire or not isinstance(inventaire["schema"], str):
        erreurs.append("champ 'schema' absent ou invalide")

    review_horizon = inventaire.get("review_horizon")
    if not isinstance(review_horizon, dict) or not isinstance(
        review_horizon.get("days"), int
    ):
        erreurs.append("champ 'review_horizon' absent ou invalide (doit contenir 'days': int)")

    coverage = inventaire.get("coverage")
    if not isinstance(coverage, dict):
        erreurs.append("champ 'coverage' absent ou invalide")
        contracted, floor = 0, 0
    else:
        contracted = coverage.get("contracted", 0)
        floor = coverage.get("floor", 0)
        if not isinstance(contracted, int) or isinstance(contracted, bool) or contracted < 0:
            erreurs.append("coverage.contracted doit être un entier positif ou nul")
        if not isinstance(floor, int) or isinstance(floor, bool) or floor < 0:
            erreurs.append("coverage.floor doit être un entier positif ou nul")

    contracts = inventaire.get("contracts")
    if not isinstance(contracts, list):
        erreurs.append("champ 'contracts' absent ou invalide (doit être une liste)")

    return erreurs, contracted, floor


def _erreurs_horizon(inventaire: dict, aujourd_hui: dt.date) -> tuple[list[str], dt.date]:
    try:
        horizon_jours = _horizon(inventaire)
    except ValueError as erreur:
        return [str(erreur)], aujourd_hui
    return [], aujourd_hui + dt.timedelta(days=horizon_jours)


def _erreurs_identifiants_dupliques(entrees: list[dict]) -> list[str]:
    ids = [entree.get("id") for entree in entrees if isinstance(entree, dict)]
    return [
        f"identifiant de contrat dupliqué : {identifiant}"
        for identifiant in sorted({item for item in ids if item and ids.count(item) > 1})
    ]


def _erreurs_date_revision(
    identifiant: object,
    review_due: object,
    aujourd_hui: dt.date,
    date_maximale: dt.date,
) -> list[str]:
    try:
        echeance = _date(str(review_due))
    except (TypeError, ValueError):
        return [f"{identifiant} : review_due doit être une date ISO valide"]

    erreurs: list[str] = []
    if echeance < aujourd_hui:
        erreurs.append(f"{identifiant} : review_due dépassée ({echeance.isoformat()})")
    if echeance > date_maximale:
        erreurs.append(
            f"{identifiant} : review_due dépasse l'horizon de révision "
            f"({echeance.isoformat()} > {date_maximale.isoformat()})"
        )
    return erreurs


def _erreurs_test_et_disposition(root: Path, entree: dict, identifiant: str) -> list[str]:
    erreurs: list[str] = []
    test = entree.get("compensating_test")
    reason = entree.get("compensating_test_reason")
    disposition = entree.get("disposition")

    a_test = test is not None and isinstance(test, str) and bool(test.strip())
    a_reason = reason is not None and isinstance(reason, str) and bool(reason.strip())

    if not a_test and not a_reason:
        erreurs.append(f"{identifiant} : ni compensating_test ni compensating_test_reason")
    elif a_test and a_reason:
        erreurs.append(
            f"{identifiant} : compensating_test ET compensating_test_reason tous les deux renseignés (un seul attendu)"
        )
    elif a_test:
        if not _test_compensatoire_existe(root, test):
            erreurs.append(f"{identifiant} : test compensatoire absent du dépôt : {test}")

    if disposition == "FIXED" and not a_test:
        erreurs.append(
            f"{identifiant} : disposition FIXED sans compensating_test "
            "(une justification d'absence de test est acceptée seulement pour JUSTIFIED/SPLIT_TO_NEW_ISSUE/BLOCKED)"
        )

    return erreurs


def _extraire_types_exception_ast(node: ast.ExceptHandler) -> list[str]:
    if node.type is None:
        return []
    if isinstance(node.type, ast.Tuple):
        return [ast.unparse(elt).strip() for elt in node.type.elts]
    return [ast.unparse(node.type).strip()]


def _verifier_site_ast(
    root: Path,
    entree: dict,
    identifiant: str,
    ast_cache: dict[Path, ast.AST | None],
) -> list[str]:
    site = entree.get("site")
    if not isinstance(site, dict):
        return [f"{identifiant} : site doit être un objet dict"]

    path_rel = site.get("path")
    line = site.get("line")
    if not isinstance(path_rel, str) or not isinstance(line, int):
        return [f"{identifiant} : site.path (str) et site.line (int) requis"]

    fichier_source = (root / path_rel).resolve()
    if fichier_source not in ast_cache:
        if not fichier_source.is_file():
            ast_cache[fichier_source] = None
        else:
            try:
                code = fichier_source.read_text(encoding="utf-8")
                ast_cache[fichier_source] = ast.parse(code, filename=str(fichier_source))
            except (OSError, SyntaxError):
                ast_cache[fichier_source] = None

    arbre = ast_cache[fichier_source]
    if arbre is None:
        return [
            f"{identifiant} : site introuvable ({path_rel}:{line}) — le code a bougé, régénérer l'entrée"
        ]

    handler_trouve: ast.ExceptHandler | None = None
    for node in ast.walk(arbre):
        if isinstance(node, ast.ExceptHandler) and node.lineno == line:
            handler_trouve = node
            break

    if handler_trouve is None:
        return [
            f"{identifiant} : site introuvable ({path_rel}:{line}) — le code a bougé, régénérer l'entrée"
        ]

    types_reels = _extraire_types_exception_ast(handler_trouve)
    types_attendus = entree.get("exception_types")
    if types_reels != types_attendus:
        return [
            f"{identifiant} : types d'exception ont dérivé (attendu {types_attendus}, trouvé {types_reels})"
        ]

    return []


def _erreurs_entree(
    root: Path,
    entree: dict,
    aujourd_hui: dt.date,
    date_maximale: dt.date,
    ast_cache: dict[Path, ast.AST | None],
) -> list[str]:
    identifiant = entree.get("id", "<sans id>")
    if not isinstance(identifiant, str):
        identifiant = "<sans id>"

    manquants = sorted(CHAMPS_OBLIGATOIRES - set(entree))
    if manquants:
        return [f"{identifiant} : champs obligatoires absents : {', '.join(manquants)}"]

    erreurs: list[str] = []

    disposition = entree.get("disposition")
    if disposition not in DISPOSITIONS_VALIDES:
        erreurs.append(f"{identifiant} : disposition invalide : {disposition}")

    for champ in ("behavior_contract", "logging", "owner", "justification", "accepted_risk"):
        valeur = entree.get(champ)
        if not isinstance(valeur, str) or not valeur.strip():
            erreurs.append(f"{identifiant} : champ '{champ}' doit être une chaîne non vide")

    if not isinstance(entree.get("risk_paths"), list):
        erreurs.append(f"{identifiant} : champ 'risk_paths' doit être une liste")

    if not isinstance(entree.get("exception_types"), list) or not entree.get("exception_types"):
        erreurs.append(f"{identifiant} : champ 'exception_types' doit être une liste non vide")

    erreurs.extend(
        _erreurs_date_revision(identifiant, entree.get("review_due"), aujourd_hui, date_maximale)
    )
    erreurs.extend(_erreurs_test_et_disposition(root, entree, identifiant))
    erreurs.extend(_verifier_site_ast(root, entree, identifiant, ast_cache))

    return erreurs


def valider(root: Path, *, aujourd_hui: dt.date | None = None) -> list[str]:
    aujourd_hui = aujourd_hui or dt.date.today()
    inventaire_path = root / "governance" / "error-handling-contracts.json"
    if not inventaire_path.is_file():
        return [f"fichier de gouvernance introuvable : {inventaire_path}"]

    try:
        inventaire = _lire_json(inventaire_path)
    except Exception as exc:
        return [f"JSON invalide dans {inventaire_path} : {exc}"]

    erreurs_struct, contracted, floor = _valider_structure_globale(inventaire)
    if erreurs_struct:
        return erreurs_struct

    contracts = inventaire.get("contracts", [])
    nb_contrats = len(contracts)

    erreurs: list[str] = []
    if contracted != nb_contrats:
        erreurs.append(
            f"coverage.contracted ({contracted}) ne correspond pas au nombre réel de contrats ({nb_contrats})"
        )

    if nb_contrats < floor:
        erreurs.append(
            f"couverture sous le plancher : {nb_contrats} contrats pour un plancher de {floor}"
        )

    erreurs_horizon, date_maximale = _erreurs_horizon(inventaire, aujourd_hui)
    erreurs.extend(erreurs_horizon)
    erreurs.extend(_erreurs_identifiants_dupliques(contracts))

    ast_cache: dict[Path, ast.AST | None] = {}
    for entree in contracts:
        if isinstance(entree, dict):
            erreurs.extend(_erreurs_entree(root, entree, aujourd_hui, date_maximale, ast_cache))

    return erreurs


def rendre(root: Path) -> str:
    inventaire = _lire_json(root / "governance" / "error-handling-contracts.json")
    lignes = [
        "<!-- Généré par scripts/governance/validate_error_contracts.py --render ; ne pas éditer à la main. -->",
        "# Contrats de gestion d'erreurs et risques acceptés",
        "",
        "Ce rapport inventorie les contrats de gestion d'erreurs (sites `except`) sous gouvernance. Les échéances sont révisées tous les 180 jours.",
        "",
        "| Disposition | Site | Exception(s) | Chemins à risque | Propriétaire | Risque accepté | Test compensatoire | Révision |",
        "|---|---|---|---|---|---|---|---|",
    ]

    contrats_tries = sorted(
        inventaire.get("contracts", []),
        key=lambda c: (
            c.get("site", {}).get("path", ""),
            c.get("site", {}).get("line", 0),
        ),
    )

    for entree in contrats_tries:
        site = entree.get("site", {})
        site_str = f"{site.get('path', '')}:{site.get('line', '')}"
        exceptions = ", ".join(entree.get("exception_types", [])) or "—"
        risk_paths = ", ".join(entree.get("risk_paths", [])) or "—"
        test = entree.get("compensating_test") or entree.get(
            "compensating_test_reason", "Aucun"
        )
        cellules = [
            str(entree.get("disposition", "—")),
            site_str,
            exceptions,
            risk_paths,
            str(entree.get("owner", "—")),
            str(entree.get("accepted_risk", "—")),
            str(test),
            str(entree.get("review_due", "—")),
        ]
        lignes.append(
            "| " + " | ".join(cellule.replace("|", "\\|").replace("\n", "<br>") for cellule in cellules) + " |"
        )

    return "\n".join(lignes) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--render", action="store_true", help="écrit le rapport Markdown généré"
    )
    args = parser.parse_args()
    root = args.root.resolve()
    erreurs = valider(root)
    if erreurs:
        for erreur in erreurs:
            print(f"ERREUR: {erreur}", file=sys.stderr)
        raise SystemExit(1)
    if args.render:
        cible = root / "governance" / "ERROR-HANDLING-CONTRACTS.md"
        cible.write_text(rendre(root), encoding="utf-8")
        print(f"OK: rapport généré : {cible.relative_to(root)}")
    else:
        print("OK: inventaire des contrats d'erreur valide")


if __name__ == "__main__":
    main()
