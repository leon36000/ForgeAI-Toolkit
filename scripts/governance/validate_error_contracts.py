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

# Round 12 (#452) — objection GPT-5.6-Terra-Pro (revue scellée) : la valeur de 'schema' n'était
# jamais comparée à la version attendue, seulement son type. Toute chaîne non vide (y compris une
# version inconnue/incompatible) franchissait le gate.
SCHEMA_VERSION_ATTENDUE = "error-handling-contracts/1"


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


def _fonction_test_existe(fichier: Path, segments: list[str]) -> bool:
    """Vérifie qu'une chaîne de segments (ex. ['test_fonction'] pour une fonction de module,
    ou ['TestClasse', 'test_methode'] pour une méthode) désigne réellement une fonction de test
    COLLECTABLE PAR PYTEST dans l'AST du fichier — pas seulement une fonction qui existe.

    Round 14 (#452) — objection GPT-5.6-Terra-Pro (revue scellée) : un compensating_test pouvait
    désigner n'importe quelle fonction existante (y compris du code de production), tant qu'elle
    portait le nom demandé — sans jamais vérifier que pytest la collecterait réellement. Convention
    pytest par défaut (pyproject.toml : aucun override python_classes/python_functions) : classes
    'Test*', fonctions/méthodes 'test_*'.
    """
    if len(segments) == 1:
        if not segments[0].startswith("test_"):
            return False
    elif len(segments) == 2:
        classe, methode = segments
        if not classe.startswith("Test") or not methode.startswith("test_"):
            return False
    else:
        return False  # profondeur non supportée par la convention pytest par défaut

    try:
        arbre = ast.parse(fichier.read_text(encoding="utf-8"), filename=str(fichier))
    except (OSError, SyntaxError):
        return False

    def _cherche(noeuds: list, segs: list[str]) -> bool:
        if not segs:
            return False
        cible = segs[0]
        reste = segs[1:]
        for noeud in noeuds:
            if isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef)) and noeud.name == cible:
                return not reste
            if isinstance(noeud, ast.ClassDef) and noeud.name == cible:
                if not reste:
                    return False
                # Round 15 (#452) — objection GPT-5.6-Terra-Pro (revue scellée) : pytest
                # n'instancie PAS une classe Test* qui définit __init__ (PytestCollectionWarning
                # « cannot collect test class ... because it has a __init__ constructor »,
                # vérifié empiriquement) — une telle classe n'est donc jamais réellement
                # collectée, même si la méthode existe bien dans l'AST.
                if any(
                    isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and m.name == "__init__"
                    for m in noeud.body
                ):
                    return False
                return _cherche(noeud.body, reste)
        return False

    return _cherche(arbre.body, segments)


def _test_compensatoire_existe(root: Path, test_compensatoire: object) -> bool:
    if not isinstance(test_compensatoire, str):
        return False
    parties = test_compensatoire.split("::")
    chemin = parties[0]
    segments = parties[1:]
    if not chemin:
        return False
    # Round 14 (#452) — objection GPT-5.6-Terra-Pro : le fichier doit être sous tests/ et nommé
    # selon la convention de découverte pytest par défaut (pyproject.toml : testpaths=["tests"],
    # aucun override python_files -> test_*.py ou *_test.py) — sinon pytest ne le collecte jamais.
    chemin_p = Path(chemin)
    if not chemin_p.parts or chemin_p.parts[0] != "tests":
        return False
    nom_fichier = chemin_p.name
    if not nom_fichier.endswith(".py") or not (
        nom_fichier.startswith("test_") or nom_fichier.endswith("_test.py")
    ):
        return False
    root_resolu = root.resolve()
    candidat = (root_resolu / chemin).resolve()
    try:
        candidat.relative_to(root_resolu)
    except ValueError:
        return False
    if not candidat.is_file():
        return False
    if not segments:
        # Round 5 (#452) — objection DeepSeek-V4-Pro (reviews/RC1-023-PR-v4) : un chemin nu (sans
        # ::fonction) était accepté dès lors que le FICHIER existait, même sans aucun rapport avec
        # le correctif. Un compensating_test doit toujours désigner une fonction/méthode précise.
        return False
    return _fonction_test_existe(candidat, segments)


