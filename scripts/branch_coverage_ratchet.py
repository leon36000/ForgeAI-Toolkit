#!/usr/bin/env python3
"""Cliquet de couverture de branches par catégorie (RC1-021, #451, incrément 2a).

Réutilise le JSON déjà produit par `scripts/branch_coverage_report.py`
(`--sortie-json`), ne relance JAMAIS sa propre mesure pytest séparée.
Calcule, pour chaque catégorie de `governance/branch-coverage-categories.json`,
le pourcentage de branches couvertes agrégé sur les fichiers dont le chemin
matche au moins un glob de la catégorie (`pathlib.PurePath.match` / `fnmatch`,
stdlib uniquement). Compare à la baseline commitée
`governance/branch-coverage-baseline.json` (clé `seuils_par_categorie`) via le
module partagé `gate_git_ref.py` (même pattern exact que `ruff_ratchet.py` /
`mypy_gate.py`). Bloquant si une catégorie régresse sous son seuil baseliné.
Mode `--regenerer-baseline` explicite pour la maintenance (jamais automatique
en CI), symétrique à `ruff_ratchet.py --regenerer-baseline`.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import sys
from pathlib import Path, PurePath
from typing import Any

import gate_git_ref


def _charger_json(chemin: Path) -> dict[str, Any]:
    try:
        contenu = json.loads(chemin.read_text(encoding="utf-8"))
    except FileNotFoundError as erreur:
        raise ValueError(f"fichier JSON introuvable : {str(chemin)!r}") from erreur
    except (OSError, UnicodeError) as erreur:
        raise ValueError(f"fichier JSON illisible {str(chemin)!r} : {erreur}") from erreur
    except json.JSONDecodeError as erreur:
        raise ValueError(f"fichier JSON invalide {str(chemin)!r} : {erreur}") from erreur
    if not isinstance(contenu, dict):
        raise ValueError(f"le contenu de {str(chemin)!r} doit être un objet JSON")
    return contenu


def _valider_categories(data: Any, libelle: str) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError(f"{libelle} doit être un objet JSON")
    categories: dict[str, Any] = {}
    for cle, valeur in data.items():
        if cle.startswith("_"):
            continue
        if not isinstance(cle, str) or not cle:
            raise ValueError(f"{libelle} contient une catégorie avec un nom invalide : {cle!r}")
        if not isinstance(valeur, dict):
            raise ValueError(f"{libelle}[{cle!r}] doit être un objet avec 'description' et 'chemins'")
        description = valeur.get("description")
        chemins = valeur.get("chemins")
        if not isinstance(description, str) or not description:
            raise ValueError(f"{libelle}[{cle!r}].description doit être une chaîne non vide")
        if not isinstance(chemins, list) or not chemins:
            raise ValueError(f"{libelle}[{cle!r}].chemins doit être une liste non vide de globs")
        for g in chemins:
            if not isinstance(g, str) or not g:
                raise ValueError(f"{libelle}[{cle!r}].chemins contient un glob invalide : {g!r}")
        if len(set(chemins)) != len(chemins):
            raise ValueError(f"{libelle}[{cle!r}].chemins contient des doublons")
        categories[cle] = {"description": description, "chemins": list(chemins)}
    if not categories:
        raise ValueError(f"{libelle} ne contient aucune catégorie (au moins une requise)")
    return categories


def _valider_baseline(data: Any, libelle: str) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError(f"{libelle} doit être un objet JSON")
    if data.get("_schema") != "branch-coverage-baseline-v1":
        raise ValueError(f"{libelle}._schema doit être 'branch-coverage-baseline-v1'")
    seuils = data.get("seuils_par_categorie")
    if not isinstance(seuils, dict):
        raise ValueError(f"{libelle}.seuils_par_categorie doit être un objet")
    if not seuils:
        raise ValueError(f"{libelle}.seuils_par_categorie ne doit pas être vide")
    for cat, seuil in seuils.items():
        if not isinstance(cat, str) or not cat:
            raise ValueError(f"{libelle}.seuils_par_categorie contient une clé invalide : {cat!r}")
        if isinstance(seuil, bool) or not isinstance(seuil, (int, float)):
            raise ValueError(f"{libelle}.seuils_par_categorie[{cat!r}] doit être un nombre")
        if not (0 <= float(seuil) <= 100):
            raise ValueError(f"{libelle}.seuils_par_categorie[{cat!r}] doit être entre 0 et 100")
    seuil_global = data.get("seuil_global_initial_branches_pct")
    if seuil_global is not None:
        if isinstance(seuil_global, bool) or not isinstance(seuil_global, (int, float)):
            raise ValueError(f"{libelle}.seuil_global_initial_branches_pct doit être un nombre")
    return data


def _valider_baseline_reference(data: Any, libelle: str) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError(f"{libelle} doit être un objet JSON")
    if data.get("_schema") != "branch-coverage-baseline-v1":
        raise ValueError(f"{libelle}._schema doit être 'branch-coverage-baseline-v1'")
    seuils = data.get("seuils_par_categorie")
    if seuils is None or (isinstance(seuils, dict) and not seuils):
        data = dict(data)
        data["seuils_par_categorie"] = {}
        seuils = data["seuils_par_categorie"]
    else:
        if not isinstance(seuils, dict):
            raise ValueError(f"{libelle}.seuils_par_categorie doit être un objet")
        if not seuils:
            raise ValueError(f"{libelle}.seuils_par_categorie ne doit pas être vide")
        for cat, seuil in seuils.items():
            if not isinstance(cat, str) or not cat:
                raise ValueError(f"{libelle}.seuils_par_categorie contient une clé invalide : {cat!r}")
            if isinstance(seuil, bool) or not isinstance(seuil, (int, float)):
                raise ValueError(f"{libelle}.seuils_par_categorie[{cat!r}] doit être un nombre")
            if not (0 <= float(seuil) <= 100):
                raise ValueError(f"{libelle}.seuils_par_categorie[{cat!r}] doit être entre 0 et 100")
    seuil_global = data.get("seuil_global_initial_branches_pct")
    if seuil_global is not None:
        if isinstance(seuil_global, bool) or not isinstance(seuil_global, (int, float)):
            raise ValueError(f"{libelle}.seuil_global_initial_branches_pct doit être un nombre")
    return data


def _fichier_matche(chemin: str, globs: list[str]) -> bool:
    pure = PurePath(chemin)
    for pattern in globs:
        try:
            if pure.match(pattern):
                return True
        except ValueError:
            # PurePath.match() lève ValueError sur un pattern vide/malformé — bascule sur
            # fnmatch ci-dessous plutôt que de faire échouer tout le calcul de couverture pour
            # un seul glob mal formé (toute autre exception, elle, doit remonter).
            pass
        if fnmatch.fnmatch(chemin, pattern):
            return True
        if fnmatch.fnmatch(PurePath(chemin).as_posix(), pattern):
            return True
    return False


def calculer_couverture_par_categorie(
    donnees: dict[str, Any],
    categories: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    fichiers = donnees.get("files", {})
    if not isinstance(fichiers, dict):
        fichiers = {}
    resultat: dict[str, dict[str, Any]] = {}
    for cat, conf in categories.items():
        globs = conf.get("chemins", [])
        total_num = 0
        total_missing = 0
        matched: list[str] = []
        for chemin, fdata in fichiers.items():
            if not isinstance(fdata, dict):
                continue
            if not _fichier_matche(chemin, globs):
                continue
            summary = fdata.get("summary")
            if not isinstance(summary, dict):
                continue
            num = summary.get("num_branches")
            missing = summary.get("missing_branches")
            if not isinstance(num, int) or not isinstance(missing, int):
                continue
            total_num += num
            total_missing += missing
            matched.append(chemin)
        if total_num > 0:
            percent = (total_num - total_missing) / total_num * 100.0
        else:
            percent = 100.0
        resultat[cat] = {
            "num_branches": total_num,
            "missing_branches": total_missing,
            "percent_branches_covered": percent,
            "fichiers": sorted(matched),
        }
    return resultat


def _afficher_couverture(couverture: dict[str, dict[str, Any]], seuils: dict[str, float]) -> None:
    print("Rapport de couverture par catégorie")
    for cat in sorted(couverture):
        cov = couverture[cat]
        seuil = seuils.get(cat, 0)
        print(f"- {cat}: {cov['percent_branches_covered']:.2f}% (seuil {float(seuil):.2f}%) "
              f"[{cov['num_branches']} branches, {cov['missing_branches']} manquantes]")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cliquet de couverture de branches par catégorie.")
    parser.add_argument("--racine", default=".", help="racine du dépôt")
    parser.add_argument("--sortie-json", default="branch-coverage.json", help="chemin du rapport JSON de couverture")
    parser.add_argument("--base-ref-git", default="origin/main", metavar="REF", help="référence git de la baseline pour le contrôle de non-croissance")
    parser.add_argument("--regenerer-baseline", action="store_true", help="régénère governance/branch-coverage-baseline.json depuis une mesure fraîche, puis quitte (opération de maintenance déclarée, review-visible via diff git, jamais automatique en CI)")
    arguments = parser.parse_args(argv)

    racine = Path(arguments.racine)
    chemin_categories = racine / "governance" / "branch-coverage-categories.json"
    chemin_baseline = racine / "governance" / "branch-coverage-baseline.json"
    sortie_json = Path(arguments.sortie_json)
    if not sortie_json.is_absolute():
        sortie_json = racine / sortie_json

    try:
        categories_brutes = _charger_json(chemin_categories)
        categories = _valider_categories(categories_brutes, "categories")
    except (OSError, UnicodeError, ValueError, RuntimeError) as erreur:
        print(str(erreur), file=sys.stderr)
        return 1

    if arguments.regenerer_baseline:
        try:
            if chemin_baseline.exists():
                baseline_brute = _charger_json(chemin_baseline)
                if not isinstance(baseline_brute, dict):
                    raise ValueError(f"le contenu de {str(chemin_baseline)!r} doit être un objet JSON")
                if "_schema" not in baseline_brute:
                    baseline_brute["_schema"] = "branch-coverage-baseline-v1"
            else:
                baseline_brute = {"_schema": "branch-coverage-baseline-v1", "seuils_par_categorie": {}}
            donnees = _charger_json(sortie_json)
            if not isinstance(donnees.get("files"), dict):
                raise ValueError(f"le rapport de couverture {str(sortie_json)!r} ne contient pas de clé 'files' valide")
            couverture = calculer_couverture_par_categorie(donnees, categories)
            nouveaux_seuils: dict[str, float] = {}
            for cat in sorted(categories):
                nouveaux_seuils[cat] = float(couverture[cat]["percent_branches_covered"])
            baseline_brute["seuils_par_categorie"] = nouveaux_seuils
            _valider_baseline(baseline_brute, "baseline régénérée")
            texte = json.dumps(baseline_brute, indent=2, ensure_ascii=False) + "\n"
            chemin_baseline.parent.mkdir(parents=True, exist_ok=True)
            chemin_baseline.write_text(texte, encoding="utf-8")
        except (OSError, UnicodeError, ValueError, RuntimeError) as erreur:
            print(str(erreur), file=sys.stderr)
            return 1
        print(f"Baseline régénérée dans {str(chemin_baseline)} : seuils par catégorie = {nouveaux_seuils}")
        return 0

    try:
        baseline_brute = _charger_json(chemin_baseline)
        baseline = _valider_baseline(baseline_brute, "baseline")
    except (OSError, UnicodeError, ValueError, RuntimeError) as erreur:
        print(str(erreur), file=sys.stderr)
        return 1

    try:
        donnees = _charger_json(sortie_json)
    except (OSError, UnicodeError, ValueError, RuntimeError) as erreur:
        print(str(erreur), file=sys.stderr)
        return 1

    if not isinstance(donnees.get("files"), dict):
        print(f"le rapport de couverture {str(sortie_json)!r} ne contient pas de clé 'files' valide", file=sys.stderr)
        return 1

    couverture = calculer_couverture_par_categorie(donnees, categories)
    seuils = baseline.get("seuils_par_categorie", {})

    cats_courantes = set(categories.keys())
    cats_baseline = set(seuils.keys())
    if cats_courantes != cats_baseline:
        manquantes = sorted(cats_baseline - cats_courantes)
        en_trop = sorted(cats_courantes - cats_baseline)
        details: list[str] = []
        if manquantes:
            details.append(f"catégories baseline absentes des catégories actuelles : {manquantes}")
        if en_trop:
            details.append(f"catégories actuelles absentes de la baseline : {en_trop}")
        print("incohérence entre catégories et baseline : " + "; ".join(details) + " — mettre à jour governance/branch-coverage-categories.json et régénérer la baseline via --regenerer-baseline", file=sys.stderr)
        return 1

    anomalies: list[str] = []
    for cat in sorted(categories):
        # Round 4 de revue scellée (#451, objection mineure fondée) : teste la liste RÉELLE de
        # fichiers matchés (`fichiers`), pas `num_branches == 0` — un fichier peut légitimement
        # matcher un glob sans posséder la moindre branche (ex. module de pures constantes), ce
        # qui n'est PAS suspect et ne doit jamais être rapporté comme « aucun fichier ne matche ».
        if not couverture[cat]["fichiers"]:
            anomalies.append(f"catégorie {cat!r} : aucun fichier du rapport ne matche ses globs ({categories[cat]['chemins']}) — vérifier `governance/branch-coverage-categories.json` (fichiers supprimés/renommés hors périmètre, ou config de globs erronée)")
    for cat in sorted(categories):
        percent = couverture[cat]["percent_branches_covered"]
        seuil = float(seuils[cat])
        if percent + 1e-9 < seuil:
            anomalies.append(f"catégorie {cat!r} en régression : {percent:.2f}% < seuil {seuil:.2f}% ({couverture[cat]['missing_branches']}/{couverture[cat]['num_branches']} branches manquantes)")

    try:
        base_reference, message_reference = gate_git_ref.charger_base_reference_git(
            racine, chemin_baseline, arguments.base_ref_git, _valider_baseline_reference
        )
        if message_reference:
            print(f"Avertissement : {message_reference}", file=sys.stderr)
    except (OSError, ValueError, RuntimeError) as erreur:
        print(str(erreur), file=sys.stderr)
        return 1

    if base_reference is not None:
        seuils_ref = base_reference.get("seuils_par_categorie", {})
        if not isinstance(seuils_ref, dict):
            seuils_ref = {}
        cats_ref = set(seuils_ref.keys())
        # cats_ref vide : référence à l'ancien schéma (pré-#451 incrément 2a, pas encore de
        # seuils_par_categorie) OU référence sans catégories du tout — rien de comparable, ce
        # n'est PAS une incohérence (correctif après échec réel de
        # test_main_reference_git_ancien_schema_sans_seuils_par_categorie_tolere : la validation
        # de schéma tolère déjà ce cas via _valider_baseline_reference, mais cette comparaison
        # devait aussi le traiter comme "rien à comparer", pas comme une incohérence).
        if cats_ref:
            if cats_baseline != cats_ref:
                manquantes_ref = sorted(cats_ref - cats_baseline)
                en_trop_ref = sorted(cats_baseline - cats_ref)
                details_ref: list[str] = []
                if manquantes_ref:
                    details_ref.append(f"catégories de référence absentes de la baseline locale : {manquantes_ref}")
                if en_trop_ref:
                    details_ref.append(f"catégories locales absentes de la référence : {en_trop_ref}")
                anomalies.append("incohérence de catégories avec la référence git : " + "; ".join(details_ref))
            for cat in sorted(cats_baseline & cats_ref):
                seuil_local = float(seuils[cat])
                seuil_ref = float(seuils_ref[cat])
                if seuil_local + 1e-9 < seuil_ref:
                    anomalies.append(f"seuil de catégorie {cat!r} a baissé depuis la référence git ({seuil_local:.2f}% < {seuil_ref:.2f}%) : la baseline ne peut pas baisser silencieusement")

    if anomalies:
        for a in anomalies:
            print(f"ANOMALIE : {a}", file=sys.stderr)
        _afficher_couverture(couverture, {k: float(v) for k, v in seuils.items()})
        return 1

    _afficher_couverture(couverture, {k: float(v) for k, v in seuils.items()})
    print("Cliquet couverture de branches par catégorie : OK, aucune régression.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
