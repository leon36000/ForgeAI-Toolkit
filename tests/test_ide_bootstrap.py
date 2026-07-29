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


import dataclasses
from forgeai.ide.bootstrap import HookSpec


class TestHookSpecNormalisation:

    def test_hookspec_seul_genere_un_dict_avec_matcher_explicite(self):
        """HookSpec seul -> clé unique, matcher explicite, structure complète."""
        spec = HookSpec(event="PreToolUse", command="python3 /x/garde.py", matcher="Write|Edit")
        cfg = generate_governance_config(skills=[], hooks=[spec])
        hooks = json.loads(cfg.content)["hooks"]
        assert hooks == {
            "PreToolUse": [
                {
                    "matcher": "Write|Edit",
                    "hooks": [{"type": "command", "command": "python3 /x/garde.py"}],
                }
            ]
        }

    def test_melange_str_et_hookspec_coexistent_avec_forme_historique_pour_str(self):
        """Mélange str + HookSpec -> deux clés ; la str garde event==command et matcher '*'."""
        spec = HookSpec(event="PreToolUse", command="cmd")
        cfg = generate_governance_config(
            skills=[],
            hooks=["SessionStart", spec],
        )
        hooks = json.loads(cfg.content)["hooks"]
        assert set(hooks.keys()) == {"SessionStart", "PreToolUse"}
        assert hooks["SessionStart"] == [
            {
                "matcher": "*",
                "hooks": [{"type": "command", "command": "SessionStart"}],
            }
        ]
        assert hooks["PreToolUse"] == [
            {
                "matcher": "*",
                "hooks": [{"type": "command", "command": "cmd"}],
            }
        ]

    def test_deux_hookspec_meme_event_une_seule_cle_ordre_preservé(self):
        """Deux HookSpec sur le même event -> une seule clé, deux règles, ordre d'origine conservé."""
        spec1 = HookSpec(event="PreToolUse", command="a", matcher="Write")
        spec2 = HookSpec(event="PreToolUse", command="b", matcher="Edit")
        cfg = generate_governance_config(skills=[], hooks=[spec1, spec2])
        hooks = json.loads(cfg.content)["hooks"]
        assert list(hooks.keys()) == ["PreToolUse"]
        assert hooks["PreToolUse"] == [
            {
                "matcher": "Write",
                "hooks": [{"type": "command", "command": "a"}],
            },
            {
                "matcher": "Edit",
                "hooks": [{"type": "command", "command": "b"}],
            },
        ]

    def test_champs_vides_levent_ideerror(self):
        """event / command / matcher vides -> IDEError (vérif via __post_init__)."""
        with pytest.raises(IDEError):
            HookSpec(event="", command="cmd")
        with pytest.raises(IDEError):
            HookSpec(event="PreToolUse", command="")
        with pytest.raises(IDEError):
            HookSpec(event="PreToolUse", command="cmd", matcher="")

    def test_hookspec_est_gelee(self):
        """HookSpec est frozen -> toute affectation d'attribut lève FrozenInstanceError."""
        spec = HookSpec(event="PreToolUse", command="cmd")
        with pytest.raises(dataclasses.FrozenInstanceError):
            spec.event = "PostToolUse"
        with pytest.raises(dataclasses.FrozenInstanceError):
            spec.command = "autre"
        with pytest.raises(dataclasses.FrozenInstanceError):
            spec.matcher = "Edit"


# O1 — déduplication stricte des règles identiques
def test_hooks_str_doublon_produit_une_seule_regle():
    """["A", "A"] : une seule règle, pas deux exécutions de la même commande."""
    cfg = generate_governance_config(skills=["s"], hooks=["A", "A"])
    data = json.loads(cfg.content)
    assert data["hooks"]["A"] == [
        {"matcher": "*", "hooks": [{"type": "command", "command": "A"}]}
    ]
    assert len(data["hooks"]["A"]) == 1


def test_hooks_hookspec_doublon_strict_produit_une_seule_regle():
    """[HookSpec(e, c1), HookSpec(e, c1)] : une seule règle (dedup strict)."""
    cfg = generate_governance_config(
        skills=["s"], hooks=[HookSpec("e", "c1"), HookSpec("e", "c1")]
    )
    data = json.loads(cfg.content)
    assert len(data["hooks"]["e"]) == 1
    assert data["hooks"]["e"][0]["matcher"] == "*"
    assert data["hooks"]["e"][0]["hooks"][0]["command"] == "c1"


def test_hooks_hookspec_distincts_sont_agreges():
    """[HookSpec(e, c1, m1), HookSpec(e, c2, m2)] : DEUX règles (distinctes)."""
    cfg = generate_governance_config(
        skills=["s"],
        hooks=[
            HookSpec("e", "c1", "m1"),
            HookSpec("e", "c2", "m2"),
        ],
    )
    data = json.loads(cfg.content)
    assert len(data["hooks"]["e"]) == 2
    matchers = {r["matcher"] for r in data["hooks"]["e"]}
    assert matchers == {"m1", "m2"}