def _valider_structure_globale(inventaire: dict) -> tuple[list[str], int, int]:
    erreurs: list[str] = []
    if "schema" not in inventaire or not isinstance(inventaire["schema"], str):
        erreurs.append("champ 'schema' absent ou invalide")
    elif inventaire["schema"] != SCHEMA_VERSION_ATTENDUE:
        erreurs.append(
            f"champ 'schema' inattendu : {inventaire['schema']!r} "
            f"(attendu : {SCHEMA_VERSION_ATTENDUE!r})"
        )

    review_horizon = inventaire.get("review_horizon")
    if not isinstance(review_horizon, dict) or not isinstance(
        review_horizon.get("days"), int
    ):
        erreurs.append("champ 'review_horizon' absent ou invalide (doit contenir 'days': int)")
    elif (
        not isinstance(review_horizon.get("justification"), str)
        or not review_horizon["justification"].strip()
    ):
        # Round 8 (#452) — objection GPT-5.6-Terra-Pro (revue scellée) : ce champ n'était ni
        # exigé ni typé, alors que le rapport Markdown le rend visible comme partie du contrat.
        erreurs.append("review_horizon.justification doit être une chaîne non vide")

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
        # Round 8 (#452) — objection GPT-5.6-Terra-Pro (revue scellée) : ces champs de couverture
        # n'étaient ni exigés ni typés — un inventaire amputé de l'un d'eux passait quand même le
        # gate dès lors que contracted/floor et les contrats restaient valides.
        total_sites = coverage.get("total_except_sites_src_forgeai")
        if not isinstance(total_sites, int) or isinstance(total_sites, bool) or total_sites < 0:
            erreurs.append(
                "coverage.total_except_sites_src_forgeai doit être un entier positif ou nul"
            )
        for champ in ("measured_on", "measured_command", "note"):
            valeur = coverage.get(champ)
            if not isinstance(valeur, str) or not valeur.strip():
                erreurs.append(f"coverage.{champ} doit être une chaîne non vide")

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


def _resoudre_dans_racine(root_resolu: Path, path_rel: str) -> Path | None:
    """Résout un chemin relatif en chemin ABSOLU normalisé confiné à root_resolu, ou None s'il en
    sort. Ne vérifie PAS si path_rel est absolu (à l'appelant de le faire s'il veut un message
    d'erreur dédié) — centralise seulement la normalisation.

    Round 18 (#452) — objection GPT-5.6-Terra-Pro (revue scellée) : _erreurs_sites_dupliques (round
    17) et _verifier_site_ast réimplémentaient chacune leur propre résolution de chemin, et
    avaient dérivé — la dédup comparait la CHAÎNE BRUTE (site.path) tandis que la vérif AST
    résolvait/normalisait ce même chemin. `src/forgeai/example.py` et `src/forgeai/./example.py`
    passaient tous deux la vérif AST sur le MÊME ExceptHandler mais n'étaient pas détectés comme
    doublons. Centraliser la résolution dans une seule fonction empêche cette classe de dérive.
    """
    candidat = (root_resolu / path_rel).resolve()
    try:
        candidat.relative_to(root_resolu)
    except ValueError:
        return None
    return candidat


def _erreurs_sites_dupliques(entrees: list[dict], root: Path) -> list[str]:
    # Round 17 (#452) — objection GPT-5.6-Terra-Pro (revue scellée) : _erreurs_identifiants_dupliques
    # ne détecte que les `id` dupliqués, jamais deux entrées ciblant le MÊME site (site.path,
    # site.line) sous des id distincts — le plancher de couverture pouvait ainsi être atteint sans
    # que 31 sites AST réellement distincts soient contractualisés.
    root_resolu = root.resolve()
    sites: list[tuple[Path, int]] = []
    for entree in entrees:
        if not isinstance(entree, dict):
            continue
        site = entree.get("site")
        if not isinstance(site, dict):
            continue
        path, line = site.get("path"), site.get("line")
        if not isinstance(path, str) or Path(path).is_absolute():
            continue
        if not isinstance(line, int) or isinstance(line, bool):
            continue
        resolu = _resoudre_dans_racine(root_resolu, path)
        if resolu is not None:
            sites.append((resolu, line))
    return [
        f"site dupliqué référencé par plusieurs contrats : {chemin.relative_to(root_resolu)}:{ligne}"
        for chemin, ligne in sorted({item for item in sites if sites.count(item) > 1})
    ]


