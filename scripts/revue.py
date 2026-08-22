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
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable

_PLACEHOLDER = re.compile(r"\{(story_id|criteres|artefact_path|artefact)\}")
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


def _sol_prompt_sha256(review_dir: Path) -> str:
    prompt_path = review_dir / _SOL_PROMPT_FILENAME
    if not prompt_path.is_file():
        raise ValueError(f"{_SOL_PROMPT_FILENAME} absent du dossier de revue")
    try:
        prompt_bytes = prompt_path.read_bytes()
    except OSError as error:
        raise ValueError(f"{_SOL_PROMPT_FILENAME} illisible") from error
    return hashlib.sha256(prompt_bytes).hexdigest()


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
            ":(exclude)governance/path-classification.json",
            ":(exclude)governance/PATH-CLASSIFICATION.md",
        ]
    )


def _diff_canonique(
    base_ref: str,
    head_ref: str,
    *,
    # RC1-010 (#440) lot 5d : reviews/ est intégralement migré vers evidence/reviews/ — le
    # préfixe legacy "reviews/" est retiré de l'exclusion par défaut (mort : plus aucun fichier
    # de revue n'y vit).
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
    final (les reviewers ont vu un diff SANS ces fichiers). Même raisonnement pour
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
    }


def build_prompt(story_id: str, criteres: str, artefact_path: str, artefact: str,
                 template_path: Path = TEMPLATE, *, mode: str = "multi_vendor",
                 expected: dict | None = None, base_ref: str | None = None,
                 head_ref: str | None = None, runner: GitRunner | None = None) -> tuple[str, str]:
    """Rend (prompt_exact, sha256). Le template est lu au canon ; aucun texte n'est ajouté."""
    tpl = template_path.read_text(encoding="utf-8")
    # On ne garde que le corps (après le commentaire HTML d'en-tête) pour le prompt envoyé.
    # Le marqueur est OBLIGATOIRE : sans lui, l'en-tête (instructions internes) fuiterait dans
    # le prompt envoyé aux reviewers → non-neutralité (revue aveugle Nemotron). On échoue fort.
    if "-->" not in tpl:
        raise ValueError(f"template {template_path} sans marqueur '-->' : en-tête non séparable")
    tpl = tpl.split("-->", 1)[1].lstrip("\n")
    values = {"story_id": story_id, "criteres": criteres.strip(),
              "artefact_path": artefact_path, "artefact": artefact}
    # Substitution EN UN SEUL PASSAGE (re.sub) : le texte substitué n'est JAMAIS re-scanné,
    # donc un champ contenant « {artefact} » ne peut pas injecter un autre champ. Corrige le
    # défaut d'injection croisée des .replace() chaînés (revue aveugle Qwen, criterion #4).
    prompt = _PLACEHOLDER.sub(lambda m: values[m.group(1)], tpl)
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
        }
        if expected is not None:
            for field, value in metadata.items():
                expected_value = expected.get(field)
                if expected_value is not None and expected_value != value:
                    raise ValueError(f"métadonnée Git {field} contradictoire")
        prompt = (
            "Tu es reviewer de code Sol. Analyse uniquement l'ARTEFACT ci-dessous dans "
            "un contexte frais et en lecture seule.\n"
            "Ne consulte aucun autre verdict et ne suppose aucun résultat attendu.\n\n"
            f"STORY : {story_id}\n"
            f"CRITÈRES D'ACCEPTATION :\n{criteres.strip()}\n\n"
            f"ARTEFACT — {artefact_path} :\n{artefact}\n\n"
            "MODE DE REVUE : sol_blind\n"
            "MÉTADONNÉES GIT EXACTES (à recopier sans modification) :\n"
            f"{json.dumps(metadata, ensure_ascii=False, sort_keys=True)}\n\n"
            "Réponds STRICTEMENT avec un objet JSON valide, rien avant, rien après, "
            "conforme à ce schéma :\n"
        )
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
        prompt += json.dumps(response_schema, ensure_ascii=False, sort_keys=True)
    elif mode != "multi_vendor":
        raise ValueError(f"mode de revue inconnu : {mode!r}")
    return prompt, hashlib.sha256(prompt.encode("utf-8")).hexdigest()


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
    for requirement in ("fresh_context", "blind", "reviewer_read_only", "read_only"):
        if review.get(requirement) is not True:
            raise ValueError(f"review.{requirement} doit être true")
    if policy.get("terminal_states") != ["DONE_WITH_EVIDENCE", "BLOCKED_WITH_REASON"]:
        raise ValueError("terminal_states de politique d'autonomie invalides")
    return policy


