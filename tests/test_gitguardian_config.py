"""Regression tests for the bounded GitGuardian exclusion policy (RC1-015)."""

from __future__ import annotations

from pathlib import Path

import yaml


REPO = Path(__file__).resolve().parents[1]
CONFIG = REPO / ".gitguardian.yaml"
EXPECTED_BOUNDED_EXCLUSIONS = [
    "tests/fixtures/**",
    "src/forgeai/data/catalogue.json",
    "LICENSE",
    ".gitignore",
]


def _ignored_paths(config_path: Path = CONFIG) -> list[str]:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert isinstance(config, dict)
    section = config.get("secret")
    assert isinstance(section, dict)
    paths = section.get("ignored_paths")
    assert isinstance(paths, list)
    assert all(isinstance(path, str) for path in paths)
    return paths


def test_real_config_contains_only_bounded_exclusions() -> None:
    assert _ignored_paths() == EXPECTED_BOUNDED_EXCLUSIONS
    assert not any(path in {"*.md", "**/*.md"} for path in _ignored_paths())


def test_ordinary_markdown_locations_remain_in_scan_scope() -> None:
    ignored = set(_ignored_paths())
    ordinary_markdown = (
        "README.md",
        "Docs/ordinary.md",
        "stories/ordinary.md",
        "evidence/reviews/ordinary.md",
    )
    assert all(path not in ignored for path in ordinary_markdown)


def test_fake_secret_fixture_stays_in_markdown_scan_input(tmp_path: Path) -> None:
    fake_value = "ghp_" + "f" * 36
    document = tmp_path / "Docs" / "ordinary.md"
    document.parent.mkdir()
    document.write_text(f"# Fixture\n\n{fake_value}\n", encoding="utf-8")

    assert fake_value in document.read_text(encoding="utf-8")
    assert "**/*.md" not in _ignored_paths()


def test_bounded_fixture_exclusion_remains_explicit() -> None:
    ignored = _ignored_paths()
    assert "tests/fixtures/**" in ignored
    assert "evidence/reviews/**/*.md" not in ignored