def _compter_except_handlers_reels(root: Path) -> int:
    """Recompte indépendamment (AST) le nombre total de blocs `except` sous src/forgeai/ — même
    grandeur que coverage.total_except_sites_src_forgeai, faisant foi pour la comparaison."""
    total = 0
    racine_src = root / "src" / "forgeai"
    if not racine_src.is_dir():
        return 0
    for fichier in sorted(racine_src.rglob("*.py")):
        try:
            arbre = ast.parse(fichier.read_text(encoding="utf-8"), filename=str(fichier))
        except (OSError, SyntaxError):
            continue
        total += sum(1 for noeud in ast.walk(arbre) if isinstance(noeud, ast.ExceptHandler))
    return total


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
    # bool exclu explicitement : isinstance(True, int) vaut True en Python (même piège déjà
    # gardé pour coverage.contracted/floor/total_except_sites_src_forgeai plus haut).
    if (
        not isinstance(path_rel, str)
        or not isinstance(line, int)
        or isinstance(line, bool)
        or line <= 0
    ):
        return [f"{identifiant} : site.path (str) et site.line (int > 0) requis"]

    # Round 13 (#452) — objection GPT-5.6-Terra-Pro (revue scellée) : site.path n'était confiné
    # ni à la racine du dépôt ni à src/forgeai/. Un chemin absolu passait tel quel — piège pathlib
    # classique : (root / "/etc/passwd") == Path("/etc/passwd"), le côté gauche est ignoré par
    # l'opérateur / quand le droit est absolu — et une remontée ../.. pouvait faire sortir la
    # validation AST du périmètre annoncé de l'inventaire.
    if Path(path_rel).is_absolute():
        return [f"{identifiant} : site.path doit être un chemin relatif (reçu un chemin absolu)"]
    root_resolu = root.resolve()
    # Round 18 (#452) : résolution centralisée dans _resoudre_dans_racine — partagée avec
    # _erreurs_sites_dupliques pour que les deux fonctions s'accordent sur « même fichier ».
    fichier_source = _resoudre_dans_racine(root_resolu, path_rel)
    if fichier_source is None:
        return [f"{identifiant} : site.path sort de la racine du dépôt : {path_rel}"]
    chemin_relatif_reel = fichier_source.relative_to(root_resolu)
    # Round 16 (#452) — objection GPT-5.6-Terra-Pro (revue scellée) : round 13 testait le préfixe
    # sur la CHAÎNE BRUTE path_rel, contournable par une traversée qui reste sous root tout en
    # s'échappant de src/forgeai/ (ex. "src/forgeai/../../tests/x.py" commence par "src/forgeai/"
    # en texte mais résout à <root>/tests/x.py). Le test porte désormais sur le chemin RÉSOLU ET
    # NORMALISÉ (chemin_relatif_reel, déjà produit par .resolve() + relative_to() ci-dessus), via
    # .parts plutôt qu'un préfixe de chaîne — insensible à toute forme de ../ ou de séparateurs.
    if chemin_relatif_reel.parts[:2] != ("src", "forgeai"):
        return [f"{identifiant} : site.path doit cibler src/forgeai/ (reçu : {path_rel})"]

    # Round 8 (#452) — objection GPT-5.6-Terra-Pro (revue scellée) : site.function n'était ni
    # exigé ni typé alors qu'il documente la fonction englobante de chaque site contractualisé.
    fonction = site.get("function")
    if not isinstance(fonction, str) or not fonction.strip():
        return [f"{identifiant} : site.function doit être une chaîne non vide"]

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

    # Round 10 (#452) — objection GPT-5.6-Terra-Pro (revue scellée) : 'id' était exigé (présence,
    # via CHAMPS_OBLIGATOIRES) mais ni son type chaîne ni son caractère non vide ne l'étaient —
    # "id": null ou "id": "" passait la validation, invalidant le caractère machine-identifiable
    # de l'inventaire (et rendait _erreurs_identifiants_dupliques aveugle, id étant falsy-filtré).
    for champ in ("id", "behavior_contract", "logging", "owner", "justification", "accepted_risk"):
        valeur = entree.get(champ)
        if not isinstance(valeur, str) or not valeur.strip():
            erreurs.append(f"{identifiant} : champ '{champ}' doit être une chaîne non vide")

    risk_paths = entree.get("risk_paths")
    if not isinstance(risk_paths, list):
        erreurs.append(f"{identifiant} : champ 'risk_paths' doit être une liste")
    elif any(not isinstance(rp, str) or not rp.strip() for rp in risk_paths):
        # Durcissement proactif (round 12-13, #452) — même famille que exception_types :
        # le type des ÉLÉMENTS de la liste n'était pas vérifié.
        erreurs.append(f"{identifiant} : champ 'risk_paths' doit contenir des chaînes non vides")

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
    erreurs.extend(_erreurs_sites_dupliques(contracts, root))

    # Round 17 (#452) — objection GPT-5.6-Terra-Pro (revue scellée) : coverage.total_except_sites_
    # src_forgeai n'était jamais vérifié contre un décompte AST réel — un total arbitraire passait
    # le gate tant qu'il restait un entier positif (round 8). total_declare est garanti entier ici
    # (structure déjà validée plus haut, retour anticipé sinon).
    total_declare = inventaire["coverage"]["total_except_sites_src_forgeai"]
    total_reel = _compter_except_handlers_reels(root)
    if total_declare != total_reel:
        erreurs.append(
            f"coverage.total_except_sites_src_forgeai ({total_declare}) ne correspond pas au "
            f"décompte AST réel de src/forgeai/ ({total_reel})"
        )

    ast_cache: dict[Path, ast.AST | None] = {}
    for index, entree in enumerate(contracts):
        if isinstance(entree, dict):
            erreurs.extend(_erreurs_entree(root, entree, aujourd_hui, date_maximale, ast_cache))
        else:
            # Round 5 (#452) — objection DeepSeek-V4-Pro (reviews/RC1-023-PR-v4) : une entrée
            # non-dict était silencieusement ignorée au lieu de signaler une violation de schéma.
            erreurs.append(
                f"contracts[{index}] : entrée invalide, doit être un objet (type reçu : "
                f"{type(entree).__name__})"
            )

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
