#!/usr/bin/env python3
"""Valide l'inventaire et le rendu de la hiérarchie d'autorité."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
ID_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{2,63}$")
STATUSES = {"active", "conflicted", "superseded", "archived", "draft"}
KINDS = {
    "doctrine",
    "spec",
    "adr",
    "decision",
    "ide_rules",
    "manifest",
    "data",
    "ledger",
    "story",
    "generated",
}
RETENTIONS = {"in_force", "historical_record", "pending_cleanup"}
VERSION_SOURCES = {"declared_in_file", "assigned_by_inventory"}
DIGEST_POLICIES = {"content_sha256", "section_sha256", "delegated", "none"}

REQUIRED_SOURCE_FIELDS = {
    "id",
    "title",
    "path",
    "anchor",
    "kind",
    "scope",
    "version",
    "version_source",
    "status",
    "owner",
    "superseded_by",
    "prevails_over",
    "positions",
    "digest",
    "retention",
    "cleanup_issue",
    "resolution_issue",
    "decision",
    "notes",
}


def _load_marker_re() -> re.Pattern[str]:
    path = REPO_ROOT / "scripts" / "no_stub_scan.py"
    spec = importlib.util.spec_from_file_location("_authority_no_stub_scan", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"chargement impossible: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.MARKER_RE


MARKER_RE = _load_marker_re()


def _error(errors: list[str], message: str) -> None:
    errors.append(f"• {message}")


def _section_bytes(path: Path, anchor: str) -> bytes:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    lines = text.splitlines(keepends=True)
    heading_index: int | None = None
    level: int | None = None

    for index, line in enumerate(lines):
        match = re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", line.rstrip("\n"))
        if match and match.group(2) == anchor:
            heading_index = index
            level = len(match.group(1))
            break

    if heading_index is None or level is None:
        raise ValueError(f"section ancrée absente: {anchor!r}")

    end = len(lines)
    next_heading = re.compile(rf"^#{{1,{level}}}\s")
    for index in range(heading_index + 1, len(lines)):
        if next_heading.match(lines[index]):
            end = index
            break

    return "".join(lines[heading_index:end]).encode("utf-8")


def digest_of(path: Path, policy: str, anchor: str | None) -> str:
    """Calcule une empreinte de contenu ou d'une section Markdown."""
    if policy == "content_sha256":
        material = path.read_bytes().replace(b"\r\n", b"\n")
    elif policy == "section_sha256":
        if not isinstance(anchor, str) or not anchor:
            raise ValueError("ancre requise pour une empreinte de section")
        material = _section_bytes(path, anchor)
    else:
        raise ValueError(f"politique d'empreinte non calculable: {policy}")
    return hashlib.sha256(material).hexdigest()


def cycles(aretes: dict[str, list[str]]) -> list[list[str]]:
    """Retourne les cycles d'un graphe orienté via DFS itératif."""
    nodes = set(aretes)
    for destinations in aretes.values():
        nodes.update(destinations)

    colors = {node: 0 for node in nodes}
    found: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()

    for root in sorted(nodes):
        if colors[root] != 0:
            continue
        colors[root] = 1
        stack: list[tuple[str, int]] = [(root, 0)]
        trail = [root]

        while stack:
            node, index = stack[-1]
            destinations = aretes.get(node, [])
            if index >= len(destinations):
                colors[node] = 2
                stack.pop()
                trail.pop()
                continue

            child = destinations[index]
            stack[-1] = (node, index + 1)
            color = colors.get(child, 0)
            if color == 0:
                colors[child] = 1
                stack.append((child, 0))
                trail.append(child)
            elif color == 1:
                start = trail.index(child)
                cycle = trail[start:] + [child]
                key = tuple(cycle)
                if key not in seen:
                    seen.add(key)
                    found.append(cycle)

    return found


def _load_jsonl_sequences(path: Path) -> set[int]:
    if not path.is_file():
        return set()
    sequences: set[int] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        seq = entry.get("seq") if isinstance(entry, dict) else None
        if isinstance(seq, int) and not isinstance(seq, bool):
            sequences.add(seq)
    return sequences


