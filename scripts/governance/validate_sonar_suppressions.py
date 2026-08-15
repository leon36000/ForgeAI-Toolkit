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


def _motifs(valeur: str) -> list[str]:
    return [motif.strip() for motif in valeur.split(",") if motif.strip()]


def _regex_glob_sonar(motif: str) -> re.Pattern[str]:
    parties: list[str] = ["^"]
    index = 0
    while index < len(motif):
        caractere = motif[index]
        if caractere == "*" and index + 1 < len(motif) and motif[index + 1] == "*":
            index += 2
            if index < len(motif) and motif[index] == "/":
                parties.append("(?:.*/)?")
                index += 1
            else:
                parties.append(".*")
            continue
        if caractere == "*":
            parties.append("[^/]*")
        elif caractere == "?":
            parties.append("[^/]")
        else:
            parties.append(re.escape(caractere))
        index += 1
    parties.append("$")
    return re.compile("".join(parties))


def _est_exclu(relatif: str, motifs: list[str]) -> bool:
    return any(_regex_glob_sonar(motif).fullmatch(relatif) for motif in motifs)


def _sources_python(root: Path, props: dict[str, str]) -> list[Path]:
    paths: list[Path] = []
    exclusions = _motifs(props.get("sonar.exclusions", ""))
    for source in _motifs(props.get("sonar.sources", "")):
        candidate = root / source
        if candidate.is_file() and candidate.suffix == ".py":
            paths.append(candidate)
        elif candidate.is_dir():
            paths.extend(candidate.rglob("*.py"))
    return sorted(
        {
            path
            for path in paths
            if not _est_exclu(path.relative_to(root).as_posix(), exclusions)
        }
    )


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


def _suppression_inline(
    relatif: str, numero: int, regle: str | None, **extra: object
) -> dict:
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


def _suppressions_commentaire(relatif: str, numero: int, commentaire: str) -> list[dict]:
    if not NOSONAR_MARKER.search(commentaire):
        return []

    ciblee = NOSONAR_TARGETED.search(commentaire)
    if ciblee:
        return [
            _suppression_inline(relatif, numero, regle)
            for regle in (item.strip() for item in ciblee.group(1).split(","))
        ]

    legacy = NOSONAR_LEGACY_RULE.search(commentaire)
    if legacy:
        return [
            _suppression_inline(
                relatif,
                numero,
                None,
                nue=True,
                legacy_rule=legacy.group(1),
            )
        ]

    return [_suppression_inline(relatif, numero, None, nue=True)]


def _suppressions_inline(path: Path, root: Path) -> list[dict]:
    relatif = path.relative_to(root).as_posix()
    suppressions: list[dict] = []
    for numero, commentaire in _commentaires_nosonar(path):
        suppressions.extend(_suppressions_commentaire(relatif, numero, commentaire))
    return suppressions


def _suppression_multicritere(props: dict[str, str], identifiant: str) -> dict:
    regle = props.get(f"sonar.issue.ignore.multicriteria.{identifiant}.ruleKey")
    resource = props.get(f"sonar.issue.ignore.multicriteria.{identifiant}.resourceKey")
    if regle is None or resource is None:
        return {
            "id": f"properties-multicriteria:{identifiant}:INCOMPLET",
            "kind": "properties-multicriteria",
            "rule": regle,
            "scope": "file",
            "sites": [{"path": resource}] if resource else [],
            "incomplete": True,
        }
    return {
        "id": f"properties-multicriteria:{identifiant}",
        "kind": "properties-multicriteria",
        "rule": regle,
        "scope": "file",
        "sites": [{"path": resource}],
    }


def _suppressions_multicriteres(props: dict[str, str]) -> list[dict]:
    identifiants = _motifs(props.get("sonar.issue.ignore.multicriteria", ""))
    return [_suppression_multicritere(props, identifiant) for identifiant in identifiants]


def _exclusions_proprietes(props: dict[str, str]) -> list[dict]:
    exclusions: list[dict] = []
    for cle in PROPERTIES:
        kind = (
            "coverage-exclusion"
            if cle == "sonar.coverage.exclusions"
            else "analysis-exclusion"
        )
        for motif in _motifs(props.get(cle, "")):
            exclusions.append(
                {
                    "id": f"{kind}:{cle}:{motif}",
                    "kind": kind,
                    "rule": None,
                    "scope": "glob",
                    "sites": [{"path": motif}],
                }
            )
    return exclusions


def suppressions_reelles(root: Path) -> list[dict]:
    props = _proprietes(root / "sonar-project.properties")
    validator = (
        root / "scripts" / "governance" / "validate_sonar_suppressions.py"
    ).resolve()
    suppressions: list[dict] = []

    for path in _sources_python(root, props):
        if path.resolve() == validator:
            continue
        if any(part in {".git", "__pycache__"} for part in path.parts):
            continue
        suppressions.extend(_suppressions_inline(path, root))

    suppressions.extend(_suppressions_multicriteres(props))
    suppressions.extend(_exclusions_proprietes(props))
    return suppressions


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


def _erreurs_horizon(inventaire: dict, aujourd_hui: dt.date) -> tuple[list[str], dt.date]:
    try:
        horizon_jours = _horizon(inventaire)
    except ValueError as erreur:
        return [str(erreur)], aujourd_hui
    return [], aujourd_hui + dt.timedelta(days=horizon_jours)


