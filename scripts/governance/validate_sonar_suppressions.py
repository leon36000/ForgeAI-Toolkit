#!/usr/bin/env python3
"""Valide l'inventaire des suppressions Sonar et rend son rapport Markdown."""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import re
import sys
import tokenize
from pathlib import Path

NOSONAR_MARKER = re.compile(r"\bNOSONAR\b")
NOSONAR_TARGETED = re.compile(
    r"\bNOSONAR\(\s*([A-Za-z][A-Za-z0-9_.:-]*(?:\s*,\s*[A-Za-z][A-Za-z0-9_.:-]*)*)\s*\)(?:\s|$)"
)
NOSONAR_LEGACY_RULE = re.compile(
    r"\bNOSONAR\s+([A-Za-z][A-Za-z0-9_.:-]*)(?:\s|$)"
)
PROPERTIES = (
    "sonar.exclusions",
    "sonar.test.exclusions",
    "sonar.coverage.exclusions",
)


def _lire_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _proprietes(path: Path) -> dict[str, str]:
    resultat: dict[str, str] = {}
    for ligne in path.read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#") or "=" not in ligne:
            continue
        cle, valeur = ligne.split("=", 1)
        resultat[cle.strip()] = valeur.strip()
    return resultat


def _sources_python(root: Path, props: dict[str, str]) -> list[Path]:
    paths: list[Path] = []
    for source in props.get("sonar.sources", "").split(","):
        source = source.strip()
        if not source:
            continue
        candidate = root / source
        if candidate.is_file() and candidate.suffix == ".py":
            paths.append(candidate)
        elif candidate.is_dir():
            paths.extend(candidate.rglob("*.py"))
    return sorted(set(paths))


def _commentaires_nosonar(path: Path) -> list[tuple[int, str]]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    result: list[tuple[int, str]] = []
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        if token.type != tokenize.COMMENT:
            continue
        line_number, column = token.start
        if lines[line_number - 1][:column].strip():
            result.append((line_number, token.string))
    return result


def _suppression_inline(relatif: str, numero: int, regle: str | None, **extra: object) -> dict:
    suffixe = regle if regle is not None else "NU"
    resultat: dict = {
        "id": f"inline:{relatif}:{numero}:{suffixe}",
        "kind": "inline",
        "rule": regle,
        "scope": "line",
        "sites": [{"path": relatif, "line": numero}],
    }
    resultat.update(extra)
    return resultat


def suppressions_reelles(root: Path) -> list[dict]:
    reelles: list[dict] = []
    props = _proprietes(root / "sonar-project.properties")
    validator = (root / "scripts" / "governance" / "validate_sonar_suppressions.py").resolve()

    for path in _sources_python(root, props):
        if path.resolve() == validator:
            continue
        if any(part in {".git", "__pycache__"} for part in path.parts):
            continue
        relatif = path.relative_to(root).as_posix()
        for numero, commentaire in _commentaires_nosonar(path):
            if not NOSONAR_MARKER.search(commentaire):
                continue
            ciblee = NOSONAR_TARGETED.search(commentaire)
            if ciblee:
                for regle in (item.strip() for item in ciblee.group(1).split(",")):
                    reelles.append(_suppression_inline(relatif, numero, regle))
                continue
            legacy = NOSONAR_LEGACY_RULE.search(commentaire)
            if legacy:
                reelles.append(
                    _suppression_inline(
                        relatif,
                        numero,
                        None,
                        nue=True,
                        legacy_rule=legacy.group(1),
                    )
                )
                continue
            reelles.append(_suppression_inline(relatif, numero, None, nue=True))

    identifiants = [
        item.strip()
        for item in props.get("sonar.issue.ignore.multicriteria", "").split(",")
        if item.strip()
    ]
    for identifiant in identifiants:
        regle = props.get(f"sonar.issue.ignore.multicriteria.{identifiant}.ruleKey")
        resource = props.get(f"sonar.issue.ignore.multicriteria.{identifiant}.resourceKey")
        if regle is None or resource is None:
            reelles.append(
                {
                    "id": f"properties-multicriteria:{identifiant}:INCOMPLET",
                    "kind": "properties-multicriteria",
                    "rule": regle,
                    "scope": "file",
                    "sites": [{"path": resource}] if resource else [],
                    "incomplete": True,
                }
            )
        else:
            reelles.append(
                {
                    "id": f"properties-multicriteria:{identifiant}",
                    "kind": "properties-multicriteria",
                    "rule": regle,
                    "scope": "file",
                    "sites": [{"path": resource}],
                }
            )

    for cle in PROPERTIES:
        kind = "coverage-exclusion" if cle == "sonar.coverage.exclusions" else "analysis-exclusion"
        for motif in (item.strip() for item in props.get(cle, "").split(",")):
            if motif:
                reelles.append(
                    {
                        "id": f"{kind}:{cle}:{motif}",
                        "kind": kind,
                        "rule": None,
                        "scope": "glob",
                        "sites": [{"path": motif}],
                    }
                )
    return reelles


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


