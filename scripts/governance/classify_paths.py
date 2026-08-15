import unicodedata


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