def _erreurs_identifiants_dupliques(entrees: list[dict]) -> list[str]:
    ids = [entree.get("id") for entree in entrees]
    return [
        f"identifiant d'inventaire dupliqué : {identifiant}"
        for identifiant in sorted({item for item in ids if ids.count(item) > 1})
    ]


def _erreurs_suppression_reelle(entree: dict, inventaire_par_id: dict) -> list[str]:
    erreurs: list[str] = []
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
                f"NOSONAR nu interdit : {site['path']}:{site['line']} ; "
                "indiquez la règle exacte"
            )
    if entree.get("incomplete"):
        erreurs.append(f"suppression multicritère incomplète : {entree['id']}")
    if entree["id"] not in inventaire_par_id:
        erreurs.append(f"suppression réelle non inventoriée : {entree['id']}")
    return erreurs


def _erreurs_suppressions_reelles(
    reelles: list[dict], inventaire_par_id: dict
) -> list[str]:
    erreurs: list[str] = []
    for entree in reelles:
        erreurs.extend(_erreurs_suppression_reelle(entree, inventaire_par_id))
    return erreurs


def _erreurs_entrees_fossiles(
    reels_par_id: dict, inventaire_par_id: dict
) -> list[str]:
    return [
        f"entrée d'inventaire fossile : {identifiant}"
        for identifiant in inventaire_par_id
        if identifiant not in reels_par_id
    ]


def _erreurs_date_revision(
    identifiant: object,
    review_due: object,
    aujourd_hui: dt.date,
    date_maximale: dt.date,
) -> list[str]:
    try:
        echeance = _date(review_due)
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


def _erreurs_test_compensatoire(
    root: Path, identifiant: object, test_compensatoire: object
) -> list[str]:
    if test_compensatoire is None:
        return []
    if _test_compensatoire_existe(root, test_compensatoire):
        return []
    return [
        f"{identifiant} : test compensatoire absent du dépôt : {test_compensatoire}"
    ]


def _erreurs_portee_large(entree: dict, identifiant: object) -> list[str]:
    test_compensatoire = entree["compensating_test"]
    if entree["scope"] not in {"file", "glob"} or test_compensatoire:
        return []
    raison = entree.get("compensating_test_reason", "")
    if "non-réductible" in raison.lower():
        return []
    return [
        f"{identifiant} : portée {entree['scope']} sans test compensatoire "
        "ni justification explicite de non-réductibilité"
    ]


def _erreurs_entree(
    root: Path, entree: dict, aujourd_hui: dt.date, date_maximale: dt.date
) -> list[str]:
    identifiant = entree.get("id", "<sans id>")
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
    manquants = sorted(champs - set(entree))
    if manquants:
        return [
            f"{identifiant} : champs obligatoires absents : {', '.join(manquants)}"
        ]

    erreurs = _erreurs_date_revision(
        identifiant, entree["review_due"], aujourd_hui, date_maximale
    )
    if any("review_due doit être une date ISO valide" in erreur for erreur in erreurs):
        return erreurs
    erreurs.extend(
        _erreurs_test_compensatoire(root, identifiant, entree["compensating_test"])
    )
    erreurs.extend(_erreurs_portee_large(entree, identifiant))
    return erreurs


def _erreurs_entrees(
    root: Path, entrees: list[dict], aujourd_hui: dt.date, date_maximale: dt.date
) -> list[str]:
    erreurs: list[str] = []
    for entree in entrees:
        erreurs.extend(_erreurs_entree(root, entree, aujourd_hui, date_maximale))
    return erreurs


def valider(root: Path, *, aujourd_hui: dt.date | None = None) -> list[str]:
    aujourd_hui = aujourd_hui or dt.date.today()
    inventaire = _lire_json(root / "governance" / "sonar-suppressions.json")
    entrees = inventaire.get("suppressions", [])

    erreurs, date_maximale = _erreurs_horizon(inventaire, aujourd_hui)
    erreurs.extend(_erreurs_identifiants_dupliques(entrees))

    reelles = suppressions_reelles(root)
    reels_par_id = {entree["id"]: entree for entree in reelles}
    inventaire_par_id = {entree.get("id"): entree for entree in entrees}

    erreurs.extend(_erreurs_suppressions_reelles(reelles, inventaire_par_id))
    erreurs.extend(_erreurs_entrees_fossiles(reels_par_id, inventaire_par_id))
    erreurs.extend(_erreurs_entrees(root, entrees, aujourd_hui, date_maximale))
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
        "La portée réelle des suppressions ciblées est vérifiée par le scan SonarCloud de la PR qui introduit une occurrence voisine : toute occurrence non couverte par un `NOSONAR(<règle>)` ciblé apparaît dans ce scan. La vérification ne relève donc pas du gate local ; sur la PR 499, `api/issues/search?pullRequest=499` a renvoyé deux issues et aucune sur `registre.py`, ce qui a confirmé que les deux `NOSONAR` nus retirés ne masquaient aucune issue.",
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
        lignes.append(
            "| " + " | ".join(cellule.replace("|", "\\|") for cellule in cellules) + " |"
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
        cible = root / "governance" / "SONAR-SUPPRESSIONS.md"
        cible.write_text(rendre(root), encoding="utf-8")
        print(f"OK: rapport généré : {cible.relative_to(root)}")
    else:
        print("OK: inventaire des suppressions Sonar valide")


if __name__ == "__main__":
    main()
