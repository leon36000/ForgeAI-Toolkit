#!/usr/bin/env python3
"""Pipeline de revue aveugle — génération de prompt NEUTRE + dépouillement DÉTERMINISTE.

Deux fonctions, toutes deux pures/déterministes (invariants #5 et #10 : « aucun LLM n'écrit
un score », « prompts sans verdict attendu ») :

  build_prompt(...)  → remplit CANON/revue-template.md avec l'artefact/critères et rend le
                       texte EXACT à envoyer aux reviewers + son sha256. Le prompt n'est
                       JAMAIS écrit à la main : identique pour les 3 reviewers (le sha256
                       partagé le prouve au dépouillement).

  tally(verdicts)    → dépouillement PAR SCRIPT. Exige ≥3 verdicts de ≥3 vendors DISTINCTS,
                       tous liés au MÊME prompt_sha256 ; APPROVE ssi tous APPROVE ET aucune
                       objection bloquante ; sinon REJECT avec l'union des objections triées
                       par sévérité. Aucun jugement de modèle : fonction pure de règles
                       binaires.

  verifier_recu(...) → lie un dossier de revue au commit/diff git EXACT qui va être fusionné
                       (issue #434). Le reçu (reviews/<ID>/RECU.json) est un CLAIM écrit par
                       l'Orchestrateur ; cette fonction le RÉFUTE mécaniquement en le comparant
                       à l'état git réellement résolu (jamais l'inverse — le gate ne fait
                       jamais confiance au reçu lui-même).

Usage :
  revue.py prompt --artefact <path> --story <id> [--criteres <fichier>] [--out <fichier>]
  revue.py tally <dossier_verdicts>          # lit *.verdict.json ; code retour 0 si APPROVE
  revue.py recu --dossier <nom> --base-ref <ref> --issue <n> --round <n> [--codeur <id>]*
  revue.py diff-canonique --base-ref <ref> [--head-ref HEAD]
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

_TEMPLATE_FIELD = re.compile(
    r"\{(story_id|criteres|artefact_path|artefact|metadata_json|response_schema)\}"
)
_MEMBER_START = re.compile(r"^\s*-\s*id:\s*(\S+)\s*(?:#.*)?$")
_MEMBER_FIELD = re.compile(r"^\s+(vendor|provider_id|modele|statut):\s*(.+?)\s*(?:#.*)?$")
# manifests/routes.yaml : mapping flow-style (une route par ligne) — membre/modele_reponse
# toujours sur la 1ère ligne de l'entrée (une éventuelle "note:" continue sur la ligne
# suivante, jamais capturée ici, pas pertinente pour l'identité vendor).
_ROUTE_ENTRY = re.compile(r"membre:\s*(\S+?),.*?modele_reponse:\s*([^,}]+)")
_NON_ALNUM = re.compile(r"[^a-z0-9]")
_OBJECT_ID = re.compile(r"^[0-9a-f]{40}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_SOL_PROMPT_FILENAME = "SOL-PROMPT.md"
_SOL_TEMPLATE_PATH = "CANON/revue-template.md"
_SOL_ARTIFACT_PATH = "canonical-git-diff"
_SOL_CRITERIA = "(voir story)"
_SOL_CANONICAL_ID = "sol"
_SOL_CANONICAL_MODEL = "GPT-5.6 Sol"
_SOL_CANONICAL_VENDOR = "openai"
_SOL_CANONICAL_PROVIDER_ID = "GPT-5.6-Sol"
_SOL_CANONICAL_STATUS = "actif"
_SOL_CANONICAL_CODEUR_ID = "luna_writer"
_SOL_CANONICAL_STORY_ID = "stories/ORCH-LUNA-SOL-603.md"
_LUNA_CANONICAL_MODEL = "GPT-5.6 Luna"
_LUNA_CANONICAL_VENDOR = "openai"
_LUNA_CANONICAL_PROVIDER_ID = "GPT-5.6-Luna-Writer"
_LUNA_CANONICAL_STATUS = "actif"
_SOL_CLOCK_SKEW = timedelta(minutes=5)
_SOL_MAX_WINDOW_HOURS = 24

REPO = Path(__file__).resolve().parent.parent
TEMPLATE = REPO / "CANON" / "revue-template.md"
AUTONOMY_POLICY = REPO / "governance" / "autonomy-policy.json"

# _SEVERITY_RANK/_BLOCKING couvrent DEUX vocabulaires : les verdicts réels du dépôt écrivent
# la clé française "severite" avec l'échelle mineure/majeure/critique, alors que le code
# historique n'attendait que la clé anglaise "severity" avec critique/eleve/moyen/faible — un
# vrai verdict français ne matchait donc JAMAIS _BLOCKING (bug trouvé par revue d'architecture
# #434, aucune régression sur les entrées déjà dans reviews/BINDING.txt : vérifié qu'aucune
# n'y combine APPROVE + objection sévère).
_SEVERITY_RANK = {
    "critique": 0,
    "eleve": 1,
    "majeure": 1,
    "moyen": 2,
    "faible": 3,
    "mineure": 3,
}
_BLOCKING = {"critique", "eleve", "majeure"}

GitRunner = Callable[[list[str]], str]


def _normalize(value: str) -> str:
    """Réduit un identifiant à ses seuls alphanumériques minuscules — "Qwen3.7-Max",
    "qwen 3.7 max" et "qwen37max" doivent tous résoudre au même vendor, quelle que soit la
    ponctuation utilisée par la source (roster, route, ou verdict réel)."""
    return _NON_ALNUM.sub("", value.strip().lower())


def _load_roles_yaml(path: Path) -> list[dict]:
    """Lit uniquement les données membres nécessaires du roster YAML stable."""
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []

    start = None
    for index, line in enumerate(lines):
        if line == "membres:":
            start = index + 1
            break
    if start is None:
        return []

    block = []
    for line in lines[start:]:
        if line and not line[0].isspace() and re.match(r"^[^:#]+:", line):
            break
        block.append(line)

    members = []
    current = None
    for line in block:
        start_match = _MEMBER_START.match(line)
        if start_match:
            if current is not None:
                members.append(current)
            current = {"id": start_match.group(1)}
            continue
        if current is None:
            continue
        field_match = _MEMBER_FIELD.match(line)
        if field_match:
            key, value = field_match.groups()
            if value != "null":
                current[key] = value
    if current is not None:
        members.append(current)
    return members


def _load_routes_yaml(path: Path) -> list[tuple[str, str]]:
    """Lit les paires (membre, modele_reponse) du fichier de routes stable.

    modele_reponse est le nom de route LiteLLM RÉELLEMENT renvoyé par le bridge — c'est LUI
    qui apparaît comme `reviewer_model` dans les verdicts scellés réels, pas forcément le
    `provider_id` de manifests/roles.yaml (les deux divergent pour au moins un membre :
    deepseek → provider_id "deepseek" mais modele_reponse "DeepSeek-V4-Pro").
    """
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    pairs = []
    for line in lines:
        match = _ROUTE_ENTRY.search(line)
        if match:
            pairs.append((match.group(1), match.group(2).strip()))
    return pairs


def _vendor_table(
    roles_path: Path = REPO / "manifests" / "roles.yaml",
    routes_path: Path = REPO / "manifests" / "routes.yaml",
) -> dict[str, str] | None:
    """Construit la table identité→vendor des REVIEWERS possibles, depuis le roster versionné
    (manifests/roles.yaml, enrichi des alias de manifests/routes.yaml).

    Exclut les membres sans route bridge (`provider_id` absent, ex. fable — Anthropic ne
    review jamais). Retourne None (distinct de {}) si le roster est introuvable/illisible —
    l'appelant (tally) doit alors échouer fort, jamais retomber sur une table vide silencieuse
    qui romprait l'anti-Sybil.
    """
    roles = _load_roles_yaml(roles_path)
    if not roles:
        return None
    table = {}
    for member in roles:
        vendor = member.get("vendor")
        provider_id = member.get("provider_id")
        if not vendor or not provider_id:
            continue  # pas de route bridge (ex. fable) → pas un reviewer possible
        normalized_vendor = vendor.lower()
        for key in (member.get("id"), provider_id, member.get("modele")):
            if key:
                table[_normalize(key)] = normalized_vendor
    for membre, modele_reponse in _load_routes_yaml(routes_path):
        vendor = table.get(_normalize(membre))
        if vendor:
            table[_normalize(modele_reponse)] = vendor
    return table


def _codeur_vendor_table(
    roles_path: Path = REPO / "manifests" / "roles.yaml",
) -> dict[str, str] | None:
    """Construit la table identité→vendor des CODEURS possibles (distincte de
    `_vendor_table`, qui exclut délibérément les membres sans `provider_id` — ex. fable).

    Pour l'anti-auto-review (#434), fable DOIT être résoluble vers anthropic : c'est le codeur
    le plus fréquent (l'Orchestrateur lui-même), et un membre sans route bridge n'en reste pas
    moins un codeur légitime. Retourne None si le roster est introuvable/illisible.
    """
    roles = _load_roles_yaml(roles_path)
    if not roles:
        return None
    table = {}
    for member in roles:
        vendor = member.get("vendor")
        if not vendor:
            continue
        normalized_vendor = vendor.lower()
        for key in (member.get("id"), member.get("provider_id"), member.get("modele")):
            if key:
                table[_normalize(key)] = normalized_vendor
    return table


def vendor_of(model_or_vendor: str, table: dict[str, str] | None = None) -> str:
    key = model_or_vendor.strip().lower()
    loaded_table = _vendor_table() if table is None else table
    if loaded_table is None:
        return key  # roster introuvable : tel quel (rejeté au dépouillement, cf. tally)
    # inconnu → renvoie la forme lisible (pas normalisée) : rejeté au dépouillement, cf. tally
    return loaded_table.get(_normalize(model_or_vendor), key)


def _default_runner(command: list[str]) -> str:
    return subprocess.run(
        command,
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def _validate_git_ref(ref: str) -> None:
    # Même garde anti-injection d'option git que scripts/gate_docs.py (SonarCloud S8705) :
    # une ref commençant par "-" serait interprétée comme une option, pas une référence.
    if not isinstance(ref, str) or not ref or ref.startswith("-"):
        raise ValueError(f"reference git invalide {ref!r}")


def _validate_object_id(value: object, field: str = "object_id") -> str:
    if not isinstance(value, str) or _OBJECT_ID.fullmatch(value) is None:
        raise ValueError(f"{field} doit être un object ID hexadécimal exact")
    return value


def _validate_digest(value: object, field: str = "digest") -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise ValueError(f"{field} doit être un digest SHA-256 exact")
    return value


def _resolve_commit(execute: GitRunner, commit: str) -> str:
    _validate_object_id(commit, "commit")
    resolved = execute(["git", "rev-parse", "--verify", f"{commit}^{{commit}}"]).strip()
    if resolved != commit:
        raise ValueError("commit résolu différent de l'object ID fourni")
    return resolved


def _resolve_commit_tree(execute: GitRunner, commit: str) -> str:
    _resolve_commit(execute, commit)
    tree = execute(["git", "rev-parse", "--verify", f"{commit}^{{tree}}"]).strip()
    _validate_object_id(tree, "tree")
    return tree


def _require_commit_ancestor(
    execute: GitRunner,
    ancestor: str,
    descendant: str,
    field: str,
) -> None:
    """Require a declared review commit to remain on the current Git lineage."""
    try:
        execute(["git", "merge-base", "--is-ancestor", ancestor, descendant])
    except subprocess.CalledProcessError as error:
        raise ValueError(f"{field} hors de la lignée Git courante") from error


def _sol_prompt_bytes(review_dir: Path) -> bytes:
    prompt_path = review_dir / _SOL_PROMPT_FILENAME
    if prompt_path.is_symlink():
        raise ValueError(f"{_SOL_PROMPT_FILENAME} doit être un fichier régulier, pas un symlink")
    if not prompt_path.is_file():
        raise ValueError(f"{_SOL_PROMPT_FILENAME} absent du dossier de revue")
    try:
        return prompt_path.read_bytes()
    except OSError as error:
        raise ValueError(f"{_SOL_PROMPT_FILENAME} illisible") from error


def _sol_prompt_sha256(review_dir: Path) -> str:
    return hashlib.sha256(_sol_prompt_bytes(review_dir)).hexdigest()


def _validate_sol_dossier(dossier: object, review_dir: Path | None = None) -> str:
    """Validate the receipt directory identifier and, when available, its loaded directory."""
    if not isinstance(dossier, str) or not dossier.strip():
        raise ValueError("dossier Sol invalide")
    if dossier in {".", ".."} or Path(dossier).name != dossier:
        raise ValueError("dossier Sol doit être un nom de répertoire simple")
    if review_dir is not None and Path(review_dir).name != dossier:
        raise ValueError("dossier Sol différent du répertoire de revue")
    return dossier


def _validate_sol_story_id(story: object, issue: object) -> str:
    """Accept only the immutable story bound to this Sol contract.

    The story is copied into the canonical prompt, so accepting an arbitrary receipt-controlled
    string would make the prompt byte-identically reconstructable while silently changing the
    work item (or injecting newlines/instructions).  The current policy has one explicit story
    binding; future contracts must add a new policy constant rather than widening this input.
    """
    try:
        policy_story = load_autonomy_policy()["review"]["story_id"]
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("story Sol impossible à lier à la politique") from error
    if story != policy_story:
        raise ValueError("story Sol différente de l'identifiant canonique")
    expected_issue = int(Path(policy_story).stem.rsplit("-", 1)[-1])
    if isinstance(issue, bool) or issue != expected_issue:
        raise ValueError("issue Sol différente de l'identifiant canonique")
    return policy_story


def _diff_artifact_canonique(
    base_ref: str,
    head_ref: str,
    *,
    runner: GitRunner | None = None,
) -> str:
    """Retourne l'artefact texte généré par les mêmes refs que le digest Sol."""
    _validate_git_ref(base_ref)
    _validate_git_ref(head_ref)
    execute = _default_runner if runner is None else runner
    return execute(
        [
            "git",
            "diff",
            "--no-ext-diff",
            "--binary",
            "--no-renames",
            f"{base_ref}...{head_ref}",
            "--",
            ".",
            ":(exclude)evidence/reviews/**",
            ":(exclude).superpowers/sdd/**",
            ":(exclude)governance/path-classification.json",
            ":(exclude)governance/PATH-CLASSIFICATION.md",
        ]
    )


def _diff_sdd_canonique(
    base_ref: str,
    head_ref: str,
    *,
    runner: GitRunner | None = None,
) -> str:
    """Hash the excluded SDD coordination diff so its state remains receipt-bound."""
    _validate_git_ref(base_ref)
    _validate_git_ref(head_ref)
    execute = _default_runner if runner is None else runner
    raw = execute(
        ["git", "diff", "--raw", "--no-renames", "--no-abbrev", "-z", f"{base_ref}...{head_ref}"]
    )
    fields = raw.split("\0")
    entries: list[tuple[str, str, str, str]] = []
    index = 0
    while index + 1 < len(fields):
        metadata = fields[index]
        path = fields[index + 1]
        index += 2
        if not metadata or not path.startswith(".superpowers/sdd/"):
            continue
        parts = metadata.split()
        if len(parts) != 5 or not parts[0].startswith(":"):
            raise ValueError(f"sortie git --raw SDD invalide: {metadata!r}")
        entries.append((parts[1], parts[2], parts[3], path))
    entries.sort()
    canonical = "".join(
        f"{mode}\0{base_sha}\0{head_sha}\0{path}\n"
        for mode, base_sha, head_sha, path in entries
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _diff_canonique(
    base_ref: str,
    head_ref: str,
    *,
    # RC1-010 (#440) lot 5d : reviews/ est intégralement migré vers evidence/reviews/ — le
    # préfixe legacy "reviews/" est retiré de l'exclusion par défaut (mort : plus aucun fichier
    # de revue n'y vit).
    #
    # #603 : les journaux .superpowers/sdd/ contiennent les résultats des itérations de
    # coordination; les exclure empêche une revue Sol aveugle de recevoir des verdicts
    # antérieurs par transitivité. Ils restent versionnés pour l'audit, mais ne sont pas
    # des changements produit évalués par le prompt courant.
    #
    # #504 : governance/path-classification.json (+ son rendu .md) trace individuellement
    # chaque fichier sous evidence/reviews/**, RECU.json compris — le régénérer APRÈS avoir
    # scellé un reçu change donc TOUJOURS le diff que ce reçu prétend attester (interblocage
    # circulaire entre les gates reviews-sealed et path-classification, main rouge sur
    # path-classification depuis 3 merges au moment de la découverte). Ce manifeste est de
    # toute façon déjà retiré à la main des packs de revue depuis le lot 5b — les reviewers ne
    # le voient jamais — donc l'exclure ici aligne l'empreinte scellée sur ce qui est
    # réellement revu, au lieu de sceller des octets jamais vus. Exclusion par nom de fichier
    # EXACT (pas de préfixe partiel) : governance/path-classification-rules.json (écrit à la
    # main, load_bearing) ne doit surtout PAS matcher par accident.
    exclude: tuple[str, ...] = (
        "evidence/reviews/",
        ".superpowers/sdd/",
        "governance/path-classification.json",
        "governance/PATH-CLASSIFICATION.md",
    ),
    runner: GitRunner | None = None,
) -> str:
    """Retourne l'empreinte SHA-256 canonique du diff merge-base, hors artefacts exclus.

    N'utilise PAS sha256(git diff texte) : cette sortie dépend de core.autocrlf,
    diff.algorithm, diff.renames et du ~/.gitconfig de qui l'exécute — instable. Utilise la
    PLOMBERIE (`git diff --raw --no-renames -z`), extrait (mode, sha_base, sha_head, chemin)
    par entrée, trie (ordre déterministe, indépendant de l'ordre retourné par git), hache.

    Exclusion OBLIGATOIRE de "evidence/reviews/" : le diff d'une PR contient TOUJOURS les
    artefacts de sa propre revue (le dossier evidence/reviews/<ID>/*.verdict.json + la ligne
    BINDING.txt sont ajoutés dans LA MÊME PR que le code qu'ils attestent) — sans cette
    exclusion, l'empreinte calculée par le reçu ne pourrait JAMAIS correspondre à celle du diff
    final (les reviewers ont vu un diff SANS ces fichiers). Les journaux `.superpowers/sdd/`
    sont également exclus du prompt Sol : ils peuvent contenir des conclusions de revues
    antérieures et ne sont pas du code produit. Même raisonnement pour
    governance/path-classification.json/.md (#504) : entièrement dérivés, re-vérifiés octet à
    octet par leur propre gate (classify_paths.py check), jamais montrés aux reviewers non plus.
    """
    _validate_git_ref(base_ref)
    _validate_git_ref(head_ref)
    execute = _default_runner if runner is None else runner
    # --no-abbrev (#569) : SANS ce flag, git --raw abrège les hash d'objet à la longueur la plus
    # courte qu'IL juge unique — une heuristique qui dépend du NOMBRE TOTAL D'OBJETS du dépôt
    # LOCAL (donc de l'historique de fetch de la machine qui exécute), pas seulement du contenu
    # des deux extrémités du diff. Un worktree partageant le `.git` du dépôt principal (des
    # dizaines de milliers d'objets accumulés) et un clone frais (seulement ce qui est sur
    # GitHub) abrègent alors à des longueurs DIFFÉRENTES pour le MÊME diff logique, produisant
    # un digest différent — le gate reviews-sealed en CI (toujours un clone frais) peut alors
    # rejeter à tort un reçu généré localement (worktree). --full-index NE corrige PAS ce cas :
    # ce flag ne s'applique qu'au format patch normal (ligne `index aaaa..bbbb`), jamais au
    # format `--raw`. Vérifié : avec --no-abbrev, les deux environnements produisent des hash
    # SHA-1 complets (40 caractères) strictement identiques pour un même diff logique.
    raw = execute(
        ["git", "diff", "--raw", "--no-renames", "--no-abbrev", "-z", f"{base_ref}...{head_ref}"]
    )
    fields = raw.split("\0")
    entries: list[tuple[str, str, str, str]] = []
    index = 0
    while index + 1 < len(fields):
        metadata = fields[index]
        path = fields[index + 1]
        index += 2
        if not metadata:
            continue
        parts = metadata.split()
        if len(parts) != 5 or not parts[0].startswith(":"):
            raise ValueError(f"sortie git --raw invalide: {metadata!r}")
        mode_head = parts[1]
        sha_base = parts[2]
        sha_head = parts[3]
        if not any(path.startswith(prefix) for prefix in exclude):
            entries.append((mode_head, sha_base, sha_head, path))
    entries.sort()
    canonical = "".join(
        f"{mode_head}\0{sha_base}\0{sha_head}\0{path}\n"
        for mode_head, sha_base, sha_head, path in entries
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _etat_git_reel(
    base_ref: str,
    head_ref: str = "HEAD",
    *,
    runner: GitRunner | None = None,
) -> dict:
    """Résout l'état git exact auquel un reçu est attaché (commit, arbre, empreinte du diff
    canonique). Adaptateur MINCE — la logique de vérification pure vit dans `verifier_recu`."""
    _validate_git_ref(base_ref)
    _validate_git_ref(head_ref)
    execute = _default_runner if runner is None else runner
    return {
        "base_commit": execute(["git", "merge-base", base_ref, head_ref]).strip(),
        "head_commit": execute(["git", "rev-parse", head_ref]).strip(),
        "head_tree": execute(["git", "rev-parse", f"{head_ref}^{{tree}}"]).strip(),
        "diff_digest": _diff_canonique(base_ref, head_ref, runner=execute),
        "sdd_diff_digest": _diff_sdd_canonique(base_ref, head_ref, runner=execute),
    }


def _template_mode_body(template_content: str, mode: str, template_path: Path) -> str:
    """Select one mode section from the versioned template without adding prose in code."""
    if "-->" not in template_content:
        raise ValueError(f"template {template_path} sans marqueur '-->' : en-tête non séparable")
    body = template_content.split("-->", 1)[1].lstrip("\n")
    start = f"<!-- MODE:{mode} -->"
    end = f"<!-- END MODE:{mode} -->"
    if start not in body or end not in body:
        raise ValueError(f"template {template_path} sans section {mode!r}")
    selected = body.split(start, 1)[1].split(end, 1)[0]
    return selected.strip("\n")


def build_prompt(story_id: str, criteres: str, artefact_path: str, artefact: str,
                 template_path: Path = TEMPLATE, *, mode: str = "multi_vendor",
                 expected: dict | None = None, base_ref: str | None = None,
                 head_ref: str | None = None, runner: GitRunner | None = None,
                 template_content: str | None = None) -> tuple[str, str]:
    """Render one exact, versioned prompt section and return its SHA-256."""
    if template_content is None:
        tpl = template_path.read_text(encoding="utf-8")
    elif isinstance(template_content, str):
        tpl = template_content
    else:
        raise ValueError("contenu du template invalide")
    if mode not in ("multi_vendor", "sol_blind"):
        raise ValueError(f"mode de revue inconnu : {mode!r}")
    template_sha256 = hashlib.sha256(tpl.encode("utf-8")).hexdigest()
    template_path_label = template_path
    if mode == "sol_blind":
        if not base_ref or not head_ref:
            raise ValueError("base_ref et head_ref requis pour le mode sol_blind")
        if runner is None:
            canonical_artifact = _diff_artifact_canonique(base_ref, head_ref)
            git_state = _etat_git_reel(base_ref, head_ref)
        else:
            canonical_artifact = _diff_artifact_canonique(
                base_ref, head_ref, runner=runner
            )
            git_state = _etat_git_reel(base_ref, head_ref, runner=runner)
        if artefact != canonical_artifact:
            raise ValueError("artefact fourni différent du diff Git canonique")
        metadata = {
            "base_commit": git_state["base_commit"],
            "reviewed_head_commit": git_state["head_commit"],
            "reviewed_head_tree": git_state["head_tree"],
            "candidate_diff_digest": git_state["diff_digest"],
            "sdd_diff_digest": _diff_sdd_canonique(
                base_ref, head_ref, runner=runner
            ),
            "template_sha256": template_sha256,
        }
        if expected is not None:
            for field, value in metadata.items():
                expected_value = expected.get(field)
                if expected_value is not None and expected_value != value:
                    raise ValueError(f"métadonnée Git {field} contradictoire")
        response_schema = {
            "fresh_context": True,
            "blind": True,
            "reviewer_read_only": True,
            "reviewer_model": "GPT-5.6-Sol",
            **metadata,
            "prompt_sha256": "sha256 du prompt reçu",
            "verdict": "APPROVE ou REJECT",
            "blocking_findings": [],
            "reviewed_at": "timestamp ISO-8601 avec fuseau",
        }
        values = {
            "story_id": story_id,
            "criteres": criteres.strip(),
            "artefact_path": artefact_path,
            "artefact": artefact,
            "metadata_json": json.dumps(metadata, ensure_ascii=False, sort_keys=True),
            "response_schema": json.dumps(response_schema, ensure_ascii=False, sort_keys=True),
        }
    else:
        values = {
            "story_id": story_id,
            "criteres": criteres.strip(),
            "artefact_path": artefact_path,
            "artefact": artefact,
            "metadata_json": "",
            "response_schema": json.dumps(
                {
                    "verdict": "APPROVE ou REJECT",
                    "objections": [
                        {
                            "severity": "critique|eleve|moyen|faible",
                            "file": "chemin",
                            "line": "entier ou null",
                            "desc": "défaut réel et vérifiable",
                        }
                    ],
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        }
    template_body = _template_mode_body(tpl, mode, template_path_label)
    # One substitution pass: substituted fields are never rescanned for placeholders.
    prompt = _TEMPLATE_FIELD.sub(lambda match: values[match.group(1)], template_body)
    return prompt, hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def _git_blob(execute: GitRunner, commit: str, path: str) -> str:
    """Read a fixed versioned text input from an already frozen commit."""
    _validate_object_id(commit, "commit")
    if not path or path.startswith("/") or ".." in Path(path).parts:
        raise ValueError("chemin Git versionné invalide")
    content = execute(["git", "show", f"{commit}:{path}"])
    if not isinstance(content, str):
        raise ValueError("entrée Git versionnée illisible")
    return content


def _canonical_sol_prompt(
    story_id: str,
    base_commit: str,
    reviewed_head_commit: str,
    *,
    runner: GitRunner | None = None,
) -> tuple[bytes, str]:
    """Rebuild the exact Sol prompt from frozen Git objects and versioned inputs."""
    execute = _default_runner if runner is None else runner
    frozen_base = _resolve_commit(execute, base_commit)
    frozen_head = _resolve_commit(execute, reviewed_head_commit)
    template_content = _git_blob(execute, frozen_head, _SOL_TEMPLATE_PATH)
    artifact = _diff_artifact_canonique(frozen_base, frozen_head, runner=execute)
    prompt, prompt_sha = build_prompt(
        story_id,
        _SOL_CRITERIA,
        _SOL_ARTIFACT_PATH,
        artifact,
        mode="sol_blind",
        base_ref=frozen_base,
        head_ref=frozen_head,
        runner=execute,
        template_content=template_content,
    )
    return prompt.encode("utf-8"), prompt_sha


def _sol_prompt_metadata(prompt: bytes) -> dict:
    """Extract the exact Git metadata object from a generated Sol prompt."""
    try:
        text = prompt.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("prompt Sol non UTF-8") from error
    marker = "MÉTADONNÉES GIT EXACTES (à recopier sans modification) :\n"
    if marker not in text:
        raise ValueError("métadonnées Git absentes du prompt Sol")
    line = text.split(marker, 1)[1].splitlines()[0]
    try:
        metadata = json.loads(line)
    except json.JSONDecodeError as error:
        raise ValueError("métadonnées Git du prompt Sol invalides") from error
    if not isinstance(metadata, dict):
        raise ValueError("métadonnées Git du prompt Sol invalides")
    for field in ("base_commit", "reviewed_head_commit", "reviewed_head_tree"):
        if field not in metadata:
            raise ValueError(f"métadonnée Git absente du prompt Sol : {field}")
        _validate_object_id(metadata[field], field)
    for field in ("candidate_diff_digest", "sdd_diff_digest", "template_sha256"):
        if field not in metadata:
            raise ValueError(f"métadonnée Git absente du prompt Sol : {field}")
        _validate_digest(metadata[field], field)
    return metadata


def _severity(objection: dict) -> str:
    """Sévérité normalisée d'une objection — accepte les clés française ET anglaise."""
    return str(objection.get("severite") or objection.get("severity") or "faible").lower()


def load_autonomy_policy(path: Path = AUTONOMY_POLICY) -> dict:
    """Charge et valide le contrat d'autonomie utilisé par les chemins de production."""
    try:
        policy = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"politique d'autonomie illisible : {path}") from error
    if not isinstance(policy, dict):
        raise ValueError("politique d'autonomie invalide")
    if policy.get("schema") != "autonomy-policy/1":
        raise ValueError("schema de politique d'autonomie invalide")
    worker = policy.get("worker")
    if not isinstance(worker, dict):
        raise ValueError("politique d'autonomie: worker manquant")
    if worker.get("primary_model") != "GPT-5.6 Luna":
        raise ValueError("worker.primary_model doit être GPT-5.6 Luna")
    lanes = worker.get("max_active_writer_lanes")
    if isinstance(lanes, bool) or not isinstance(lanes, int) or lanes != 2:
        raise ValueError("max_active_writer_lanes doit être exactement 2")
    review = policy.get("review")
    if not isinstance(review, dict):
        raise ValueError("politique d'autonomie: review manquant")
    if review.get("default_mode") != "sol_blind":
        raise ValueError("review.default_mode doit être sol_blind")
    if review.get("reviewer_model") != "GPT-5.6 Sol":
        raise ValueError("review.reviewer_model doit être GPT-5.6 Sol")
    if review.get("story_id") != _SOL_CANONICAL_STORY_ID:
        raise ValueError("review.story_id doit être l'identifiant Sol canonique")
    for requirement in ("fresh_context", "blind", "reviewer_read_only", "read_only"):
        if review.get(requirement) is not True:
            raise ValueError(f"review.{requirement} doit être true")
    if policy.get("terminal_states") != ["DONE_WITH_EVIDENCE", "BLOCKED_WITH_REASON"]:
        raise ValueError("terminal_states de politique d'autonomie invalides")
    return policy


def _canonical_sol_member() -> dict[str, str] | None:
    """Return Sol only when the active roster entry matches the policy contract exactly."""
    try:
        policy = load_autonomy_policy()
    except ValueError:
        return None
    if policy["review"]["reviewer_model"] != _SOL_CANONICAL_MODEL:
        return None
    roles = _load_roles_yaml(REPO / "manifests" / "roles.yaml")
    matches = [member for member in roles if member.get("id") == _SOL_CANONICAL_ID]
    if len(matches) != 1:
        return None
    member = matches[0]
    expected = {
        "id": _SOL_CANONICAL_ID,
        "modele": _SOL_CANONICAL_MODEL,
        "statut": _SOL_CANONICAL_STATUS,
        "vendor": _SOL_CANONICAL_VENDOR,
        "provider_id": _SOL_CANONICAL_PROVIDER_ID,
    }
    if any(member.get(field) != value for field, value in expected.items()):
        return None
    return expected


def _sol_aliases(table: dict[str, str] | None) -> set[str] | None:
    """Return only aliases of the exact canonical active Sol member."""
    member = _canonical_sol_member()
    if table is None or member is None:
        return None
    aliases = {
        _normalize(member["id"]),
        _normalize(member["provider_id"]),
        _normalize(member["modele"]),
    }
    if any(table.get(alias) != _SOL_CANONICAL_VENDOR for alias in aliases):
        return None
    return aliases


def _canonical_luna_member() -> dict[str, str] | None:
    """Return Luna writer only when the active roster entry is canonical and unique."""
    try:
        policy = load_autonomy_policy()
    except ValueError:
        return None
    if policy["worker"]["primary_model"] != _LUNA_CANONICAL_MODEL:
        return None
    roles = _load_roles_yaml(REPO / "manifests" / "roles.yaml")
    matches = [member for member in roles if member.get("id") == _SOL_CANONICAL_CODEUR_ID]
    if len(matches) != 1:
        return None
    member = matches[0]
    expected = {
        "id": _SOL_CANONICAL_CODEUR_ID,
        "modele": _LUNA_CANONICAL_MODEL,
        "statut": _LUNA_CANONICAL_STATUS,
        "vendor": _LUNA_CANONICAL_VENDOR,
        "provider_id": _LUNA_CANONICAL_PROVIDER_ID,
    }
    if any(member.get(field) != value for field, value in expected.items()):
        return None
    return expected


def _codeur_identity_table(
    roles_path: Path = REPO / "manifests" / "roles.yaml",
    *,
    include_retired: bool = False,
) -> dict[str, str] | None:
    """Resolve selectable codewriter aliases to canonical roster member IDs.

    Retired identities remain resolvable by legacy audit paths, but are not accepted for fresh
    ``sol_blind`` evidence unless an archive caller explicitly opts into them.
    """
    roles = _load_roles_yaml(roles_path)
    if not roles:
        return None
    table: dict[str, str] = {}
    for member in roles:
        if not include_retired and member.get("statut") == "retire":
            continue
        member_id = member.get("id")
        if not isinstance(member_id, str) or not member_id:
            continue
        aliases = [member.get("id"), member.get("provider_id"), member.get("modele")]
        for alias in aliases:
            if not isinstance(alias, str) or not alias:
                continue
            key = _normalize(alias)
            previous = table.get(key)
            if previous is not None and previous != member_id:
                return None
            table[key] = member_id
    return table or None


def _aware_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        timestamp = datetime.fromisoformat(value)
    except ValueError:
        return None
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        return None
    return timestamp


def _validation_time(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now().astimezone()
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("horloge de validation doit être un timestamp avec fuseau")
    return now


def _sol_window_hours(value: object, default: object) -> float:
    window = default if value is None else value
    if isinstance(window, bool) or not isinstance(window, (int, float)):
        raise ValueError("fenêtre Sol invalide")
    try:
        numeric_window = float(window)
    except (OverflowError, ValueError) as error:
        raise ValueError("fenêtre Sol invalide") from error
    if (
        not math.isfinite(numeric_window)
        or numeric_window < 0
        or numeric_window > _SOL_MAX_WINDOW_HOURS
    ):
        raise ValueError("fenêtre Sol invalide")
    return numeric_window


def _validate_sol_freshness(
    recu: dict,
    verdicts: list[dict],
    *,
    fenetre_heures_defaut: int | float = 24,
    now: datetime | None = None,
) -> None:
    """Validate current Sol receipt timestamps with an injectable validation clock."""
    if len(verdicts) != 1 or not isinstance(verdicts[0], dict):
        raise ValueError("sol_blind exige exactement un verdict objet")
    validation_time = _validation_time(now)
    receipt_time = _aware_timestamp(recu.get("date_heure"))
    receipt_reviewed_at = _aware_timestamp(recu.get("reviewed_at"))
    verdict_reviewed_at = _aware_timestamp(verdicts[0].get("reviewed_at"))
    if receipt_time is None:
        raise ValueError("date_heure du reçu doit avoir un fuseau")
    if receipt_reviewed_at is None or verdict_reviewed_at is None:
        raise ValueError("reviewed_at doit avoir un fuseau")
    if receipt_reviewed_at != verdict_reviewed_at:
        raise ValueError("reviewed_at du reçu ne correspond pas au verdict")
    verdict_date_value = verdicts[0].get("date_heure")
    verdict_date = None
    if verdict_date_value is not None:
        verdict_date = _aware_timestamp(verdict_date_value)
        if verdict_date is None:
            raise ValueError("date_heure du verdict doit avoir un fuseau")
    window = _sol_window_hours(recu.get("fenetre_heures"), fenetre_heures_defaut)
    if receipt_reviewed_at > receipt_time:
        raise ValueError("reviewed_at postérieur à date_heure")
    if verdict_date is not None and verdict_date < receipt_reviewed_at:
        raise ValueError("date_heure du verdict antérieure à reviewed_at")
    if receipt_time > validation_time + _SOL_CLOCK_SKEW:
        raise ValueError("date_heure du reçu futur")
    if receipt_reviewed_at > validation_time + _SOL_CLOCK_SKEW:
        raise ValueError("reviewed_at du verdict futur")
    if verdict_date is not None and verdict_date > validation_time + _SOL_CLOCK_SKEW:
        raise ValueError("date_heure du verdict futur")
    if validation_time - receipt_reviewed_at > timedelta(hours=window) + _SOL_CLOCK_SKEW:
        raise ValueError("preuve Sol périmée")


def _sol_expected_from_git(
    recu: dict,
    etat_git: dict | None,
    review_dir: Path,
    verdicts: list[dict],
    *,
    runner: GitRunner | None = None,
) -> dict:
    """Construit les attentes Sol depuis Git, le prompt stocké et le verdict séparé."""
    if not isinstance(recu, dict):
        raise ValueError("reçu Sol invalide")
    if recu.get("schema") != "recu-revue/2":
        raise ValueError("schema Sol doit être exactement recu-revue/2")
    required = (
        "story", "base_commit", "head_commit", "head_tree", "reviewed_head_commit",
        "reviewed_head_tree", "candidate_diff_digest", "diff_digest", "prompt_sha256",
        "sdd_diff_digest", "template_sha256", "reviewed_at",
    )
    for field in required:
        if field not in recu:
            raise ValueError(f"métadonnée Sol absente : {field}")
    _validate_sol_story_id(recu["story"], recu.get("issue"))
    for field in ("base_commit", "head_commit", "head_tree", "reviewed_head_commit", "reviewed_head_tree"):
        _validate_object_id(recu[field], field)
    for field in (
        "candidate_diff_digest", "diff_digest", "sdd_diff_digest", "prompt_sha256"
    ):
        _validate_digest(recu[field], field)
    execute = _default_runner if runner is None else runner
    base_commit = _resolve_commit(execute, recu["base_commit"])
    head_commit = _resolve_commit(execute, recu["head_commit"])
    head_tree = _resolve_commit_tree(execute, head_commit)
    reviewed_head_commit = _resolve_commit(execute, recu["reviewed_head_commit"])
    reviewed_head_tree = _resolve_commit_tree(execute, reviewed_head_commit)
    if recu["head_tree"] != head_tree:
        raise ValueError("head_tree différent de l'arbre Git du head_commit")
    if recu["reviewed_head_tree"] != reviewed_head_tree:
        raise ValueError("reviewed_head_tree différent de l'arbre Git examiné")
    canonical_digest = _diff_canonique(base_commit, reviewed_head_commit, runner=execute)
    _validate_digest(canonical_digest, "candidate_diff_digest Git")
    if recu["candidate_diff_digest"] != canonical_digest:
        raise ValueError("candidate_diff_digest différent du diff Git examiné")
    if recu["diff_digest"] != canonical_digest:
        raise ValueError("diff_digest différent du diff Git examiné")
    canonical_sdd_digest = _diff_sdd_canonique(
        base_commit, reviewed_head_commit, runner=execute
    )
    if recu["sdd_diff_digest"] != canonical_sdd_digest:
        raise ValueError("sdd_diff_digest différent du journal SDD Git examiné")
    if len(verdicts) != 1 or not isinstance(verdicts[0], dict):
        raise ValueError("sol_blind exige exactement un verdict objet")
    canonical_prompt, canonical_prompt_sha = _canonical_sol_prompt(
        recu["story"],
        base_commit,
        reviewed_head_commit,
        runner=execute,
    )
    template_content = _git_blob(execute, reviewed_head_commit, _SOL_TEMPLATE_PATH)
    template_sha = hashlib.sha256(template_content.encode("utf-8")).hexdigest()
    _validate_digest(recu["template_sha256"], "template_sha256")
    if recu["template_sha256"] != template_sha:
        raise ValueError("template_sha256 différent du template Git examiné")
    stored_prompt = _sol_prompt_bytes(review_dir)
    if stored_prompt != canonical_prompt:
        raise ValueError(
            f"{_SOL_PROMPT_FILENAME} différent du prompt Sol canonique généré depuis Git"
        )
    prompt_sha = hashlib.sha256(stored_prompt).hexdigest()
    if prompt_sha != canonical_prompt_sha:
        raise ValueError("sha256 du prompt canonique incohérent")
    if recu["prompt_sha256"] != prompt_sha:
        raise ValueError("prompt_sha256 différent des octets de SOL-PROMPT.md canonique")
    reviewed_at = verdicts[0].get("reviewed_at")
    if _aware_timestamp(reviewed_at) is None:
        raise ValueError("reviewed_at du verdict doit avoir un fuseau")
    if recu["reviewed_at"] != reviewed_at:
        raise ValueError("reviewed_at du reçu ne correspond pas au verdict")

    covers_current = False
    if etat_git is not None:
        current_base = _validate_object_id(etat_git.get("base_commit"), "base_commit courant")
        current_head = _validate_object_id(etat_git.get("head_commit"), "head_commit courant")
        current_tree = _validate_object_id(etat_git.get("head_tree"), "head_tree courant")
        current_digest = _validate_digest(etat_git.get("diff_digest"), "diff_digest courant")
        current_sdd_digest = _validate_digest(
            etat_git.get("sdd_diff_digest"), "sdd_diff_digest courant"
        )
        covers_current = (
            base_commit == current_base
            and canonical_digest == current_digest
            and recu["candidate_diff_digest"] == current_digest
            and recu["sdd_diff_digest"] == current_sdd_digest
        )
        # current_head/current_tree are resolved by _etat_git_reel; retaining the explicit
        # shape checks here prevents a malformed injected state from becoming an expectation.
        if not current_head or not current_tree:
            raise ValueError("état Git courant incomplet")
        _require_commit_ancestor(
            execute, head_commit, reviewed_head_commit, "head_commit"
        )
        _require_commit_ancestor(
            execute, reviewed_head_commit, current_head, "reviewed_head_commit"
        )
    return {
        "candidate_diff_digest": canonical_digest,
        "diff_digest": canonical_digest,
        "base_commit": base_commit,
        "head_commit": head_commit,
        "head_tree": head_tree,
        "reviewed_head_commit": reviewed_head_commit,
        "reviewed_head_tree": reviewed_head_tree,
        "prompt_sha256": prompt_sha,
        "sdd_diff_digest": canonical_sdd_digest,
        "template_sha256": template_sha,
        "reviewed_at": reviewed_at,
        "_covers_current": covers_current,
    }


def _sol_receipt_binding_matches_current(recu: object, etat_git: object) -> bool:
    """Classifie uniquement la liaison base/diff; full proof reste séparée."""
    if not isinstance(recu, dict) or not isinstance(etat_git, dict):
        return False
    try:
        receipt_base = _validate_object_id(recu.get("base_commit"), "base_commit")
        receipt_digest = _validate_digest(recu.get("diff_digest"), "diff_digest")
        candidate_digest = _validate_digest(
            recu.get("candidate_diff_digest"), "candidate_diff_digest"
        )
        receipt_sdd_digest = _validate_digest(
            recu.get("sdd_diff_digest"), "sdd_diff_digest"
        )
        current_base = _validate_object_id(etat_git.get("base_commit"), "base_commit courant")
        current_digest = _validate_digest(etat_git.get("diff_digest"), "diff_digest courant")
        current_sdd_digest = _validate_digest(
            etat_git.get("sdd_diff_digest"), "sdd_diff_digest courant"
        )
    except ValueError:
        return False
    return (
        receipt_base == current_base
        and receipt_digest == current_digest
        and candidate_digest == current_digest
        and receipt_sdd_digest == current_sdd_digest
    )


def tally_sol_blind(
    verdicts: list[dict],
    expected: dict,
    codeurs: list[str],
    *,
    allow_retired_codeurs: bool = False,
) -> dict:
    """Dépouille strictement l'unique verdict frais du reviewer Sol."""
    if not isinstance(verdicts, list) or len(verdicts) != 1:
        count = len(verdicts) if isinstance(verdicts, list) else "invalide"
        return {"result": "INVALIDE", "reason": f"sol_blind exige exactement 1 verdict (reçu: {count})"}
    verdict = verdicts[0]
    if not isinstance(verdict, dict):
        return {"result": "INVALIDE", "reason": "verdict Sol invalide"}
    try:
        load_autonomy_policy()
    except ValueError as error:
        return {"result": "INVALIDE", "reason": str(error)}

    table = _vendor_table()
    sol_aliases = _sol_aliases(table)
    if sol_aliases is None:
        return {
            "result": "INVALIDE",
            "reason": "identité Sol active absente du roster ou non vérifiable",
        }
    reviewer_model = verdict.get("reviewer_model")
    if reviewer_model != _SOL_CANONICAL_PROVIDER_ID:
        return {
            "result": "INVALIDE",
            "reason": "reviewer_model n'est pas l'identité provider canonique Sol",
        }
    if "vendor" in verdict:
        vendor = verdict.get("vendor")
        if not isinstance(vendor, str) or _normalize(vendor) not in {
            _normalize(_SOL_CANONICAL_ID),
            _normalize(_SOL_CANONICAL_VENDOR),
        }:
            return {"result": "INVALIDE", "reason": "vendor du reviewer n'est pas Sol/openai"}

    if not isinstance(codeurs, list) or not codeurs:
        return {"result": "INVALIDE", "reason": "codeur requis pour sol_blind"}
    codeur_table = _codeur_identity_table(include_retired=allow_retired_codeurs)
    if codeur_table is None:
        return {"result": "INVALIDE", "reason": "roster de codeurs introuvable"}
    if not allow_retired_codeurs and _canonical_luna_member() is None:
        return {
            "result": "INVALIDE",
            "reason": "identité active canonique luna_writer absente du roster",
        }
    resolved_codeurs = []
    for codeur in codeurs:
        if not isinstance(codeur, str):
            return {"result": "INVALIDE", "reason": f"codeur invalide : {codeur!r}"}
        codeur_key = _normalize(codeur)
        if codeur_key not in codeur_table:
            return {"result": "INVALIDE", "reason": f"codeur inconnu : {codeur}"}
        resolved_codeurs.append(codeur_table[codeur_key])
        if codeur_table[codeur_key] == _SOL_CANONICAL_ID:
            return {"result": "INVALIDE", "reason": "le codeur ne peut pas être Sol"}
    if not allow_retired_codeurs and (
        len(resolved_codeurs) != 1 or resolved_codeurs[0] != _SOL_CANONICAL_CODEUR_ID
    ):
        return {
            "result": "INVALIDE",
            "reason": "le codeur Sol frais doit résoudre vers luna_writer",
        }

    for field in ("fresh_context", "blind", "reviewer_read_only"):
        if verdict.get(field) is not True:
            return {"result": "INVALIDE", "reason": f"{field} doit être true"}

    if not isinstance(expected, dict):
        return {"result": "INVALIDE", "reason": "métadonnées attendues invalides"}
    expected_fields = (
        "candidate_diff_digest", "diff_digest", "base_commit", "reviewed_head_commit",
        "reviewed_head_tree", "prompt_sha256", "sdd_diff_digest", "template_sha256",
        "reviewed_at",
    )
    missing = [field for field in expected_fields if field not in expected]
    if missing:
        return {"result": "INVALIDE", "reason": f"métadonnées attendues absentes : {missing[0]}"}
    try:
        for field in ("base_commit", "reviewed_head_commit", "reviewed_head_tree"):
            _validate_object_id(expected[field], field)
        for field in (
            "candidate_diff_digest", "diff_digest", "sdd_diff_digest", "prompt_sha256",
            "template_sha256",
        ):
            _validate_digest(expected[field], field)
    except ValueError as error:
        return {"result": "INVALIDE", "reason": str(error)}
    if expected["candidate_diff_digest"] != expected["diff_digest"]:
        return {"result": "INVALIDE", "reason": "diff_digest différent du diff attendu"}
    expected_digest = expected["candidate_diff_digest"]
    if verdict.get("candidate_diff_digest") != expected_digest:
        return {"result": "INVALIDE", "reason": "candidate_diff_digest différent du diff attendu"}
    try:
        _validate_digest(verdict.get("candidate_diff_digest"), "candidate_diff_digest verdict")
        for field in ("base_commit", "reviewed_head_commit", "reviewed_head_tree"):
            _validate_object_id(verdict.get(field), f"{field} verdict")
        for field in ("prompt_sha256", "sdd_diff_digest", "template_sha256"):
            _validate_digest(verdict.get(field), f"{field} verdict")
    except ValueError as error:
        return {"result": "INVALIDE", "reason": str(error)}
    for field in (
        "base_commit", "reviewed_head_commit", "reviewed_head_tree",
        "prompt_sha256", "sdd_diff_digest", "template_sha256",
    ):
        if verdict.get(field) != expected[field]:
            return {"result": "INVALIDE", "reason": f"{field} différent des métadonnées attendues"}
    if verdict.get("reviewed_at") != expected["reviewed_at"]:
        return {"result": "INVALIDE", "reason": "reviewed_at différent ou non frais"}
    if _aware_timestamp(verdict.get("reviewed_at")) is None:
        return {"result": "INVALIDE", "reason": "reviewed_at doit être un timestamp avec fuseau"}
    if verdict.get("verdict") != "APPROVE":
        return {"result": "REJECT", "reason": "verdict Sol différent de APPROVE"}
    if verdict.get("blocking_findings") != []:
        return {"result": "REJECT", "reason": "blocking_findings non vide"}
    return {
        "result": "APPROVE",
        "reason": "Sol APPROVE sur le diff exact",
        "vendors": ["openai"],
        "reviewer_model": reviewer_model,
        "prompt_sha256": expected["prompt_sha256"],
        "sdd_diff_digest": expected["sdd_diff_digest"],
        "template_sha256": expected["template_sha256"],
        "reviewed_at": expected["reviewed_at"],
        "blocking_findings": [],
    }


def tally(verdicts: list[dict]) -> dict:
    """Dépouillement déterministe. Retourne {result, reason, vendors, objections, prompt_sha256,
    bloquantes}. APPROVE ssi tous les verdicts sont APPROVE ET aucune objection bloquante."""
    table = _vendor_table()
    if table is None:
        return {
            "result": "INVALIDE",
            "reason": "roster de vendors introuvable ou illisible (manifests/roles.yaml) — identité des reviewers non vérifiable",
        }
    if len(verdicts) < 3:
        return {"result": "INVALIDE", "reason": f"{len(verdicts)} verdict(s) < 3 requis"}
    shas = {v.get("prompt_sha256") for v in verdicts}
    if len(shas) != 1 or None in shas:
        return {"result": "INVALIDE",
                "reason": f"prompts non identiques (sha distincts : {sorted(s or 'MANQUANT' for s in shas)})"}
    vendors = [vendor_of(v.get("vendor") or v.get("reviewer_model", ""), table) for v in verdicts]
    # Anti-Sybil (revue aveugle Nemotron) : un vendor NON reconnu ne peut pas compter comme
    # « distinct » — sinon des chaînes bidon simuleraient la diversité de vendors exigée.
    known_vendors = set(table.values())
    inconnus = sorted(set(vendors) - known_vendors)
    if inconnus:
        return {"result": "INVALIDE",
                "reason": f"vendor(s) inconnu(s), identité non vérifiable : {inconnus}"}
    distinct = set(vendors)
    if len(distinct) < 3:
        return {"result": "INVALIDE",
                "reason": f"{len(distinct)} vendor(s) distinct(s) < 3 (vus : {sorted(distinct)})"}
    raw = [str(v.get("verdict", "")).upper() for v in verdicts]
    if any(r not in ("APPROVE", "REJECT") for r in raw):
        return {"result": "INVALIDE", "reason": f"verdict hors APPROVE/REJECT : {raw}"}
    objections = [o for v in verdicts for o in v.get("objections", [])]
    objections.sort(key=lambda o: _SEVERITY_RANK.get(_severity(o), 9))
    bloquantes = [o for o in objections if _severity(o) in _BLOCKING]
    result = "APPROVE" if all(r == "APPROVE" for r in raw) and not bloquantes else "REJECT"
    reason = f"{raw.count('APPROVE')}/{len(raw)} APPROVE"
    if bloquantes:
        reason += "; objection bloquante"
    return {"result": result, "reason": reason,
            "vendors": sorted(distinct), "prompt_sha256": shas.pop(),
            "objections": objections, "bloquantes": bloquantes}


def _verifier_recu_multi_vendor(
    recu: dict,
    verdicts: list[dict],
    etat_git: dict,
    *,
    fenetre_heures_defaut: int | float = 24,
) -> dict:
    """Vérifie PUREMENT un reçu de revue (reviews/<ID>/RECU.json) contre son état git déjà
    résolu (aucun appel git ici — testable sans git réel, cf. `_etat_git_reel` pour
    l'adaptateur). Le reçu est un CLAIM écrit par l'Orchestrateur ; cette fonction le RÉFUTE
    mécaniquement, jamais l'inverse.

    Retourne {result: APPROVE|REJECT|INVALIDE, reason: str, ...infos de tally si APPROVE}.
    """
    required = (
        "schema", "dossier", "issue", "round", "base_commit", "head_commit", "head_tree",
        "diff_digest", "prompt_sha256", "reviewers_attendus", "codeur", "resultat",
        "date_heure", "fenetre_heures",
    )
    if not isinstance(recu, dict):
        return {"result": "INVALIDE", "reason": "données absentes : reçu"}
    for key in required:
        if key not in recu:
            return {"result": "INVALIDE", "reason": f"données absentes : {key}"}
    if isinstance(recu["round"], bool) or not isinstance(recu["round"], int) or recu["round"] <= 0:
        return {"result": "INVALIDE", "reason": "round invalide"}

    # Liaison au commit/diff : PAS d'égalité stricte sur head_commit/head_tree — un reçu
    # correctement généré (`revue.py recu`) puis COMMIS ne peut structurellement JAMAIS
    # contenir le hash exact du commit/arbre qui l'inclut lui-même (paradoxe d'auto-référence
    # trouvé par revue scellée RC1-004-PR497, DeepSeek-V4-Pro — critique). head_commit/
    # head_tree restent des champs REQUIS du schéma (traçabilité/audit), mais la garantie de
    # liaison réelle repose sur base_commit (jamais auto-référentiel — c'est l'état de
    # base_ref, pas de cette PR) et diff_digest (DÉJÀ insensible à l'auto-référence : il
    # exclut reviews/** des deux côtés de la comparaison, donc committer le reçu APRÈS l'avoir
    # généré ne change jamais ce digest).
    if recu["base_commit"] != etat_git.get("base_commit"):
        return {"result": "INVALIDE", "reason": "reçu lié à un autre commit"}
    if recu["diff_digest"] != etat_git.get("diff_digest"):
        return {"result": "INVALIDE", "reason": "diff modifié après revue"}

    tally_result = tally(verdicts)
    if tally_result["result"] != "APPROVE":
        return {"result": tally_result["result"], "reason": tally_result["reason"]}
    if recu["prompt_sha256"] != tally_result.get("prompt_sha256"):
        return {"result": "INVALIDE", "reason": "réponse contradictoire"}
    if recu["resultat"] != tally_result["result"]:
        return {"result": "INVALIDE", "reason": "réponse contradictoire"}

    reviewers = recu["reviewers_attendus"]
    if not isinstance(reviewers, list) or len(reviewers) < 3 or len(reviewers) != len(verdicts):
        return {"result": "INVALIDE", "reason": "nombre incorrect de reviewers"}

    codeurs = recu["codeur"]
    # OBLIGATOIREMENT non vide ICI (pas seulement dans la CLI `recu`, round 2 — objection
    # critique DeepSeek-V4-Pro round 2 : verifier_recu EST la frontière d'application réelle
    # du gate ; un RECU.json écrit/modifié à la main avec codeur:[] contournerait sinon
    # totalement l'anti-auto-review, peu importe ce que la CLI exige).
    if not isinstance(codeurs, list) or not codeurs:
        return {"result": "INVALIDE", "reason": "codeur requis (liste vide)"}
    codeur_table = _codeur_vendor_table()
    if codeur_table is None:
        return {"result": "INVALIDE", "reason": "roster de codeurs introuvable"}
    vendors_codeurs = set()
    for codeur in codeurs:
        if not isinstance(codeur, str) or _normalize(codeur) not in codeur_table:
            return {"result": "INVALIDE", "reason": f"codeur inconnu : {codeur}"}
        vendors_codeurs.add(codeur_table[_normalize(codeur)])
    if vendors_codeurs & set(tally_result["vendors"]):
        return {"result": "INVALIDE", "reason": "l'auteur ne peut pas être reviewer"}

    try:
        receipt_date = datetime.fromisoformat(str(recu["date_heure"]))
        window = recu.get("fenetre_heures", fenetre_heures_defaut)
        if isinstance(window, bool) or not isinstance(window, (int, float)) or window < 0:
            raise ValueError("fenêtre invalide")
        verdict_dates = []
        for verdict in verdicts:
            if not verdict.get("date_heure"):
                return {"result": "INVALIDE", "reason": "verdict périmé"}
            verdict_dates.append(datetime.fromisoformat(str(verdict["date_heure"])))
        if not verdict_dates:
            return {"result": "INVALIDE", "reason": "verdict périmé"}
        min_gap = abs((receipt_date - min(verdict_dates)).total_seconds()) / 3600
        max_gap = abs((receipt_date - max(verdict_dates)).total_seconds()) / 3600
    except (TypeError, ValueError):
        return {"result": "INVALIDE", "reason": "verdict périmé"}
    if min_gap > window or max_gap > window:
        return {"result": "INVALIDE", "reason": "verdict périmé"}

    return {
        **tally_result,
        "result": "APPROVE",
        "reason": f"reçu valide, lié au commit {etat_git['head_commit']}",
    }


def _verifier_recu_sol_blind(
    recu: dict,
    verdicts: list[dict],
    etat_git: dict,
    *,
    review_dir: Path | None = None,
    runner: GitRunner | None = None,
    fenetre_heures_defaut: int | float = 24,
    now: datetime | None = None,
) -> dict:
    required = (
        "schema", "mode", "story", "dossier", "issue", "round", "base_commit", "head_commit",
        "head_tree", "diff_digest", "candidate_diff_digest", "reviewed_head_commit",
        "reviewed_head_tree", "prompt_sha256", "sdd_diff_digest", "template_sha256",
        "reviewers_attendus",
        "codeur", "resultat",
        "reviewed_at", "verdict", "reviewer_model", "date_heure",
        "fenetre_heures", "blocking_findings",
    )
    if not isinstance(recu, dict):
        return {"result": "INVALIDE", "reason": "données absentes : reçu"}
    for key in required:
        if key not in recu:
            return {"result": "INVALIDE", "reason": f"données absentes : {key}"}
    if recu.get("schema") != "recu-revue/2":
        return {"result": "INVALIDE", "reason": "schema Sol doit être exactement recu-revue/2"}
    if recu.get("mode") != "sol_blind":
        return {"result": "INVALIDE", "reason": "mode de reçu inconnu"}
    if not isinstance(etat_git, dict):
        return {"result": "INVALIDE", "reason": "état Git courant invalide"}
    try:
        _validate_sol_dossier(recu["dossier"])
    except ValueError as error:
        return {"result": "INVALIDE", "reason": str(error)}
    try:
        current_base = _validate_object_id(etat_git.get("base_commit"), "base_commit courant")
        current_digest = _validate_digest(etat_git.get("diff_digest"), "diff_digest courant")
        current_sdd_digest = _validate_digest(
            etat_git.get("sdd_diff_digest"), "sdd_diff_digest courant"
        )
    except ValueError as error:
        return {"result": "INVALIDE", "reason": str(error)}
    if recu["base_commit"] != current_base:
        return {"result": "INVALIDE", "reason": "reçu lié à un autre commit"}
    if recu["diff_digest"] != current_digest:
        return {"result": "INVALIDE", "reason": "diff modifié après revue"}
    if recu["candidate_diff_digest"] != current_digest:
        return {"result": "INVALIDE", "reason": "candidate_diff_digest différent du diff courant"}
    if recu["sdd_diff_digest"] != current_sdd_digest:
        return {"result": "INVALIDE", "reason": "sdd_diff_digest différent du journal SDD courant"}
    try:
        _validate_digest(recu["sdd_diff_digest"], "sdd_diff_digest")
        _validate_digest(recu["template_sha256"], "template_sha256")
    except ValueError as error:
        return {"result": "INVALIDE", "reason": str(error)}
    try:
        _validate_sol_freshness(
            recu,
            verdicts,
            fenetre_heures_defaut=fenetre_heures_defaut,
            now=now,
        )
    except ValueError as error:
        return {"result": "INVALIDE", "reason": str(error)}
    if review_dir is None:
        return {"result": "INVALIDE", "reason": f"{_SOL_PROMPT_FILENAME} requis pour sol_blind"}
    try:
        _validate_sol_dossier(recu["dossier"], Path(review_dir))
    except ValueError as error:
        return {"result": "INVALIDE", "reason": str(error)}
    try:
        expected = _sol_expected_from_git(
            recu, etat_git, Path(review_dir), verdicts, runner=runner
        )
    except (OSError, TypeError, ValueError, subprocess.CalledProcessError) as error:
        return {"result": "INVALIDE", "reason": f"preuve Git/prompt Sol invalide : {error}"}
    tally_result = tally_sol_blind(verdicts, expected=expected, codeurs=recu["codeur"])
    if tally_result["result"] != "APPROVE":
        return {"result": tally_result["result"], "reason": tally_result["reason"]}
    if recu["prompt_sha256"] != tally_result.get("prompt_sha256"):
        return {"result": "INVALIDE", "reason": "réponse contradictoire"}
    if recu["template_sha256"] != tally_result.get("template_sha256"):
        return {"result": "INVALIDE", "reason": "template_sha256 du reçu contradictoire"}
    if recu["sdd_diff_digest"] != tally_result.get("sdd_diff_digest"):
        return {"result": "INVALIDE", "reason": "sdd_diff_digest du reçu contradictoire"}
    if recu["resultat"] != tally_result["result"]:
        return {"result": "INVALIDE", "reason": "réponse contradictoire"}
    if recu["blocking_findings"] != []:
        return {"result": "REJECT", "reason": "blocking_findings du reçu non vide"}
    if recu["blocking_findings"] != verdicts[0].get("blocking_findings"):
        return {
            "result": "INVALIDE",
            "reason": "blocking_findings du reçu différent du verdict Sol",
        }
    reviewers = recu["reviewers_attendus"]
    if not isinstance(reviewers, list) or len(reviewers) != 1:
        return {"result": "INVALIDE", "reason": "nombre incorrect de reviewers Sol"}
    reviewer_model = verdicts[0].get("reviewer_model") if verdicts else None
    if reviewers != [reviewer_model]:
        return {"result": "INVALIDE", "reason": "identité reviewer contradictoire"}
    if recu["reviewer_model"] != reviewer_model or recu["verdict"] != verdicts[0].get("verdict"):
        return {"result": "INVALIDE", "reason": "verdict Sol contradictoire dans le reçu"}
    return {
        **tally_result,
        "result": "APPROVE",
        "reason": f"reçu Sol valide, lié au commit {etat_git.get('head_commit')}",
    }


def _validate_sol_archive_receipt(
    recu: object,
    execute: GitRunner,
    *,
    verdicts: list[dict] | None = None,
    review_dir: Path | None = None,
) -> None:
    """Validate the immutable Sol receipt contract and exact archive object IDs."""
    if not isinstance(recu, dict):
        raise ValueError("reçu Sol archive invalide")
    required = (
        "schema", "mode", "story", "dossier", "issue", "round", "base_commit",
        "head_commit", "head_tree", "candidate_diff_digest", "diff_digest",
        "reviewed_head_commit", "reviewed_head_tree", "prompt_sha256",
        "sdd_diff_digest", "template_sha256", "reviewers_attendus", "codeur", "resultat",
        "reviewed_at", "verdict",
        "reviewer_model", "date_heure", "fenetre_heures", "blocking_findings",
    )
    for field in required:
        if field not in recu:
            raise ValueError(f"métadonnée Sol archive absente : {field}")
    if recu.get("schema") != "recu-revue/2":
        raise ValueError("schema Sol doit être exactement recu-revue/2")
    if recu.get("mode") != "sol_blind":
        raise ValueError("mode Sol archive invalide")
    _validate_sol_story_id(recu["story"], recu.get("issue"))
    _validate_sol_dossier(recu["dossier"], review_dir)
    if recu["resultat"] != "APPROVE":
        raise ValueError("resultat Sol archive doit être APPROVE")
    if recu["verdict"] != "APPROVE":
        raise ValueError("verdict Sol archive doit être APPROVE")
    if recu["blocking_findings"] != []:
        raise ValueError("blocking_findings Sol archive doit être vide")
    reviewers = recu["reviewers_attendus"]
    if not isinstance(reviewers, list) or len(reviewers) != 1:
        raise ValueError("reviewers_attendus Sol archive invalide")
    if reviewers != [recu["reviewer_model"]]:
        raise ValueError("reviewer_model Sol archive contradictoire")
    if not isinstance(recu["codeur"], list) or not recu["codeur"]:
        raise ValueError("codeur Sol archive requis")
    if verdicts is not None:
        if len(verdicts) != 1 or not isinstance(verdicts[0], dict):
            raise ValueError("sol_blind exige exactement un verdict objet")
        verdict = verdicts[0]
        for field in (
            "reviewer_model",
            "verdict",
            "blocking_findings",
            "reviewed_at",
            "sdd_diff_digest",
            "template_sha256",
        ):
            if recu[field] != verdict.get(field):
                raise ValueError(f"{field} du reçu Sol archive contradictoire")
        if review_dir is None:
            raise ValueError("dossier de revue Sol archive requis")
        expected = _sol_expected_from_git(
            recu, None, Path(review_dir), verdicts, runner=execute
        )
        tally_result = tally_sol_blind(
            verdicts,
            expected=expected,
            codeurs=recu["codeur"],
            allow_retired_codeurs=True,
        )
        if tally_result["result"] != "APPROVE":
            raise ValueError(
                f"verdict Sol archive non conforme : {tally_result.get('reason', '')}"
            )
    for field in (
        "base_commit", "head_commit", "head_tree", "reviewed_head_commit",
        "reviewed_head_tree",
    ):
        _validate_object_id(recu.get(field), field)
    for field in ("base_commit", "head_commit", "reviewed_head_commit"):
        _resolve_commit(execute, recu[field])
    for field in (
        "candidate_diff_digest", "diff_digest", "sdd_diff_digest", "prompt_sha256",
        "template_sha256",
    ):
        _validate_digest(recu[field], field)
    for commit_field, tree_field in (
        ("head_commit", "head_tree"),
        ("reviewed_head_commit", "reviewed_head_tree"),
    ):
        actual_tree = execute(
            ["git", "rev-parse", "--verify", f"{recu[commit_field]}^{{tree}}"]
        ).strip()
        _validate_object_id(actual_tree, f"{commit_field} tree Git")
        if actual_tree != recu[tree_field]:
            raise ValueError(f"{tree_field} différent de l'arbre Git du commit")


def verifier_recu(
    recu: dict,
    verdicts: list[dict],
    etat_git: dict,
    *,
    fenetre_heures_defaut: int | float = 24,
    review_dir: Path | None = None,
    runner: GitRunner | None = None,
    now: datetime | None = None,
) -> dict:
    """Dispatch le mode explicite; les reçus sans mode restent multi-vendor."""
    if isinstance(recu, dict):
        mode = recu.get("mode", "multi_vendor")
        if mode == "sol_blind":
            return _verifier_recu_sol_blind(
                recu,
                verdicts,
                etat_git,
                review_dir=review_dir,
                runner=runner,
                fenetre_heures_defaut=fenetre_heures_defaut,
                now=now,
            )
        if mode not in ("multi_vendor", "sol_blind"):
            return {"result": "INVALIDE", "reason": f"mode de reçu inconnu : {mode!r}"}
    return _verifier_recu_multi_vendor(
        recu, verdicts, etat_git, fenetre_heures_defaut=fenetre_heures_defaut
    )


def _cmd_prompt(args) -> int:
    artefact = Path(args.artefact).read_text(encoding="utf-8")
    criteres = Path(args.criteres).read_text(encoding="utf-8") if args.criteres else "(voir story)"
    mode = getattr(args, "mode", "multi_vendor")
    template_content = None
    if mode == "sol_blind":
        base_ref = getattr(args, "base_ref", None)
        if not base_ref:
            raise ValueError("--base-ref est obligatoire avec --mode sol_blind")
        if not args.out or Path(args.out).name != _SOL_PROMPT_FILENAME:
            raise ValueError(f"--out doit désigner {_SOL_PROMPT_FILENAME} en mode sol_blind")
        head_ref = getattr(args, "head_ref", "HEAD")
        git_state = _etat_git_reel(base_ref, head_ref)
        frozen_base = _validate_object_id(git_state["base_commit"], "base_commit Git")
        frozen_head = _validate_object_id(git_state["head_commit"], "head_commit Git")
        canonical_artifact = _diff_artifact_canonique(frozen_base, frozen_head)
        if artefact != canonical_artifact:
            raise ValueError("artefact fourni différent du diff Git canonique")
        artefact = canonical_artifact
        base_ref = frozen_base
        head_ref = frozen_head
        criteres = _SOL_CRITERIA
        template_content = _git_blob(_default_runner, frozen_head, _SOL_TEMPLATE_PATH)
        artefact_path = _SOL_ARTIFACT_PATH
    else:
        base_ref = None
        head_ref = None
        artefact_path = args.artefact
    prompt, sha = build_prompt(
        args.story,
        criteres,
        artefact_path,
        artefact,
        mode=mode,
        base_ref=base_ref,
        head_ref=head_ref,
        template_content=template_content,
    )
    if args.out:
        Path(args.out).write_text(prompt, encoding="utf-8")
    else:
        print(prompt)
    print(f"\n# prompt_sha256={sha}", file=sys.stderr)
    return 0


def _cmd_tally(args) -> int:
    verdicts = [json.loads(p.read_text(encoding="utf-8"))
                for p in sorted(Path(args.dossier).glob("*.verdict.json"))]
    res = tally(verdicts)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0 if res.get("result") == "APPROVE" else 1


def _cmd_recu(args) -> int:
    # RC1-010 (#440) lot 5d : reviews/ est intégralement migré vers evidence/reviews/.
    dossier = REPO / "evidence" / "reviews" / args.dossier
    verdicts = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(dossier.glob("*.verdict.json"))
    ]
    etat = _etat_git_reel(args.base_ref, args.head_ref)
    mode = getattr(args, "mode", "multi_vendor")
    if mode == "sol_blind":
        template_sha256 = None
        sdd_diff_digest = None
        story = getattr(args, "story", None)
        if not isinstance(story, str) or not story.strip():
            raise ValueError("--story est obligatoire avec --mode sol_blind")
        _validate_sol_story_id(story, args.issue)
        try:
            canonical_prompt, prompt_sha = _canonical_sol_prompt(
                story,
                etat["base_commit"],
                etat["head_commit"],
            )
            if _sol_prompt_bytes(dossier) != canonical_prompt:
                raise ValueError(
                    f"{_SOL_PROMPT_FILENAME} différent du prompt Sol canonique généré depuis Git"
                )
        except (OSError, ValueError, subprocess.CalledProcessError) as error:
            prompt_sha = None
            result = {"result": "INVALIDE", "reason": str(error)}
        if len(verdicts) != 1:
            result = {"result": "INVALIDE", "reason": "sol_blind exige exactement 1 verdict"}
        elif prompt_sha is not None:
            prompt_metadata = _sol_prompt_metadata(canonical_prompt)
            template_sha256 = prompt_metadata["template_sha256"]
            sdd_diff_digest = prompt_metadata["sdd_diff_digest"]
            expected = {
                **etat,
                "candidate_diff_digest": etat["diff_digest"],
                "reviewed_head_commit": etat["head_commit"],
                "reviewed_head_tree": etat["head_tree"],
                "prompt_sha256": prompt_sha,
                "sdd_diff_digest": sdd_diff_digest,
                "template_sha256": template_sha256,
                "reviewed_at": verdicts[0].get("reviewed_at"),
            }
            result = tally_sol_blind(verdicts, expected=expected, codeurs=args.codeur)
        reviewer = verdicts[0] if len(verdicts) == 1 else {}
        recu = {
            "schema": "recu-revue/2",
            "mode": "sol_blind",
            "story": story,
            "dossier": args.dossier,
            "issue": args.issue,
            "round": args.round,
            "replanned": getattr(args, "replanned", False),
            **etat,
            "candidate_diff_digest": etat["diff_digest"],
            "reviewed_head_commit": etat["head_commit"],
            "reviewed_head_tree": etat["head_tree"],
            "prompt_sha256": result.get("prompt_sha256"),
            "reviewers_attendus": [reviewer.get("reviewer_model", "")],
            "codeur": args.codeur,
            "resultat": result["result"],
            "reviewed_at": reviewer.get("reviewed_at"),
            "verdict": reviewer.get("verdict"),
            "reviewer_model": reviewer.get("reviewer_model"),
            "template_sha256": template_sha256,
            "sdd_diff_digest": sdd_diff_digest,
            "blocking_findings": reviewer.get("blocking_findings", []),
            "date_heure": datetime.now().astimezone().isoformat(),
            "fenetre_heures": args.fenetre_heures,
        }
    else:
        result = tally(verdicts)
        recu = {
            "schema": "recu-revue/1",
            "dossier": args.dossier,
            "issue": args.issue,
            "round": args.round,
            "replanned": getattr(args, "replanned", False),
            **etat,
            "prompt_sha256": result.get("prompt_sha256"),
            "reviewers_attendus": [
                v.get("vendor") or v.get("reviewer_model", "") for v in verdicts
            ],
            "codeur": args.codeur,
            "resultat": result["result"],
            "date_heure": datetime.now().astimezone().isoformat(),
            "fenetre_heures": args.fenetre_heures,
        }
    content = json.dumps(recu, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(content + "\n", encoding="utf-8")
    else:
        print(content)
    return 0


def _cmd_diff_canonique(args) -> int:
    print(_diff_canonique(args.base_ref, args.head_ref))
    return 0


def main() -> None:
    import argparse
    p = argparse.ArgumentParser(prog="revue.py")
    sub = p.add_subparsers(dest="cmd", required=True)

    pp = sub.add_parser("prompt", help="génère le prompt de revue neutre + sha256")
    pp.add_argument("--artefact", required=True)
    pp.add_argument("--story", required=True)
    pp.add_argument("--criteres", default=None)
    pp.add_argument("--mode", choices=("multi_vendor", "sol_blind"), default="multi_vendor")
    pp.add_argument("--base-ref", default=None)
    pp.add_argument("--head-ref", default="HEAD")
    pp.add_argument("--out", default=None)
    pp.set_defaults(func=_cmd_prompt)

    pt = sub.add_parser("tally", help="dépouille les *.verdict.json d'un dossier (déterministe)")
    pt.add_argument("dossier")
    pt.set_defaults(func=_cmd_tally)

    pr = sub.add_parser("recu", help="génère un reçu lié à l'état git courant (#434)")
    pr.add_argument("--dossier", required=True)
    pr.add_argument("--base-ref", required=True)
    pr.add_argument("--head-ref", default="HEAD")
    pr.add_argument("--issue", required=True, type=int)
    pr.add_argument("--round", required=True, type=int)
    pr.add_argument("--mode", choices=("multi_vendor", "sol_blind"), default="multi_vendor")
    pr.add_argument(
        "--story",
        default=None,
        help="identifiant immuable de la story pour --mode sol_blind",
    )
    pr.add_argument("--replanned", action="store_true")
    # OBLIGATOIRE (≥1) : un --codeur silencieusement optionnel (défaut []) permettait de
    # contourner l'anti-auto-review par simple omission (revue scellée RC1-004-PR497,
    # DeepSeek-V4-Pro — majeure). verifier_recu() reste tolérant à une liste vide construite
    # directement (cas de test/receipt manuel), mais l'outil de génération FORCE la
    # déclaration explicite.
    pr.add_argument("--codeur", action="append", required=True)
    pr.add_argument("--fenetre-heures", type=int, default=24)
    pr.add_argument("--out", default=None)
    pr.set_defaults(func=_cmd_recu)

    pd = sub.add_parser("diff-canonique", help="calcule l'empreinte canonique du diff (#434)")
    pd.add_argument("--base-ref", required=True)
    pd.add_argument("--head-ref", default="HEAD")
    pd.set_defaults(func=_cmd_diff_canonique)

    args = p.parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
