import argparse
import fnmatch
import hashlib
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path


_MANIFEST_JSON = Path("governance") / "path-classification.json"
_MANIFEST_MARKDOWN = Path("governance") / "PATH-CLASSIFICATION.md"
_DEFAULT_RULES = Path("governance") / "path-classification-rules.json"


def detect_collisions(paths: list[str], targets: dict[str, str] | None = None) -> dict:
    result = {"case": [], "unicode": [], "portability": []}
    target_values = list(targets.values()) if targets is not None else []

    all_values: list[str] = []
    for value in list(paths) + target_values:
        if value not in all_values:
            all_values.append(value)

    case_edges: set[tuple[str, str]] = set()
    unicode_edges: set[tuple[str, str]] = set()

    def add_pair(left: str, right: str) -> None:
        if left == right:
            return

        left_fold = left.casefold()
        right_fold = right.casefold()
        left_nfd_fold = unicodedata.normalize("NFD", left).casefold()
        right_nfd_fold = unicodedata.normalize("NFD", right).casefold()
        pair = tuple(sorted((left, right)))

        if left_fold == right_fold:
            case_edges.add(pair)
        elif left_nfd_fold == right_nfd_fold:
            unicode_edges.add(pair)

    def compare_within(values: list[str]) -> None:
        for index, left in enumerate(values):
            for right in values[index + 1:]:
                add_pair(left, right)

    compare_within(paths)
    compare_within(target_values)

    if targets is not None:
        for target in target_values:
            own_sources = {
                source for source, destination in targets.items() if destination == target
            }
            for path in paths:
                if path not in own_sources:
                    add_pair(target, path)

    def groups_from_edges(edges: set[tuple[str, str]]) -> list[list[str]]:
        adjacency: dict[str, set[str]] = {}
        for left, right in edges:
            adjacency.setdefault(left, set()).add(right)
            adjacency.setdefault(right, set()).add(left)

        groups: list[list[str]] = []
        visited: set[str] = set()
        for value in all_values:
            if value in visited or value not in adjacency:
                continue

            component: set[str] = set()
            pending = [value]
            visited.add(value)
            while pending:
                current = pending.pop()
                component.add(current)
                for neighbor in adjacency[current]:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        pending.append(neighbor)

            groups.append([item for item in all_values if item in component])
        return groups

    for group in groups_from_edges(case_edges):
        result["case"].append(
            {
                "paths": group,
                "description": "Chemins distincts entrant en collision après comparaison insensible à la casse.",
            }
        )

    if targets is not None:
        sources_by_target: dict[str, list[str]] = {}
        for source, target in targets.items():
            sources_by_target.setdefault(target, []).append(source)
        for target, sources in sources_by_target.items():
            if len(sources) > 1:
                result["case"].append(
                    {
                        "paths": sorted(sources),
                        "description": (
                            f"Cible ambiguë : {len(sources)} sources distinctes "
                            f"migrent vers le même emplacement : {target}."
                        ),
                    }
                )

    for group in groups_from_edges(unicode_edges):
        result["unicode"].append(
            {
                "paths": group,
                "description": "Chemins distincts entrant en collision après normalisation Unicode NFD et comparaison insensible à la casse.",
            }
        )

    colliding_values: set[str] = set()
    for left, right in case_edges | unicode_edges:
        colliding_values.add(left)
        colliding_values.add(right)

    for value in all_values:
        if (
            unicodedata.normalize("NFC", value) != value
            and value not in colliding_values
        ):
            result["unicode"].append(
                {
                    "kind": "non_nfc",
                    "paths": [value],
                    "description": "Anomalie de normalisation Unicode : le chemin n'est pas en forme NFC.",
                }
            )

    for value in all_values:
        dangerous = [
            character
            for character in value
            if unicodedata.category(character) in {"Cc", "Cf", "Cs", "Co", "Cn"}
            or (
                unicodedata.category(character) == "Zs"
                and character != " "
            )
        ]
        if dangerous:
            result["portability"].append(
                {
                    "paths": [value],
                    "description": "Le chemin contient des caractères invisibles ou dangereux pour la portabilité.",
                }
            )

    return result


