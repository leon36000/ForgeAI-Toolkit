import fnmatch
import json
import re
import subprocess
import unicodedata
from pathlib import Path


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
        stationary_paths = [
            path
            for path in paths
            if path not in targets or targets[path] == path
        ]
        for target in target_values:
            for path in stationary_paths:
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
                    "rule": "windows_forbidden_char",
                    "segment": segment,
                    "detail": detail,
                }
            )
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
                    "rule": "trailing_dot_or_space",
                    "segment": segment,
                    "detail": detail,
                }
            )
            violations.append(
                {
                    "rule": "windows_trailing_dot_or_space",
                    "segment": segment,
                    "detail": detail,
                }
            )

        if segment == "" or segment == "." or segment == ".." or segment == ".git":
            violations.append(
                {
                    "rule": "illegal_segment",
                    "segment": segment,
                    "detail": "Le segment est vide, réservé ou ne constitue pas un nom de répertoire valide.",
                }
            )
            if segment == ".git":
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
                "rule": "path_too_long",
                "segment": path,
                "detail": detail,
            }
        )
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
                "rule": "path_length_warning",
                "segment": path,
                "detail": detail,
            }
        )
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

    if "reviews/BINDING.txt" in tracked_set:
        try:
            binding_path = _within_repo(
                repo_root, repo_root / "reviews/BINDING.txt"
            )
            for line_number, line in enumerate(
                binding_path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                candidate = line.strip()
                if not candidate or candidate.startswith("#"):
                    continue
                resolved = f"reviews/{candidate}"
                if any(
                    path == resolved or path.startswith(resolved + "/")
                    for path in tracked
                ):
                    graph["edges"].append(
                        {
                            "referrer": "reviews/BINDING.txt",
                            "line": line_number,
                            "candidate": candidate,
                            "resolved": resolved,
                            "severity": "hard",
                        }
                    )
                else:
                    graph["dangling"].append(
                        {
                            "referrer": "reviews/BINDING.txt",
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

    for referrer in tracked:
        path_name = Path(referrer)
        if referrer in structured_referrers:
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
