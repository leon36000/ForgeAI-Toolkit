#!/usr/bin/env python3
"""Inventaire + résolveur de doublons de preuves (RC1-011, #441).

Décision d'architecture (voir stories/RC1-011.md) : AUCUN ARTEFACT DE REVUE SCELLÉ existant sous
`evidence/reviews/**` (pack.md, REVIEW-PACK.md, `*.verdict.json` déjà déposés) n'est supprimé ni
modifié par ce module — seul `evidence/reviews/BINDING.txt` (index d'ancrage append-only du gate
`reviews-sealed`, jamais lui-même dans la préimage d'un sceau `prompt_sha256`) reçoit une nouvelle
ligne par story scellée, motif standard de ce dépôt. Ce module produit un manifest JSON (avant/après) déclarant, par
groupe de fichiers byte-identiques, un `canonique` (convention `min()` en ordre POSIX —
déterministe, sans prétention d'antériorité) et ses `repliques[]`, et expose `resoudre(manifest,
chemin) -> chemin` pour suivre cette déclaration côté lecture seule.

Les groupes composés à 100% de fichiers `*.verdict.json` reçoivent la classe dédiée
`attestation-verdict` (canonique=null) : ils ne sont JAMAIS dédupliqués — le nom de fichier
(`glm.verdict.json`, `kimi.verdict.json`, ...) est le seul support survivant de l'identité du
reviewer pour les 35 verdicts au format legacy, sans champ `vendor`/`reviewer_model`.

Usage :
  evidence_dedup.py --racine DIR --phase avant|apres --sortie MANIFEST.json
  evidence_dedup.py --resoudre CHEMIN --verifier MANIFEST.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

SCHEMA = "evidence-dedup/1"


def empreinte(chemin: Path) -> str:
    """sha256 hexdigest du contenu du fichier `chemin`."""
    return hashlib.sha256(chemin.read_bytes()).hexdigest()


def inventaire(racine: Path, exclure: tuple[str, ...] = ()) -> dict[str, str]:
    """{chemin_relatif_posix: sha256} pour tout fichier sous `racine`.

    `Path.rglob` uniquement — AUCUN appel git/subprocess : doit fonctionner dans une
    extraction/clone propre sans `.git` (critère #441 « extraction dans un clone propre »).
    `exclure` : préfixes de chemin relatif (posix) à ignorer, ex. `("dedup/",)` pour ne pas
    s'auto-inventorier quand `racine` contient déjà le manifest en cours de génération.
    """
    resultat: dict[str, str] = {}
    for chemin in sorted(racine.rglob("*")):
        if not chemin.is_file():
            continue
        rel = chemin.relative_to(racine).as_posix()
        if any(rel.startswith(prefixe) for prefixe in exclure):
            continue
        try:
            resultat[rel] = empreinte(chemin)
        except OSError:
            continue
    return resultat


def grouper(inv: dict[str, str]) -> list[dict]:
    """Groupes de >=2 chemins partageant le même sha256 (fichiers sans doublon ignorés)."""
    par_hash: dict[str, list[str]] = {}
    for chemin, sha in inv.items():
        par_hash.setdefault(sha, []).append(chemin)
    groupes = [
        {"sha256": sha, "membres": sorted(membres)}
        for sha, membres in par_hash.items()
        if len(membres) >= 2
    ]
    return sorted(groupes, key=lambda g: g["sha256"])


def canonique(membres: list[str]) -> str:
    """Chemin canonique d'un groupe : minimum en ordre POSIX — déterministe et stable,
    sans prétention d'antériorité (convention documentée dans stories/RC1-011.md)."""
    return min(membres)


def classifier(groupe: dict) -> tuple[str, str | None]:
    """Classe un groupe : `("attestation-verdict", None)` si 100% des membres sont des
    `*.verdict.json` (jamais dédupliqué), sinon `("duplique", canonique(membres))`."""
    membres = groupe["membres"]
    if membres and all(m.endswith(".verdict.json") for m in membres):
        return "attestation-verdict", None
    return "duplique", canonique(membres)


def _inventaire_digest(inv: dict[str, str]) -> str:
    """sha256 déterministe (ordre trié) de l'inventaire entier — preuve mécanique de
    stabilité de contenu entre deux générations (avant/après)."""
    h = hashlib.sha256()
    for chemin in sorted(inv):
        h.update(chemin.encode("utf-8"))
        h.update(b"\0")
        h.update(inv[chemin].encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def construire_manifest(racine: Path, phase: str, exclure: tuple[str, ...] = ("dedup/",)) -> dict:
    """Construit le manifest complet (schema/phase/fichiers_total/inventaire_sha256/groupes)."""
    inv = inventaire(racine, exclure=exclure)
    groupes: list[dict] = []
    for groupe_brut in grouper(inv):
        classe, can = classifier(groupe_brut)
        membres = groupe_brut["membres"]
        repliques = sorted(m for m in membres if m != can) if can is not None else sorted(membres)
        groupes.append(
            {
                "sha256": groupe_brut["sha256"],
                "classe": classe,
                "canonique": can,
                "repliques": repliques,
            }
        )
    return {
        "schema": SCHEMA,
        "phase": phase,
        "fichiers_total": len(inv),
        "inventaire_sha256": _inventaire_digest(inv),
        "groupes": groupes,
    }


def resoudre(manifest: dict, chemin: str) -> str:
    """Résout `chemin` vers son canonique déclaré dans `manifest`.

    - Une réplique d'un groupe `duplique` résout vers le canonique du groupe.
    - Le canonique lui-même résout vers lui-même (idempotent).
    - Un chemin hors de tout groupe résout vers lui-même.
    - Un membre d'un groupe `attestation-verdict` résout TOUJOURS vers lui-même — ces
      groupes sont ignorés par la boucle de résolution (jamais déréférencés).
    """
    for groupe in manifest["groupes"]:
        if groupe["classe"] == "attestation-verdict":
            continue
        if chemin == groupe["canonique"]:
            return chemin
        if chemin in groupe["repliques"]:
            return groupe["canonique"]
    return chemin


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--racine", default=".", help="répertoire à inventorier récursivement")
    ap.add_argument("--phase", choices=("avant", "apres"), help="génère un manifest avant/après")
    ap.add_argument("--sortie", help="chemin de sortie du manifest JSON (avec --phase)")
    ap.add_argument("--resoudre", help="chemin relatif à résoudre vers son canonique (avec --verifier)")
    ap.add_argument("--verifier", help="chemin d'un manifest JSON existant à utiliser pour --resoudre")
    args = ap.parse_args(argv)

    racine = Path(args.racine).resolve()

    if args.phase:
        manifest = construire_manifest(racine, phase=args.phase)
        texte = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if args.sortie:
            # Valide le chemin CONSTRUIT avant d'écrire : résolution explicite (canonicalise
            # `..`/symlinks) plutôt que d'agir sur la chaîne brute fournie en CLI, et refuse
            # d'écrire si le répertoire parent résolu n'existe pas (pas de création implicite
            # de hiérarchie hors de ce qui a été explicitement préparé par l'appelant).
            sortie = Path(args.sortie).resolve()
            if not sortie.parent.is_dir():
                print(f"--sortie : répertoire parent introuvable : {sortie.parent}", file=sys.stderr)
                return 2
            sortie.write_text(texte, encoding="utf-8")
        else:
            print(texte, end="")
        return 0

    if args.resoudre:
        if not args.verifier:
            print("--resoudre nécessite --verifier <manifest.json>", file=sys.stderr)
            return 2
        # Valide le chemin CONSTRUIT avant de le lire : résolution explicite + vérification
        # d'existence, plutôt qu'un accès direct à la chaîne brute fournie en CLI.
        verifier = Path(args.verifier).resolve()
        if not verifier.is_file():
            print(f"--verifier : fichier introuvable : {verifier}", file=sys.stderr)
            return 2
        manifest = json.loads(verifier.read_text(encoding="utf-8"))
        print(resoudre(manifest, args.resoudre))
        return 0

    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