def check_portability(path: str) -> list[dict]:
    violations: list[dict] = []
    forbidden_characters = set('<>:"|?*')
    reserved_names = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "COM1",
        "COM2",
        "COM3",
        "COM4",
        "COM5",
        "COM6",
        "COM7",
        "COM8",
        "COM9",
        "LPT1",
        "LPT2",
        "LPT3",
        "LPT4",
        "LPT5",
        "LPT6",
        "LPT7",
        "LPT8",
        "LPT9",
    }

    for segment in path.split("/"):
        if any(
            character in forbidden_characters or ord(character) <= 31
            for character in segment
        ):
            detail = "Le segment contient un caractère interdit par Windows."
            violations.append(
                {
                    "rule": "windows_forbidden_character",
                    "segment": segment,
                    "detail": detail,
                }
            )

        base_name = segment.split(".", 1)[0].upper()
        if base_name in reserved_names:
            violations.append(
                {
                    "rule": "windows_reserved_name",
                    "segment": segment,
                    "detail": "Le segment correspond à un nom réservé par Windows.",
                }
            )

        if segment.endswith(".") or segment.endswith(" "):
            detail = "Un segment Windows ne peut pas se terminer par un point ou un espace."
            violations.append(
                {
                    "rule": "windows_trailing_dot_or_space",
                    "segment": segment,
                    "detail": detail,
                }
            )

        if segment == "" or segment == "." or segment == "..":
            violations.append(
                {
                    "rule": "illegal_segment",
                    "segment": segment,
                    "detail": "Le segment est vide, réservé ou ne constitue pas un nom de répertoire valide.",
                }
            )
        elif segment == ".git":
            violations.append(
                {
                    "rule": "reserved_git_segment",
                    "segment": segment,
                    "detail": "Le segment .git est réservé.",
                }
            )

        if len(segment.encode("utf-8")) > 255:
            violations.append(
                {
                    "rule": "segment_too_long",
                    "segment": segment,
                    "detail": "Le segment dépasse la limite de 255 octets en UTF-8.",
                }
            )

        if any(
            unicodedata.category(character) in {"Cc", "Cf", "Cs", "Co", "Cn"}
            or (
                unicodedata.category(character) == "Zs"
                and character != " "
            )
            for character in segment
        ):
            violations.append(
                {
                    "rule": "invisible_character",
                    "segment": segment,
                    "detail": "Le segment contient un caractère invisible ou dangereux.",
                }
            )

    path_length = len(path)
    if path_length > 240:
        detail = "Le chemin relatif dépasse la longueur maximale portable de 240 caractères."
        violations.append(
            {
                "rule": "path_length",
                "segment": path,
                "detail": detail,
                "severity": "error",
            }
        )
    elif 200 <= path_length < 240:
        detail = "Le chemin relatif approche la limite de longueur portable."
        violations.append(
            {
                "rule": "path_length",
                "segment": path,
                "detail": detail,
                "severity": "warning",
            }
        )

    return violations


def load_rules(rules_path: Path) -> dict:
    rules = json.loads(rules_path.read_text(encoding="utf-8"))
    rule_ids: set[str] = set()
    owners = rules["owners"]
    classes = rules["classes"]

    for rule in rules["rules"]:
        rule_id = rule["id"]
        if rule_id in rule_ids:
            raise ValueError(f"id de règle dupliqué : {rule_id}")
        rule_ids.add(rule_id)

        owner = rule["owner"]
        if owner not in owners:
            raise ValueError(
                f"règle {rule_id} : owner manquant dans owners : {owner}"
            )

        rule_class = rule["class"]
        if rule_class not in classes:
            raise ValueError(
                f"règle {rule_id} : classe invalide : {rule_class}"
            )

        rationale = rule["rationale"]
        if not isinstance(rationale, str) or not rationale.strip():
            raise ValueError(f"règle {rule_id} : rationale vide ou invalide")

    return rules


def classify(path: str, rules: dict) -> dict:
    selected_rule: dict | None = None

    for rule in rules["rules"]:
        match = rule["match"]
        kind = match["kind"]
        value = match["value"]

        if (
            (kind == "prefix" and path.startswith(value))
            or (kind == "exact" and path == value)
            or (kind == "suffix" and path.endswith(value))
            or (kind == "glob" and fnmatch.fnmatchcase(path, value))
        ):
            selected_rule = rule
            break

    if selected_rule is None:
        raise ValueError(f"chemin non classé : {path}")

    if selected_rule.get("target") is None:
        target_path = None
    elif selected_rule["target_kind"] == "reroot":
        target_path = selected_rule["target"] + path[
            len(selected_rule["match"]["value"]):
        ]
    elif selected_rule["target_kind"] == "keep":
        target_path = path
    elif selected_rule["target_kind"] == "explicit":
        target_path = selected_rule["target"]

    return {
        "rule_id": selected_rule["id"],
        "class": selected_rule["class"],
        "generated": selected_rule["generated"],
        "owner": selected_rule["owner"],
        "target_path": target_path,
    }


