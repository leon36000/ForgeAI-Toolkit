import pytest
import json
from forgeai.ide.bootstrap import (
    McpServer,
    generate_mcp_config,
    generate_governance_config,
    verify_bootstrap,
    MCP_CAPABLE,
)
from forgeai.ide import IDEError, IdeConfig


class TestMcpPerIde:
    def test_mcp_par_ide_contient_serveurs(self):
        """Pour chaque IDE compatible MCP, le JSON produit contient le nom et l'URL du serveur."""
        server = McpServer(name="forge-mem", url="http://localhost:4000/mcp/mem")
        for ide in MCP_CAPABLE:
            ide_cfg = generate_mcp_config(ide, [server])
            data = json.loads(ide_cfg.content)
            if ide in ("claude-code", "cline"):
                assert "mcpServers" in data
                servers = data["mcpServers"]
                assert "forge-mem" in servers
                srv = servers["forge-mem"]
                assert srv["url"] == server.url
                assert srv["type"] == "http"
            elif ide == "cursor":
                assert "mcpServers" in data
                srv = data["mcpServers"]["forge-mem"]
                assert srv["url"] == server.url
                assert "type" not in srv
            elif ide == "opencode":
                assert "mcp" in data
                srv = data["mcp"]["forge-mem"]
                assert srv["url"] == server.url
                assert srv["type"] == "remote"
                assert srv["enabled"] is True

    def test_mcp_aider_leve(self):
        """Aider n'est pas MCP‑capable et doit lever IDEError."""
        server = McpServer(name="x", url="http://y")
        with pytest.raises(IDEError):
            generate_mcp_config("aider", [server])

    def test_mcp_sans_serveur_leve(self):
        """Une liste vide de serveurs doit lever IDEError."""
        with pytest.raises(IDEError, match="aucun serveur MCP"):
            generate_mcp_config("claude-code", [])

    def test_mcp_transport_invalide_leve(self):
        """Un transport non autorisé lève IDEError dès la construction du McpServer."""
        with pytest.raises(IDEError):
            McpServer(name="x", url="http://y", transport="ftp")


class TestGovernance:
    def test_governance_claude_code(self):
        """Vérifie la structure du fichier settings.json pour claude-code."""
        cfg = generate_governance_config(
            skills=["Skill(read)"], hooks=["pre-commit-guard"]
        )
        data = json.loads(cfg.content)
        assert "permissions" in data
        assert "hooks" in data
        assert "Skill(read)" in data["permissions"]["allow"]
        hooks = data["hooks"]
        assert "pre-commit-guard" in hooks
        assert hooks["pre-commit-guard"] == [
            {
                "matcher": "*",
                "hooks": [{"type": "command", "command": "pre-commit-guard"}],
            }
        ]

    def test_governance_autre_ide_leve(self):
        """Seul claude-code est accepté ; tout autre IDE lève IDEError."""
        with pytest.raises(IDEError):
            generate_governance_config([], [], ide="cline")


class TestVerifyBootstrap:
    def test_verify_bootstrap_ok_et_ko(self):
        """Une combinaison de configurations valides donne une liste vide ;
        un contenu JSON corrompu provoque une erreur."""
        # configs valides
        mcp_cfg = generate_mcp_config(
            "claude-code", [McpServer(name="forge-mem", url="http://localhost:4000/mcp/mem")]
        )
        gov_cfg = generate_governance_config(
            skills=["Skill(read)"], hooks=["pre-commit-guard"]
        )
        assert verify_bootstrap(mcp_cfg, gov_cfg) == []

        # config JSON invalide
        bad_cfg = IdeConfig(ide="claude-code", path=".mcp.json", content="{bad", fmt="json")
        problems = verify_bootstrap(bad_cfg)
        assert len(problems) == 1
        assert "JSON invalide" in problems[0]

        # config MCP sans serveur : generate_mcp_config([]) lève IDEError en amont, donc on
        # construit un IdeConfig à la main avec un mcpServers vide pour tester verify_bootstrap.
        empty_data = json.dumps({"mcpServers": {}}, ensure_ascii=False, indent=1)
        empty_cfg = IdeConfig(ide="claude-code", path=".mcp.json", content=empty_data, fmt="json")
        problems2 = verify_bootstrap(empty_cfg)
        assert len(problems2) == 1
        assert "sans serveur" in problems2[0]

        # config gouvernance sans permissions
        bad_gov_data = json.dumps({"hooks": {}}, ensure_ascii=False, indent=1)
        bad_gov_cfg = IdeConfig(ide="claude-code", path=".claude/settings.json", content=bad_gov_data, fmt="json")
        problems3 = verify_bootstrap(bad_gov_cfg)
        assert len(problems3) == 1
        assert "sans clé 'permissions' ou 'hooks'" in problems3[0]


def test_cli_ide_mcp_et_governance(tmp_path):
    """Chemin CLI : forgeai ide mcp + governance écrivent les configs attendues."""
    from forgeai.cli import main

    reg = tmp_path / "r.jsonl"
    assert main(["ide", "mcp", "--ide", "claude-code",
                 "--server", "forge-mem=http://localhost:4000/mcp/mem",
                 "--dest", str(tmp_path), "--registre", str(reg)]) == 0
    mcp_file = tmp_path / ".mcp.json"
    assert mcp_file.exists()
    assert "forge-mem" in json.loads(mcp_file.read_text(encoding="utf-8"))["mcpServers"]

    assert main(["ide", "governance", "--ide", "claude-code",
                 "--skill", "Skill(read)", "--hook", "pre-commit-guard",
                 "--dest", str(tmp_path), "--registre", str(reg)]) == 0
    gov_file = tmp_path / ".claude" / "settings.json"
    assert gov_file.exists()
    gov = json.loads(gov_file.read_text(encoding="utf-8"))
    assert "Skill(read)" in gov["permissions"]["allow"]
    assert "pre-commit-guard" in gov["hooks"]