def _sol_aliases(table: dict[str, str] | None) -> set[str] | None:
    """Retourne les alias du Sol actif, ou None si son identité n'est pas vérifiable."""
    if table is None:
        return None
    expected_provider = _normalize("GPT-5.6-Sol")
    if table.get(_normalize("sol")) != "openai" or table.get(expected_provider) != "openai":
        return None
    roles = _load_roles_yaml(REPO / "manifests" / "roles.yaml")
    active_sol = next(
        (
            member
            for member in roles
            if _normalize(str(member.get("id", ""))) == _normalize("sol")
            and str(member.get("statut", "")).strip().lower() == "actif"
        ),
        None,
    )
    if active_sol is None:
        return None
    aliases = {
        _normalize("sol"),
        _normalize("GPT-5.6-Sol"),
        _normalize(active_sol.get("id", "")),
        _normalize(active_sol.get("provider_id", "")),
        _normalize(active_sol.get("modele", "")),
    }
    aliases.discard("")
    return aliases


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
    required = (
        "base_commit", "head_commit", "head_tree", "reviewed_head_commit",
        "reviewed_head_tree", "candidate_diff_digest", "diff_digest", "prompt_sha256",
        "reviewed_at",
    )
    for field in required:
        if field not in recu:
            raise ValueError(f"métadonnée Sol absente : {field}")
    for field in ("base_commit", "head_commit", "head_tree", "reviewed_head_commit", "reviewed_head_tree"):
        _validate_object_id(recu[field], field)
    for field in ("candidate_diff_digest", "diff_digest", "prompt_sha256"):
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
    prompt_sha = _sol_prompt_sha256(review_dir)
    if recu["prompt_sha256"] != prompt_sha:
        raise ValueError("prompt_sha256 différent des octets de SOL-PROMPT.md")
    if len(verdicts) != 1 or not isinstance(verdicts[0], dict):
        raise ValueError("sol_blind exige exactement un verdict objet")
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
        covers_current = (
            base_commit == current_base
            and canonical_digest == current_digest
            and recu["candidate_diff_digest"] == current_digest
        )
        # current_head/current_tree are resolved by _etat_git_reel; retaining the explicit
        # shape checks here prevents a malformed injected state from becoming an expectation.
        if not current_head or not current_tree:
            raise ValueError("état Git courant incomplet")
    return {
        "candidate_diff_digest": canonical_digest,
        "diff_digest": canonical_digest,
        "base_commit": base_commit,
        "head_commit": head_commit,
        "head_tree": head_tree,
        "reviewed_head_commit": reviewed_head_commit,
        "reviewed_head_tree": reviewed_head_tree,
        "prompt_sha256": prompt_sha,
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
        current_base = _validate_object_id(etat_git.get("base_commit"), "base_commit courant")
        current_digest = _validate_digest(etat_git.get("diff_digest"), "diff_digest courant")
    except ValueError:
        return False
    return (
        receipt_base == current_base
        and receipt_digest == current_digest
        and candidate_digest == current_digest
    )


def tally_sol_blind(verdicts: list[dict], expected: dict, codeurs: list[str]) -> dict:
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
    if not isinstance(reviewer_model, str) or _normalize(reviewer_model) not in sol_aliases:
        return {"result": "INVALIDE", "reason": "reviewer_model n'est pas l'identité Sol"}
    if "vendor" in verdict and vendor_of(str(verdict.get("vendor", "")), table) != "openai":
        return {"result": "INVALIDE", "reason": "vendor du reviewer n'est pas Sol/openai"}

    if not isinstance(codeurs, list) or not codeurs:
        return {"result": "INVALIDE", "reason": "codeur requis pour sol_blind"}
    codeur_table = _codeur_vendor_table()
    if codeur_table is None:
        return {"result": "INVALIDE", "reason": "roster de codeurs introuvable"}
    for codeur in codeurs:
        if not isinstance(codeur, str):
            return {"result": "INVALIDE", "reason": f"codeur invalide : {codeur!r}"}
        codeur_key = _normalize(codeur)
        if codeur_key not in codeur_table:
            return {"result": "INVALIDE", "reason": f"codeur inconnu : {codeur}"}
        if codeur_key in sol_aliases:
            return {"result": "INVALIDE", "reason": "le codeur ne peut pas être Sol"}

    for field in ("fresh_context", "blind", "reviewer_read_only"):
        if verdict.get(field) is not True:
            return {"result": "INVALIDE", "reason": f"{field} doit être true"}

    if not isinstance(expected, dict):
        return {"result": "INVALIDE", "reason": "métadonnées attendues invalides"}
    expected_fields = (
        "candidate_diff_digest", "diff_digest", "base_commit", "reviewed_head_commit",
        "reviewed_head_tree", "prompt_sha256", "reviewed_at",
    )
    missing = [field for field in expected_fields if field not in expected]
    if missing:
        return {"result": "INVALIDE", "reason": f"métadonnées attendues absentes : {missing[0]}"}
    try:
        for field in ("base_commit", "reviewed_head_commit", "reviewed_head_tree"):
            _validate_object_id(expected[field], field)
        for field in ("candidate_diff_digest", "diff_digest", "prompt_sha256"):
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
        _validate_digest(verdict.get("prompt_sha256"), "prompt_sha256 verdict")
    except ValueError as error:
        return {"result": "INVALIDE", "reason": str(error)}
    for field in ("base_commit", "reviewed_head_commit", "reviewed_head_tree", "prompt_sha256"):
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
    fenetre_heures_defaut: int = 24,
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
) -> dict:
    required = (
        "schema", "mode", "dossier", "issue", "round", "base_commit", "head_commit",
        "head_tree", "diff_digest", "candidate_diff_digest", "reviewed_head_commit",
        "reviewed_head_tree", "prompt_sha256", "reviewers_attendus", "codeur", "resultat",
        "reviewed_at", "verdict", "reviewer_model", "date_heure",
        "fenetre_heures",
    )
    if not isinstance(recu, dict):
        return {"result": "INVALIDE", "reason": "données absentes : reçu"}
    for key in required:
        if key not in recu:
            return {"result": "INVALIDE", "reason": f"données absentes : {key}"}
    if recu.get("mode") != "sol_blind":
        return {"result": "INVALIDE", "reason": "mode de reçu inconnu"}
    if not isinstance(etat_git, dict):
        return {"result": "INVALIDE", "reason": "état Git courant invalide"}
    try:
        current_base = _validate_object_id(etat_git.get("base_commit"), "base_commit courant")
        current_digest = _validate_digest(etat_git.get("diff_digest"), "diff_digest courant")
    except ValueError as error:
        return {"result": "INVALIDE", "reason": str(error)}
    if recu["base_commit"] != current_base:
        return {"result": "INVALIDE", "reason": "reçu lié à un autre commit"}
    if recu["diff_digest"] != current_digest:
        return {"result": "INVALIDE", "reason": "diff modifié après revue"}
    if recu["candidate_diff_digest"] != current_digest:
        return {"result": "INVALIDE", "reason": "candidate_diff_digest différent du diff courant"}
    if review_dir is None:
        return {"result": "INVALIDE", "reason": f"{_SOL_PROMPT_FILENAME} requis pour sol_blind"}
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
    if recu["resultat"] != tally_result["result"]:
        return {"result": "INVALIDE", "reason": "réponse contradictoire"}
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