def valider(root: Path, *, aujourd_hui: dt.date | None = None) -> list[str]:
    aujourd_hui = aujourd_hui or dt.date.today()
    inventaire = _lire_json(root / "governance" / "sonar-suppressions.json")
    entrees = inventaire.get("suppressions", [])
    erreurs: list[str] = []

    try:
        horizon_jours = _horizon(inventaire)
    except ValueError as erreur:
        erreurs.append(str(erreur))
        horizon_jours = 0
    date_maximale = aujourd_hui + dt.timedelta(days=horizon_jours)

    ids = [entree.get("id") for entree in entrees]
    for identifiant in sorted({item for item in ids if ids.count(item) > 1}):
        erreurs.append(f"identifiant d'inventaire dupliqué : {identifiant}")

    reelles = suppressions_reelles(root)
    reels_par_id = {entree["id"]: entree for entree in reelles}
    inventaire_par_id = {entree.get("id"): entree for entree in entrees}

    for entree in reelles:
        if entree.get("nue"):
            site = entree["sites"][0]
            legacy_rule = entree.get("legacy_rule")
            if legacy_rule:
                erreurs.append(
                    f"NOSONAR ciblé mal formé : {site['path']}:{site['line']} ; "
                    f"utilisez # NOSONAR({legacy_rule})"
                )
            else:
                erreurs.append(
                    f"NOSONAR nu interdit : {site['path']}:{site['line']} ; indiquez la règle exacte"
                )
        if entree.get("incomplete"):
            erreurs.append(f"suppression multicritère incomplète : {entree['id']}")
        if entree["id"] not in inventaire_par_id:
            erreurs.append(f"suppression réelle non inventoriée : {entree['id']}")

    for identifiant in inventaire_par_id:
        if identifiant not in reels_par_id:
            erreurs.append(f"entrée d'inventaire fossile : {identifiant}")

    champs = {
        "id",
        "kind",
        "rule",
        "scope",
        "sites",
        "owner",
        "justification",
        "compensating_test",
        "review_due",
        "accepted_risk",
    }
    for entree in entrees:
        identifiant = entree.get("id", "<sans id>")
        manquants = sorted(champs - set(entree))
        if manquants:
            erreurs.append(f"{identifiant} : champs obligatoires absents : {', '.join(manquants)}")
            continue
        try:
            echeance = _date(entree["review_due"])
        except (TypeError, ValueError):
            erreurs.append(f"{identifiant} : review_due doit être une date ISO valide")
            continue
        if echeance < aujourd_hui:
            erreurs.append(f"{identifiant} : review_due dépassée ({echeance.isoformat()})")
        if echeance > date_maximale:
            erreurs.append(
                f"{identifiant} : review_due dépasse l'horizon de révision "
                f"({echeance.isoformat()} > {date_maximale.isoformat()})"
            )
        test_compensatoire = entree["compensating_test"]
        if test_compensatoire is not None and not _test_compensatoire_existe(
            root, test_compensatoire
        ):
            erreurs.append(
                f"{identifiant} : test compensatoire absent du dépôt : {test_compensatoire}"
            )
        if entree["scope"] in {"file", "glob"} and not test_compensatoire:
            raison = entree.get("compensating_test_reason", "")
            if "non-réductible" not in raison.lower():
                erreurs.append(
                    f"{identifiant} : portée {entree['scope']} sans test compensatoire "
                    "ni justification explicite de non-réductibilité"
                )
    return erreurs


def rendre(root: Path) -> str:
    inventaire = _lire_json(root / "governance" / "sonar-suppressions.json")
    lignes = [
        "<!-- Généré par scripts/governance/validate_sonar_suppressions.py --render ; ne pas éditer à la main. -->",
        "# Suppressions Sonar et risques acceptés",
        "",
        "Ce rapport inventorie les suppressions actives. Les échéances sont révisées tous les 180 jours.",
        "",
        "Les suppressions inline ciblées utilisent obligatoirement la syntaxe Sonar `# NOSONAR(Sxxxx)`. La forme `# NOSONAR Sxxxx` est une suppression nue : le texte après `NOSONAR` n'est pas une clé de règle. Source : https://community.sonarsource.com/t/python-issue-suppression-improvements-nosonar-and-new-rules/145017",
        "",
        "La réduction de S2612 dans `openbao_flow.py` est désormais au site : une nouvelle occurrence ailleurs dans ce fichier n'est plus masquée.",
        "",
        "| Règle | Portée | Site | Propriétaire | Risque accepté | Test compensatoire | Révision |",
        "|---|---|---|---|---|---|---|",
    ]
    for entree in inventaire["suppressions"]:
        sites = "<br>".join(
            f"{site['path']}:{site['line']}" if "line" in site else site["path"]
            for site in entree["sites"]
        )
        test = entree["compensating_test"] or entree.get(
            "compensating_test_reason", "Aucun"
        )
        cellules = [
            str(entree["rule"] if entree["rule"] is not None else "—"),
            entree["scope"],
            sites,
            entree["owner"],
            entree["accepted_risk"],
            test,
            entree["review_due"],
        ]
        lignes.append("| " + " | ".join(cellule.replace("|", "\\|") for cellule in cellules) + " |")
    return "\n".join(lignes) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--render", action="store_true", help="écrit le rapport Markdown généré")
    args = parser.parse_args()
    root = args.root.resolve()
    erreurs = valider(root)
    if erreurs:
        for erreur in erreurs:
            print(f"ERREUR: {erreur}", file=sys.stderr)
        raise SystemExit(1)
    if args.render:
        cible = root / "governance" / "SONAR-SUPPRESSIONS.md"
        cible.write_text(rendre(root), encoding="utf-8")
        print(f"OK: rapport généré : {cible.relative_to(root)}")
    else:
        print("OK: inventaire des suppressions Sonar valide")


if __name__ == "__main__":
    main()