def test_hooks_str_et_hookpec_meme_event_et_meme_commande_dedupliques():
    """["A", HookSpec("A","A")] : une seule règle (équivalence stricte)."""
    cfg = generate_governance_config(
        skills=["s"],
        hooks=["A", HookSpec("A", "A")],
    )
    data = json.loads(cfg.content)
    assert len(data["hooks"]["A"]) == 1


def test_hooks_meme_event_mais_commandes_differentes_pas_dedupliques():
    """["A", HookSpec("A", "B")] : deux règles (commandes différentes)."""
    cfg = generate_governance_config(
        skills=["s"],
        hooks=["A", HookSpec("A", "B")],
    )
    data = json.loads(cfg.content)
    assert len(data["hooks"]["A"]) == 2


# O2+O3 — validation : type strict + whitespace + contournement object.__setattr__
def test_hookspec_event_whitespace_leve_ideerror():
    with pytest.raises(IDEError) as exc:
        HookSpec(event=" ", command="c", matcher="*")
    assert "event" in str(exc.value)


def test_hookspec_command_whitespace_leve_ideerror():
    with pytest.raises(IDEError) as exc:
        HookSpec(event="e", command="   ", matcher="*")
    assert "command" in str(exc.value)


def test_hookspec_matcher_whitespace_leve_ideerror():
    with pytest.raises(IDEError) as exc:
        HookSpec(event="e", command="c", matcher="\t\n")
    assert "matcher" in str(exc.value)


def test_hookspec_matcher_liste_leve_ideerror_avec_type_dans_message():
    with pytest.raises(IDEError) as exc:
        HookSpec(event="e", command="c", matcher=["*"])
    msg = str(exc.value)
    assert "matcher" in msg
    # O3 : le type reçu doit figurer dans le message pour faciliter le diagnostic.
    assert "list" in msg


def test_hookspec_event_int_leve_ideerror_avec_type_dans_message():
    with pytest.raises(IDEError) as exc:
        HookSpec(event=42, command="c", matcher="*")
    msg = str(exc.value)
    assert "event" in msg
    assert "int" in msg


def test_hookspec_command_int_leve_ideerror_avec_type_dans_message():
    with pytest.raises(IDEError) as exc:
        HookSpec(event="e", command=42, matcher="*")
    msg = str(exc.value)
    assert "command" in msg
    assert "int" in msg


def test_generate_governance_rejette_hookspec_mute_via_object_setattr():
    """Le contournement object.__setattr__(frozen_hookspec, ...) doit être rattrapé
    à l'usage (la validation de construction seule ne suffit pas)."""
    spec = HookSpec(event="e", command="c", matcher="*")
    # Bypass du gel : object.__setattr__ saute le __setattr__ généré par le
    # décorateur @dataclass(frozen=True).
    object.__setattr__(spec, "event", "")
    with pytest.raises(IDEError) as exc:
        generate_governance_config(skills=["s"], hooks=[spec])
    assert "event" in str(exc.value)


def test_generate_governance_rejette_hookspec_mute_command_whitespace():
    spec = HookSpec(event="e", command="c", matcher="*")
    object.__setattr__(spec, "command", "   ")
    with pytest.raises(IDEError) as exc:
        generate_governance_config(skills=["s"], hooks=[spec])
    assert "command" in str(exc.value)


def test_generate_governance_rejette_hookspec_mute_matcher_liste():
    spec = HookSpec(event="e", command="c", matcher="*")
    object.__setattr__(spec, "matcher", ["*"])
    with pytest.raises(IDEError) as exc:
        generate_governance_config(skills=["s"], hooks=[spec])
    assert "matcher" in str(exc.value)
    assert "list" in str(exc.value)


def test_hookspec_vide_a_la_construction_leve_ideerror():
    with pytest.raises(IDEError):
        HookSpec(event="", command="c", matcher="*")


# O4 — chaîne vide str : durcissement documenté
def test_hook_str_vide_leve_ideerror():
    with pytest.raises(IDEError):
        generate_governance_config(skills=["s"], hooks=[""])


def test_hook_str_whitespace_leve_ideerror():
    with pytest.raises(IDEError):
        generate_governance_config(skills=["s"], hooks=["   "])


def test_docstring_generate_governance_documente_durcissement_chaine_vide():
    """O4 : la docstring doit explicitement mentionner que la chaîne vide est
    rejetée (durcissement volontaire, pas un bug)."""
    doc = generate_governance_config.__doc__ or ""
    # Présence d'au moins un mot-clé indiquant que la chaîne vide est rejetée.
    lowered = doc.lower()
    assert (
        "chaîne vide" in lowered
        or "chaine vide" in lowered
        or ("vide" in lowered and "durcissement" in lowered)
    )


def test_docstring_generate_governance_documente_dedup_strict():
    """O1 : la docstring doit mentionner la déduplication stricte des règles."""
    doc = generate_governance_config.__doc__ or ""
    assert "édupliqu" in doc.lower() or "dedupliqu" in doc.lower()