def tracked_files(repo_root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(repo_root), "ls-files", "-z"],
        capture_output=True,
        check=True,
        text=False,
    )
    raw = result.stdout.decode("utf-8")
    return sorted(path for path in raw.split("\0") if path)


def _within_repo(repo_root: Path, path: Path) -> Path:
    root = repo_root.resolve()
    candidate = path.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise ValueError(f"chemin hors du dépôt : {path}") from error
    return candidate


def build_reference_graph(repo_root: Path, tracked: list[str]) -> dict:
    graph = {"edges": [], "dangling": []}
    tracked_set = set(tracked)
    structured_referrers = {
        "governance/authority.json",
        "reviews/BINDING.txt",
        "evidence/reviews/BINDING.txt",
        "sonar-project.properties",
    }

    if "governance/authority.json" in tracked_set:
        try:
            authority_path = _within_repo(
                repo_root, repo_root / "governance/authority.json"
            )
            authority = json.loads(authority_path.read_text(encoding="utf-8"))
            sources = authority.get("sources", [])
            if not isinstance(sources, list):
                sources = []
            for source in sources:
                if not isinstance(source, dict):
                    continue
                candidate = source.get("path")
                if isinstance(candidate, str) and candidate and candidate in tracked_set:
                    graph["edges"].append(
                        {
                            "referrer": "governance/authority.json",
                            "line": 0,
                            "candidate": candidate,
                            "resolved": candidate,
                            "severity": "hard",
                        }
                    )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
            pass

    # RC1-010 (#440) lot 5a : BINDING.txt et les dossiers qu'il référence vivent, pendant la
    # migration reviews/ -> evidence/reviews/ (lots 5b-5d), à cheval sur les DEUX racines —
    # certaines entrées déjà déplacées, d'autres pas encore. binding_referrer détecte où
    # BINDING.txt lui-même se trouve (il migre au lot 5d) ; chaque candidat est résolu contre
    # les DEUX racines possibles, dans cet ordre (evidence/reviews/ d'abord, reviews/ en repli).
    binding_referrer = (
        "evidence/reviews/BINDING.txt"
        if "evidence/reviews/BINDING.txt" in tracked_set
        else "reviews/BINDING.txt" if "reviews/BINDING.txt" in tracked_set else None
    )
    if binding_referrer is not None:
        try:
            binding_path = _within_repo(repo_root, repo_root / binding_referrer)
            for line_number, line in enumerate(
                binding_path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                candidate = line.strip()
                if not candidate or candidate.startswith("#"):
                    continue
                resolved = None
                for prefix in ("evidence/reviews/", "reviews/"):
                    essai = f"{prefix}{candidate}"
                    if any(
                        path == essai or path.startswith(essai + "/")
                        for path in tracked
                    ):
                        resolved = essai
                        break
                if resolved is not None:
                    graph["edges"].append(
                        {
                            "referrer": binding_referrer,
                            "line": line_number,
                            "candidate": candidate,
                            "resolved": resolved,
                            "severity": "hard",
                        }
                    )
                else:
                    graph["dangling"].append(
                        {
                            "referrer": binding_referrer,
                            "line": line_number,
                            "candidate": candidate,
                        }
                    )
        except (OSError, UnicodeDecodeError, ValueError):
            pass

    if "sonar-project.properties" in tracked_set:
        try:
            sonar_path = _within_repo(
                repo_root, repo_root / "sonar-project.properties"
            )
            for line_number, line in enumerate(
                sonar_path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if "resourceKey=" not in line:
                    continue
                candidate = line.split("resourceKey=", 1)[1].strip()
                if candidate in tracked_set:
                    graph["edges"].append(
                        {
                            "referrer": "sonar-project.properties",
                            "line": line_number,
                            "candidate": candidate,
                            "resolved": candidate,
                            "severity": "silent",
                        }
                    )
        except (OSError, UnicodeDecodeError, ValueError):
            pass

    allowed_extensions = {
        ".py",
        ".yml",
        ".yaml",
        ".toml",
        ".md",
        ".mdc",
        ".json",
        ".txt",
        ".cfg",
        ".properties",
    }
    known_path_extensions = {".py", ".md", ".json", ".yml", ".yaml"}
    candidate_pattern = re.compile(r"[A-Za-z0-9_.][A-Za-z0-9._/-]*")
    excluded_generic_referrers = structured_referrers | {
        _MANIFEST_JSON.as_posix(),
        _MANIFEST_MARKDOWN.as_posix(),
    }

    for referrer in tracked:
        path_name = Path(referrer)
        if referrer in excluded_generic_referrers:
            continue
        if (
            path_name.suffix not in allowed_extensions
            and path_name.name != ".gitignore"
        ):
            continue

        try:
            content = _within_repo(repo_root, repo_root / referrer).read_text(
                encoding="utf-8"
            )
        except UnicodeDecodeError:
            continue

        for line_number, line in enumerate(content.splitlines(), start=1):
            url_ranges: list[tuple[int, int]] = []
            for marker in ("http://", "https://"):
                start = 0
                while True:
                    marker_index = line.find(marker, start)
                    if marker_index == -1:
                        break
                    url_start = marker_index + len(marker)
                    url_end = url_start
                    while url_end < len(line) and not line[url_end].isspace():
                        url_end += 1
                    url_ranges.append((url_start, url_end))
                    start = marker_index + len(marker)

            for match in candidate_pattern.finditer(line):
                candidate = match.group(0).rstrip(".,;:!?)\"'")
                if not candidate:
                    continue
                if match.start() > 0 and line[match.start() - 1] == "/":
                    continue
                if match.end() < len(line) and line[match.end()] == "<":
                    continue
                if re.fullmatch(r"\d+/\d+", candidate):
                    continue
                first_segment = candidate.split("/", 1)[0].casefold()
                if first_segment.endswith(
                    (".com", ".io", ".org", ".net", ".dev")
                ):
                    continue
                if any(
                    url_start <= match.start() < url_end
                    for url_start, url_end in url_ranges
                ):
                    continue
                if candidate.startswith("/") or "${" in candidate:
                    continue
                if "/" not in candidate and Path(candidate).suffix not in known_path_extensions:
                    continue

                if candidate in tracked_set:
                    graph["edges"].append(
                        {
                            "referrer": referrer,
                            "line": line_number,
                            "candidate": candidate,
                            "resolved": candidate,
                            "severity": "hard",
                        }
                    )
                elif any(path.startswith(candidate + "/") for path in tracked):
                    graph["edges"].append(
                        {
                            "referrer": referrer,
                            "line": line_number,
                            "candidate": candidate,
                            "resolved": candidate,
                            "severity": "hard",
                        }
                    )
                else:
                    graph["dangling"].append(
                        {
                            "referrer": referrer,
                            "line": line_number,
                            "candidate": candidate,
                        }
                    )

    return graph


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def build_manifest(repo_root: Path, rules_path: Path | None = None) -> dict:
    rules_path = rules_path or _within_repo(repo_root, repo_root / _DEFAULT_RULES)
    rules = load_rules(rules_path)
    tracked = tracked_files(repo_root)
    classifications = {path: classify(path, rules) for path in tracked}
    targets = {
        path: classification["target_path"]
        for path, classification in classifications.items()
        if classification["target_path"]
    }
    collisions = detect_collisions(tracked, targets)
    for target_path in targets.values():
        for violation in check_portability(target_path):
            collisions["portability"].append(
                {
                    "paths": [target_path],
                    "description": violation["detail"],
                }
            )
    graph = build_reference_graph(repo_root, tracked)
    reference_graph = {
        **graph,
        "method": "static_text_scan",
        "completeness": "best_effort",
    }
    rules_by_id = {rule["id"]: rule for rule in rules["rules"]}

    entries = []
    self_referential_generated_paths = {
        _MANIFEST_JSON.as_posix(),
        _MANIFEST_MARKDOWN.as_posix(),
        "governance/STATE-CURRENT.json",
        "governance/STATE-CURRENT.md",
        "governance/AUTHORITY-MAP.md",
    }
    for path in sorted(tracked):
        classification = classifications[path]
        rule = rules_by_id[classification["rule_id"]]
        if path in self_referential_generated_paths:
            # Ces sorties générées s'auto-référencent : leurs métadonnées de contenu
            # doivent rester nulles pour éviter un point fixe non déterministe.
            size = None
            file_type = None
            sha256 = None
        else:
            file_path = _within_repo(repo_root, repo_root / path)
            file_data = file_path.read_bytes()
            try:
                file_data.decode("utf-8")
                file_type = "text"
            except UnicodeDecodeError:
                file_type = "binary"
            size = file_path.stat().st_size
            sha256 = _sha256(file_data)
        entries.append(
            {
                "path": path,
                "size": size,
                "type": file_type,
                "sha256": sha256,
                "class": classification["class"],
                "generated": classification["generated"],
                "owner": classification["owner"],
                "rule_id": classification["rule_id"],
                "target_path": classification["target_path"],
                "load_bearing": rule.get("load_bearing", False),
                "referenced_by": [
                    edge for edge in graph["edges"] if edge["resolved"] == path
                ],
            }
        )

    by_class: dict[str, int] = {}
    by_rule: dict[str, int] = {}
    for entry in entries:
        by_class[entry["class"]] = by_class.get(entry["class"], 0) + 1
        by_rule[entry["rule_id"]] = by_rule.get(entry["rule_id"], 0) + 1

    summary = {
        "tracked_total": len(tracked),
        "by_class": by_class,
        "by_rule": by_rule,
        "generated_total": sum(
            entry["generated"] is True for entry in entries
        ),
        "load_bearing_total": sum(
            entry["load_bearing"] is True for entry in entries
        ),
        "unclassified_total": 0,
        "case_collisions_total": len(collisions["case"]),
        "unicode_anomalies_total": sum(
            entry.get("kind") == "non_nfc"
            for entry in collisions["unicode"]
        ),
        "portability_violations_total": len(collisions["portability"]),
        "dangling_references_total": len(graph["dangling"]),
    }

    manifest = {
        "rules_sha256": _sha256(rules_path.read_bytes()),
        "entries": entries,
        "summary": summary,
        "collisions": collisions,
        "reference_graph": reference_graph,
    }
    manifest["waves"] = compute_waves(manifest)
    return manifest


def render(manifest: dict) -> str:
    summary = manifest["summary"]
    lines = [
        "# Classification des chemins",
        "",
        "NE PAS ÉDITER À LA MAIN — généré par scripts/governance/classify_paths.py --render",
        "",
        "## Résumé",
        "",
        f"- Fichiers suivis : {summary['tracked_total']}",
        f"- Fichiers générés : {summary['generated_total']}",
        f"- Éléments porteurs : {summary['load_bearing_total']}",
        f"- Fichiers non classés : {summary['unclassified_total']}",
        f"- Collisions de casse : {summary['case_collisions_total']}",
        f"- Anomalies Unicode NFC : {summary['unicode_anomalies_total']}",
        f"- Violations de portabilité : {summary['portability_violations_total']}",
        f"- Références pendantes : {summary['dangling_references_total']}",
        "(balayage textuel best-effort — une majorité de ces candidats sont du bruit connu : unités de mesure, clés de labels, ratios ; à trier manuellement avant toute décision de migration, voir governance/path-classification.json → reference_graph.dangling)",
        "",
        "## Répartition par classe",
        "",
    ]

    for classification, total in sorted(summary["by_class"].items()):
        lines.append(f"- {classification} : {total}")

    lines.extend(
        [
            "",
            "## Plan de migration",
            "",
            f"- Vagues : {len(manifest['waves'])}",
        ]
    )

    for wave in manifest["waves"]:
        lines.append(f"- Vague {wave['id']} : {len(wave['paths'])} chemin(s)")

    lines.extend(
        [
            "",
            "## Intégrité",
            "",
            f"- SHA-256 des règles : `{manifest['rules_sha256']}`",
            "",
            "L'inventaire complet des chemins est disponible dans `governance/path-classification.json`.",
            "",
        ]
    )
    return "\n".join(lines)


def check(repo_root: Path, rules_path: Path | None = None) -> tuple[bool, list[str]]:
    current = build_manifest(repo_root, rules_path)
    errors: list[str] = []

    manifest_path = _within_repo(repo_root, repo_root / _MANIFEST_JSON)
    markdown_path = _within_repo(repo_root, repo_root / _MANIFEST_MARKDOWN)

    if not manifest_path.exists():
        errors.append("fichier absent : governance/path-classification.json")
    else:
        disk_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        disk_summary = disk_manifest.get("summary", {})
        current_summary = current["summary"]

        for field in sorted(set(disk_summary) | set(current_summary)):
            disk_value = disk_summary.get(field)
            current_value = current_summary.get(field)
            if disk_value != current_value:
                errors.append(
                    f"summary divergent pour {field} : disque={disk_value!r}, "
                    f"recalculée={current_value!r}"
                )

        disk_entries = disk_manifest.get("entries")
        current_entries = current["entries"]
        if disk_entries != current_entries:
            if isinstance(disk_entries, list) and len(disk_entries) != len(current_entries):
                errors.append(
                    "entries divergentes : nombre d'entrées différent "
                    f"(disque={len(disk_entries)}, recalculée={len(current_entries)})"
                )
            else:
                errors.append("entries divergentes entre le disque et le recalcul")

        for field in ("rules_sha256", "collisions", "reference_graph"):
            if disk_manifest.get(field) != current.get(field):
                errors.append(f"{field} divergent entre le disque et le recalcul")

    if not markdown_path.exists():
        errors.append("fichier absent : governance/PATH-CLASSIFICATION.md")
    else:
        disk_markdown = markdown_path.read_text(encoding="utf-8")
        current_markdown = render(current)
        if disk_markdown != current_markdown:
            errors.append(
                "Markdown divergent : governance/PATH-CLASSIFICATION.md"
            )

    if current["summary"]["case_collisions_total"] > 0:
        errors.append(
            "collisions de casse détectées : "
            f"{current['summary']['case_collisions_total']}"
        )
    unicode_collisions_total = sum(
        len(entry["paths"]) > 1
        for entry in current["collisions"]["unicode"]
    )
    if unicode_collisions_total > 0:
        errors.append(
            "collisions Unicode réelles détectées : "
            f"{unicode_collisions_total}"
        )
    if current["summary"]["portability_violations_total"] > 0:
        errors.append(
            "violations de portabilité détectées : "
            f"{current['summary']['portability_violations_total']}"
        )

    if errors:
        errors.append(
            "corriger par : python3 scripts/governance/classify_paths.py --render"
        )
        return False, errors

    return True, []


def compute_waves(manifest: dict) -> list[dict]:
    target_paths = {
        entry["path"]: entry["target_path"]
        for entry in manifest["entries"]
        if entry["target_path"] is not None
    }
    migrating_paths = set(target_paths)
    prerequisites: dict[str, set[str]] = {
        path: set() for path in migrating_paths
    }
    dependents: dict[str, set[str]] = {
        path: set() for path in migrating_paths
    }

    for edge in manifest["reference_graph"]["edges"]:
        if edge.get("severity") != "hard":
            continue

        referrer = edge.get("referrer")
        resolved = edge.get("resolved")
        if referrer not in migrating_paths or resolved not in migrating_paths:
            continue
        if referrer == resolved:
            continue

        prerequisites[referrer].add(resolved)
        dependents[resolved].add(referrer)

    remaining_prerequisites = {
        path: set(path_prerequisites)
        for path, path_prerequisites in prerequisites.items()
    }
    unplaced = set(migrating_paths)
    waves: list[dict] = []
    wave_id = 0

    while unplaced:
        current_paths = sorted(
            path
            for path in unplaced
            if not remaining_prerequisites[path]
        )
        if not current_paths:
            remaining_paths = sorted(unplaced)
            raise ValueError(
                "cycle de dépendances détecté impliquant : "
                f"{remaining_paths[0]}"
            )

        rollback_pairs = "; ".join(
            f"git mv {target_paths[path]} {path}" for path in current_paths
        )
        rollback = (
            f"Vague {wave_id} : {len(current_paths)} chemin(s). "
            f"Rollback = {rollback_pairs} (ordre inverse), puis git commit "
            "--amend ou nouveau commit de restauration ; ne PAS exécuter cette "
            "vague sans avoir d'abord validé les vagues précédentes."
        )
        waves.append(
            {
                "id": wave_id,
                "paths": current_paths,
                "rollback": rollback,
            }
        )

        for path in current_paths:
            unplaced.remove(path)
            for dependent in dependents[path]:
                remaining_prerequisites[dependent].discard(path)

        wave_id += 1

    return waves


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--render", action="store_true")
    arguments = parser.parse_args(argv)
    repo_root = arguments.repo_root

    try:
        if arguments.render:
            manifest = build_manifest(repo_root)
            manifest_path = _within_repo(repo_root, repo_root / _MANIFEST_JSON)
            markdown_path = _within_repo(repo_root, repo_root / _MANIFEST_MARKDOWN)
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            markdown_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(
                json.dumps(
                    manifest,
                    sort_keys=True,
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            markdown_path.write_text(render(manifest), encoding="utf-8")
            return 0

        ok, errors = check(repo_root)
        for error in errors:
            print(error, file=sys.stderr)
        return 0 if ok else 1
    except (OSError, UnicodeError, ValueError, TypeError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
