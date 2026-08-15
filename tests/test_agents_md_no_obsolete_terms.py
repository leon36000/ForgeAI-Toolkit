from pathlib import Path


def _agents_md_content() -> str:
    return (Path(__file__).resolve().parents[1] / "AGENTS.md").read_text(encoding="utf-8")


def test_agents_md_ne_mentionne_plus_64_packages() -> None:
    contenu = _agents_md_content()
    assert "64 packages" not in contenu


def test_agents_md_ne_mentionne_plus_six_claims() -> None:
    contenu = _agents_md_content()
    assert "six claims" not in contenu


def test_agents_md_ne_mentionne_plus_6_claims() -> None:
    contenu = _agents_md_content()
    assert "6 claims" not in contenu


def test_agents_md_ne_mentionne_plus_cockpit_github_copilot() -> None:
    contenu = _agents_md_content()
    assert "cockpit est GitHub Copilot" not in contenu


def test_agents_md_ne_mentionne_plus_cockpit_copilot() -> None:
    contenu = _agents_md_content()
    assert "cockpit est Copilot" not in contenu


def test_agents_md_ne_mentionne_plus_copilot_cockpit() -> None:
    contenu = _agents_md_content()
    assert "COPILOT (cockpit)" not in contenu


def test_agents_md_ne_mentionne_plus_orch001_actif_depuis_m0() -> None:
    contenu = _agents_md_content()
    assert "ORCH-001 — actif depuis M0" not in contenu


def test_agents_md_mentionne_claude_code_opus_mission_lead() -> None:
    contenu = _agents_md_content()
    assert "Claude Code Opus est mission lead, gestionnaire du DAG et intégrateur" in contenu
