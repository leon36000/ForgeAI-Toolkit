import argparse
import pathlib
import re
import sys


_MARKDOWN_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")

_KNOWN_EXTENSIONS = (
    "md", "py", "json", "jsonl", "yaml", "yml", "txt", "toml", "cfg", "ini", "sh",
    "js", "cjs", "mjs", "ts", "tsx", "jsx", "html", "css", "csv", "lock", "pub",
    "gz", "mdc", "pdf", "sha256", "properties", "svg", "png", "sql", "conf",
)
_BACKTICK_PATH_RE = re.compile(
    r"`([A-Za-z0-9_.][A-Za-z0-9._/-]*/[A-Za-z0-9_.-]+\."
    + r"(?:" + "|".join(_KNOWN_EXTENSIONS) + r"))`"
)

EXCLUDE_PREFIXES = ["CANON/adr/", "governance/decisions/"]


def extract_links(text: str) -> list[tuple[str, int]]:
    links = []

    for line_number, line in enumerate(text.splitlines(), start=1):
        candidates = []

        for match in _MARKDOWN_LINK_RE.finditer(line):
            candidates.append((match.start(), match.group(1)))

        for match in _BACKTICK_PATH_RE.finditer(line):
            candidates.append((match.start(), match.group(1)))

        for _, candidate in sorted(candidates, key=lambda item: item[0]):
            if "://" in candidate or candidate.startswith("#"):
                continue
            links.append((candidate, line_number))

    return links


def _normalize_posix_path(path: pathlib.PurePosixPath) -> str:
    stack = []

    for part in path.parts:
        if part in ("", ".", "/"):
            continue
        if part == "..":
            if stack:
                stack.pop()
            continue
        stack.append(part)

    return "/".join(stack)


def _normalize_root_relative(link: str) -> str:
    return _normalize_posix_path(pathlib.PurePosixPath(link))


def resolve_link(link: str, referrer_path: str) -> str | None:
    if "${" in link:
        return None

    link = link.strip()
    if not link:
        return None

    fragment_index = link.find("#")
    if fragment_index != -1:
        link = link[:fragment_index]
        if not link:
            return None

    referrer = pathlib.PurePosixPath(referrer_path)
    resolved = referrer.parent / link
    return _normalize_posix_path(resolved)


def check_links(paths, contents, known_paths) -> list[dict]:
    results = []

    for path in paths:
        text = contents[path]
        for link, line in extract_links(text):
            resolved = resolve_link(link, path)
            if resolved is None:
                continue
            if resolved in known_paths:
                continue
            if ".." not in pathlib.PurePosixPath(link).parts:
                root_relative = _normalize_root_relative(link)
                if root_relative in known_paths:
                    continue
            results.append(
                {
                    "referrer": path,
                    "line": line,
                    "link": link,
                    "resolved": resolved,
                }
            )

    results.sort(key=lambda result: (result["referrer"], result["line"]))
    return results


def scan_repo(
    repo_root: pathlib.Path,
    scan_globs: list[str],
    exclude_prefixes: list[str] | None = None,
) -> list[dict]:
    known_paths = {
        str(path.relative_to(repo_root).as_posix())
        for path in repo_root.rglob("*")
        if path.is_file() and ".git" not in path.parts
    }

    contents = {}
    paths = []

    for pattern in scan_globs:
        for path in repo_root.glob(pattern):
            if not path.is_file() or path.suffix != ".md":
                continue

            relative_path = str(path.relative_to(repo_root).as_posix())

            if exclude_prefixes and any(
                relative_path.startswith(prefix) for prefix in exclude_prefixes
            ):
                continue

            try:
                text = path.read_text()
            except UnicodeDecodeError:
                continue

            paths.append(relative_path)
            contents[relative_path] = text

    return check_links(paths, contents, known_paths)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=pathlib.Path, default=pathlib.Path.cwd())
    args = parser.parse_args(argv)
    repo_root = args.repo_root.resolve()
    scan_globs = [
        "Docs/**/*.md",
        "governance/**/*.md",
        "README.md",
        "AGENTS.md",
        "CLAUDE.md",
        "MASTER-PLAN.md",
        "CANON/**/*.md",
    ]

    try:
        dead_links = scan_repo(
            repo_root, scan_globs, exclude_prefixes=EXCLUDE_PREFIXES
        )
    except (OSError, UnicodeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if not dead_links:
        return 0

    for entry in dead_links:
        print(
            f"{entry['referrer']}:{entry['line']}: lien mort vers "
            f"{entry['resolved']} (écrit: {entry['link']})",
            file=sys.stderr,
        )

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