def _validate_sol_archive_receipt(recu: object, execute: GitRunner) -> None:
    """Validate exact Sol archive object IDs and the trees they name."""
    if not isinstance(recu, dict):
        raise ValueError("reçu Sol archive invalide")
    for field in (
        "base_commit", "head_commit", "head_tree", "reviewed_head_commit",
        "reviewed_head_tree",
    ):
        _validate_object_id(recu.get(field), field)
    for field in ("base_commit", "head_commit", "reviewed_head_commit"):
        _resolve_commit(execute, recu[field])
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
    fenetre_heures_defaut: int = 24,
    review_dir: Path | None = None,
    runner: GitRunner | None = None,
) -> dict:
    """Dispatch le mode explicite; les reçus sans mode restent multi-vendor."""
    if isinstance(recu, dict):
        mode = recu.get("mode", "multi_vendor")
        if mode == "sol_blind":
            return _verifier_recu_sol_blind(
                recu, verdicts, etat_git, review_dir=review_dir, runner=runner
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
    if mode == "sol_blind":
        base_ref = getattr(args, "base_ref", None)
        if not base_ref:
            raise ValueError("--base-ref est obligatoire avec --mode sol_blind")
        if not args.out or Path(args.out).name != _SOL_PROMPT_FILENAME:
            raise ValueError(f"--out doit désigner {_SOL_PROMPT_FILENAME} en mode sol_blind")
        head_ref = getattr(args, "head_ref", "HEAD")
    else:
        base_ref = None
        head_ref = None
    prompt, sha = build_prompt(
        args.story,
        criteres,
        args.artefact,
        artefact,
        mode=mode,
        base_ref=base_ref,
        head_ref=head_ref,
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
        try:
            prompt_sha = _sol_prompt_sha256(dossier)
        except (OSError, ValueError) as error:
            prompt_sha = None
            result = {"result": "INVALIDE", "reason": str(error)}
        if len(verdicts) != 1:
            result = {"result": "INVALIDE", "reason": "sol_blind exige exactement 1 verdict"}
        elif prompt_sha is not None:
            expected = {
                **etat,
                "candidate_diff_digest": etat["diff_digest"],
                "reviewed_head_commit": etat["head_commit"],
                "reviewed_head_tree": etat["head_tree"],
                "prompt_sha256": prompt_sha,
                "reviewed_at": verdicts[0].get("reviewed_at"),
            }
            result = tally_sol_blind(verdicts, expected=expected, codeurs=args.codeur)
        reviewer = verdicts[0] if len(verdicts) == 1 else {}
        recu = {
            "schema": "recu-revue/2",
            "mode": "sol_blind",
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