def _conflict_identity(conflict: dict[str, Any]) -> tuple[Any, ...]:
    return (
        conflict.get("kind"),
        conflict.get("sujet"),
        tuple(sorted(conflict.get("sources", []))),
        tuple(sorted(conflict.get("positions", []))),
    )


def _real_conflicts(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_topic: dict[str, dict[str, list[str]]] = {}
    for source in sources:
        if source.get("status") not in {"active", "conflicted"}:
            continue
        source_id = source.get("id")
        if not isinstance(source_id, str):
            continue
        for position in source.get("positions", []):
            if not isinstance(position, dict):
                continue
            topic = position.get("topic")
            value = position.get("position")
            if not isinstance(topic, str) or not isinstance(value, str):
                continue
            by_topic.setdefault(topic, {}).setdefault(value, []).append(source_id)

    result: list[dict[str, Any]] = []
    for topic, positions in sorted(by_topic.items()):
        if len(positions) < 2:
            continue
        selected_sources = sorted(
            min(sorted(source_ids))
            for source_ids in positions.values()
            if source_ids
        )
        selected_positions = sorted(positions)
        if len(selected_sources) >= 2:
            result.append(
                {
                    "kind": "topic_position",
                    "sujet": topic,
                    "sources": selected_sources,
                    "positions": selected_positions,
                }
            )
    return result


def render(authority: dict) -> str:
    """Produit le rendu Markdown stable de l'inventaire canonique."""
    owners = authority.get("owners", {})
    scopes = authority.get("scopes", {})
    sources = authority.get("sources", [])

    lines = [
        "<!-- NE PAS ÉDITER À LA MAIN — généré par scripts/governance/validate_authority.py --render -->",
        "",
        "# Hiérarchie d'autorité",
        "",
        "Cette carte est le rendu de `governance/authority.json`.",
        "",
        "## Propriétaires",
        "",
        "| Identifiant | Rôle |",
        "|---|---|",
    ]
    for owner_id in sorted(owners):
        role = owners[owner_id].get("role", "") if isinstance(owners[owner_id], dict) else ""
        lines.append(f"| `{owner_id}` | {role} |")

    lines.extend(["", "## Portées", "", "| Portée | Singleton |", "|---|---|"])
    for scope_id in sorted(scopes):
        singleton = scopes[scope_id].get("singleton", False)
        lines.append(f"| `{scope_id}` | {'oui' if singleton else 'non'} |")

    lines.extend(
        [
            "",
            "## Sources",
            "",
            "| Id | Source | Statut | Portée | Propriétaire | Successeur |",
            "|---|---|---|---|---|---|",
        ]
    )
    for source in sorted(sources, key=lambda item: item.get("id", "")):
        path = source.get("path")
        anchor = source.get("anchor")
        location = f"`{path}`" if path else "décision sans fichier"
        if anchor:
            location += f" — {anchor}"
        successor = source.get("superseded_by") or "—"
        lines.append(
            "| `{id}` | {location} | {status} | `{scope}` | `{owner}` | `{successor}` |".format(
                id=source.get("id", ""),
                location=location,
                status=source.get("status", ""),
                scope=source.get("scope", ""),
                owner=source.get("owner", ""),
                successor=successor,
            )
        )

    lines.extend(["", "## Précédences déclarées", ""])
    precedence_found = False
    for source in sorted(sources, key=lambda item: item.get("id", "")):
        targets = source.get("prevails_over", [])
        if targets:
            precedence_found = True
            lines.append(f"- `{source.get('id')}` prévaut sur " + ", ".join(f"`{x}`" for x in targets))
    if not precedence_found:
        lines.append("- Aucune précédence déclarée.")

    lines.extend(["", "## Positions déclarées", ""])
    position_found = False
    for source in sorted(sources, key=lambda item: item.get("id", "")):
        for position in source.get("positions", []):
            if not isinstance(position, dict):
                continue
            position_found = True
            lines.append(
                f"- `{source.get('id')}` : `{position.get('topic')}` = "
                f"`{position.get('position')}` ({position.get('locator')})"
            )
    if not position_found:
        lines.append("- Aucune position déclarée.")

    return "\n".join(lines) + "\n"


def check(
    authority: dict,
    baseline: dict,
    repo_root: Path,
    map_text: str,
) -> tuple[bool, list[str]]:
    """Contrôle l'inventaire, les empreintes, les graphes et le rendu."""
    errors: list[str] = []
    sources_raw = authority.get("sources")
    sources: list[dict[str, Any]] = (
        sources_raw if isinstance(sources_raw, list) else []
    )
    if not isinstance(sources_raw, list):
        _error(errors, "sources doit être une liste")

    owners = authority.get("owners")
    owners = owners if isinstance(owners, dict) else {}
    scopes = authority.get("scopes")
    scopes = scopes if isinstance(scopes, dict) else {}
    topics = authority.get("topics")
    topics = topics if isinstance(topics, dict) else {}

    ids: list[str] = []
    by_id: dict[str, dict[str, Any]] = {}
    verified_digests = 0

    for index, source in enumerate(sources, start=1):
        if not isinstance(source, dict):
            _error(errors, f"source au rang {index} invalide: dictionnaire requis")
            continue

        missing = sorted(REQUIRED_SOURCE_FIELDS - set(source))
        if missing:
            _error(errors, f"source au rang {index}: champs requis absents: {', '.join(missing)}")

        source_id = source.get("id")
        if not isinstance(source_id, str) or not ID_RE.fullmatch(source_id):
            _error(errors, f"id invalide au rang {index}: {source_id!r}")
        else:
            if source_id in by_id:
                _error(errors, f"id dupliqué: {source_id}")
            else:
                by_id[source_id] = source
            ids.append(source_id)

        for field, allowed in (
            ("status", STATUSES),
            ("kind", KINDS),
            ("retention", RETENTIONS),
            ("version_source", VERSION_SOURCES),
        ):
            if source.get(field) not in allowed:
                _error(errors, f"{source_id or index}: {field} invalide: {source.get(field)!r}")

        scope = source.get("scope")
        if scope not in scopes:
            _error(errors, f"{source_id or index}: portée inconnue: {scope!r}")

        owner = source.get("owner")
        if owner not in owners:
            _error(errors, f"{source_id or index}: propriétaire hors owners: {owner!r}")

        if not isinstance(source.get("title"), str) or not source.get("title").strip():
            _error(errors, f"{source_id or index}: titre vide ou invalide")
        if not isinstance(source.get("version"), str) or not source.get("version").strip():
            if source.get("status") in {"active", "conflicted"}:
                _error(errors, f"{source_id or index}: version absente sur source active ou conflictuelle")

        positions = source.get("positions")
        if not isinstance(positions, list):
            _error(errors, f"{source_id or index}: positions doit être une liste")
        else:
            for position_index, position in enumerate(positions, start=1):
                if not isinstance(position, dict):
                    _error(errors, f"{source_id or index}: position {position_index} invalide")
                    continue
                topic = position.get("topic")
                value = position.get("position")
                locator = position.get("locator")
                vocabulary = topics.get(topic, {}).get("vocabulaire") if isinstance(topics.get(topic), dict) else None
                if not isinstance(vocabulary, list) or value not in vocabulary:
                    _error(
                        errors,
                        f"{source_id or index}: position hors vocabulaire pour {topic!r}: {value!r}",
                    )
                if not isinstance(locator, str) or not re.fullmatch(r"[^:]+:\d+(?:-\d+)?", locator):
                    _error(errors, f"{source_id or index}: locator invalide: {locator!r}")

        digest = source.get("digest")
        if not isinstance(digest, dict):
            _error(errors, f"{source_id or index}: digest invalide")
            digest = {}
        policy = digest.get("policy")
        value = digest.get("value")
        delegated_to = digest.get("delegated_to")
        if policy not in DIGEST_POLICIES:
            _error(errors, f"{source_id or index}: politique d'empreinte invalide: {policy!r}")
        if policy == "delegated" and (not isinstance(delegated_to, str) or not delegated_to.strip()):
            _error(errors, f"{source_id or index}: digest délégué exige delegated_to")
        if policy == "none" and source.get("path") is not None:
            _error(errors, f"{source_id or index}: digest none exige path null")
        if policy in {"content_sha256", "section_sha256"}:
            if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
                _error(errors, f"{source_id or index}: valeur d'empreinte absente ou invalide")
        elif value is not None:
            _error(errors, f"{source_id or index}: valeur d'empreinte doit être null pour {policy!r}")

        if source.get("status") in {"active", "conflicted"}:
            if not isinstance(owner, str) or not owner:
                _error(errors, f"{source_id or index}: propriétaire requis")
            if not isinstance(digest, dict) or policy not in DIGEST_POLICIES:
                _error(errors, f"{source_id or index}: digest requis")

        if source.get("retention") == "pending_cleanup" and source.get("cleanup_issue") is None:
            _error(errors, f"{source_id or index}: pending_cleanup exige cleanup_issue")
        if source.get("status") == "conflicted" and source.get("resolution_issue") is None:
            _error(errors, f"{source_id or index}: source conflictuelle exige resolution_issue")

        for text_field in ("title", "notes"):
            text = source.get(text_field)
            if isinstance(text, str) and MARKER_RE.search(text):
                _error(errors, f"{source_id or index}: marqueur interdit dans {text_field}")

    for source_id, source in by_id.items():
        successor = source.get("superseded_by")
        if successor is not None:
            if successor not in by_id:
                _error(errors, f"{source_id}: successeur inconnu: {successor!r}")
            elif successor == source_id:
                _error(errors, f"{source_id}: une source ne peut pas être son propre successeur")

        targets = source.get("prevails_over")
        if not isinstance(targets, list) or not all(isinstance(target, str) for target in targets):
            _error(errors, f"{source_id}: prevails_over doit être une liste de chaînes")
        elif successor is not None and successor in targets:
            _error(errors, f"{source_id}: arête croisée succession/précédence vers {successor}")

        digest = source.get("digest")
        if not isinstance(digest, dict):
            continue
        policy = digest.get("policy")
        path_value = source.get("path")
        if policy in {"content_sha256", "section_sha256"} and path_value is not None:
            if not isinstance(path_value, str):
                _error(errors, f"{source_id}: path invalide")
                continue
            file_path = repo_root / path_value
            if not file_path.is_file():
                _error(errors, f"fichier d'empreinte absent: {path_value}")
                continue
            try:
                computed = digest_of(file_path, policy, source.get("anchor"))
            except (OSError, UnicodeDecodeError, ValueError) as exc:
                _error(errors, f"empreinte impossible: {path_value}: {exc}")
                continue
            stored = digest.get("value")
            if stored != computed:
                stored_short = stored[:8] if isinstance(stored, str) else "absente"
                _error(
                    errors,
                    f"empreinte périmée: {path_value} — stockée {stored_short}…, recalculée {computed[:8]}…",
                )
            else:
                verified_digests += 1

    successor_edges = {
        source_id: [source["superseded_by"]]
        for source_id, source in by_id.items()
        if isinstance(source.get("superseded_by"), str) and source["superseded_by"] in by_id
    }
    precedence_edges = {
        source_id: [target for target in source.get("prevails_over", []) if target in by_id]
        for source_id, source in by_id.items()
        if isinstance(source.get("prevails_over"), list)
    }
    for cycle in cycles(successor_edges):
        _error(errors, "cycle de succession : " + " → ".join(cycle))
    for cycle in cycles(precedence_edges):
        _error(errors, "cycle de précédence : " + " → ".join(cycle))

    for source_id, source in by_id.items():
        current = source
        visited: set[str] = set()
        while isinstance(current.get("superseded_by"), str):
            successor = current["superseded_by"]
            if successor in visited or successor not in by_id:
                break
            visited.add(successor)
            current = by_id[successor]
        if visited and current.get("status") == "archived":
            _error(errors, f"{source_id}: succession aboutit sur une source archivée: {current.get('id')}")

    for scope_id, scope_data in scopes.items():
        if not isinstance(scope_data, dict) or not scope_data.get("singleton"):
            continue
        occupants = [
            source_id
            for source_id, source in by_id.items()
            if source.get("scope") == scope_id
            and source.get("status") in {"active", "conflicted"}
        ]
        if len(occupants) > 1:
            _error(errors, f"portée singleton violée: {scope_id} ({', '.join(sorted(occupants))})")

    baseline_conflicts = baseline.get("conflits") if isinstance(baseline, dict) else None
    if not isinstance(baseline_conflicts, list):
        _error(errors, "baseline: conflits doit être une liste")
        baseline_conflicts = []
    actual = {_conflict_identity(conflict) for conflict in _real_conflicts(list(by_id.values()))}
    expected = {_conflict_identity(conflict) for conflict in baseline_conflicts if isinstance(conflict, dict)}
    for identity in sorted(actual - expected, key=repr):
        _error(errors, f"conflit nouveau non baseliné: {identity!r}")
    for identity in sorted(expected - actual, key=repr):
        _error(errors, f"conflit baseliné périmé: {identity!r}")

    vision_path_value = authority.get("vision_log", "governance/vision-log.jsonl")
    vision_path = repo_root / vision_path_value if isinstance(vision_path_value, str) else repo_root / "governance/vision-log.jsonl"
    vision_sequences = _load_jsonl_sequences(vision_path)
    mission_sequences = _load_jsonl_sequences(repo_root / "Registres" / "mission.jsonl")
    for source_id, source in by_id.items():
        decision = source.get("decision")
        if not isinstance(decision, dict):
            _error(errors, f"{source_id}: decision invalide")
            continue
        vision_seq = decision.get("vision_log_seq")
        mission_seq = decision.get("mission_seq")
        if source.get("status") != "active" and vision_seq is None:
            _error(errors, f"{source_id}: journal de vision requis pour statut non actif")
        if vision_seq is not None and vision_seq not in vision_sequences:
            _error(errors, f"{source_id}: vision_log_seq inexistant: {vision_seq!r}")
        if mission_seq is not None and mission_seq not in mission_sequences:
            _error(errors, f"{source_id}: mission_seq inexistant: {mission_seq!r}")

    expected_map = render(authority)
    if map_text != expected_map:
        _error(errors, "carte d'autorité désynchronisée")

    return not errors, errors


def _load_json(path: Path) -> dict:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{path}: objet JSON attendu")
    return loaded


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authority", type=Path, default=Path("governance/authority.json"))
    parser.add_argument("--baseline", type=Path, default=Path("governance/conflicts-baseline.json"))
    parser.add_argument("--map", dest="map_path", type=Path, default=Path("governance/AUTHORITY-MAP.md"))
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--render", action="store_true")
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    authority_path = args.authority if args.authority.is_absolute() else repo_root / args.authority
    baseline_path = args.baseline if args.baseline.is_absolute() else repo_root / args.baseline
    map_path = args.map_path if args.map_path.is_absolute() else repo_root / args.map_path

    try:
        authority = _load_json(authority_path)
        baseline = _load_json(baseline_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"FAIL — validate_authority: {exc}")
        return 1

    if args.render:
        map_path.parent.mkdir(parents=True, exist_ok=True)
        map_path.write_text(render(authority), encoding="utf-8")

    try:
        map_text = map_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"FAIL — validate_authority: carte inaccessible: {exc}")
        return 1

    ok, errors = check(authority, baseline, repo_root, map_text)
    if not ok:
        print("FAIL — validate_authority: erreurs détectées:")
        for error in errors:
            print(f"  {error}")
        return 1

    sources = authority.get("sources", [])
    active = sum(source.get("status") == "active" for source in sources if isinstance(source, dict))
    conflicted = sum(source.get("status") == "conflicted" for source in sources if isinstance(source, dict))
    superseded = sum(source.get("status") == "superseded" for source in sources if isinstance(source, dict))
    conflicts = baseline.get("conflits", [])
    verified = sum(
        isinstance(source, dict)
        and isinstance(source.get("digest"), dict)
        and source["digest"].get("policy") in {"content_sha256", "section_sha256"}
        for source in sources
    )
    print(
        "PASS — validate_authority: "
        f"{len(sources)} sources ({active} actives, {conflicted} conflictuelles, "
        f"{superseded} superseded), 0 cycle, {len(conflicts)} conflits baselinés, "
        f"{verified} empreintes vérifiées."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
