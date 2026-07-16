from __future__ import annotations

import json
from pathlib import Path

import pytest

from forgeai.ide import (
    IDEError,
    SUPPORTED_IDES,
    IdeConfig,
    generate_ide_config,
    list_ides,
    write_ide_config,
)


@pytest.mark.parametrize("ide", SUPPORTED_IDES)
def test_tous_ides_generent_config_avec_gateway_et_modele(ide: str):
    """Chaque IDE produit un contenu contenant l'URL gateway et le modèle."""
    gw = "http://localhost:4000"
    model = "gpt-oss"
    cfg = generate_ide_config(ide, gw, model)
    assert isinstance(cfg, IdeConfig)
    assert gw in cfg.content
    # Le modèle est toujours présent, éventuellement préfixé pour aider
    assert model in cfg.content


def test_json_ides_parsables():
    """Les configurations au format JSON sont valides."""
    gw = "http://localhost:4000"
    model = "gpt-oss"
    for ide in SUPPORTED_IDES:
        cfg = generate_ide_config(ide, gw, model)
        if cfg.fmt == "json":
            try:
                json.loads(cfg.content)
            except json.JSONDecodeError as e:
                pytest.fail(f"JSON invalide pour {ide}: {e}")


def test_aucune_cle_en_clair():
    """Invariant sécurité : le générateur ne reçoit jamais la VALEUR de clé (seulement le nom
    d'env key_env), donc aucune clé littérale possible. Les formats JSON portent la référence
    ${FORGEAI_GATEWAY_KEY} ; aider s'appuie sur $OPENAI_API_KEY (aucune clé dans le fichier)."""
    gw = "http://localhost:4000"
    model = "gpt-oss"
    for ide in SUPPORTED_IDES:
        cfg = generate_ide_config(ide, gw, model, key_env="FORGEAI_GATEWAY_KEY")
        if ide == "aider":
            assert "OPENAI_API_KEY" in cfg.content
            for line in cfg.content.splitlines():
                s = line.strip()
                assert not (s.startswith("api_key") or s.startswith("token")), \
                    f"ligne suspecte dans aider : {line}"
        else:
            assert "${FORGEAI_GATEWAY_KEY}" in cfg.content, \
                f"{ide} : la clé doit être une référence d'env, jamais une valeur"


def test_ide_inconnu_leve():
    """Un IDE non supporté lève IDEError."""
    with pytest.raises(IDEError):
        generate_ide_config("intellij", "http://localhost:4000", "model")


def test_list_ides():
    """list_ides retourne les 5 IDE."""
    assert set(list_ides()) == set(SUPPORTED_IDES)


def test_write_ide_config(tmp_path: Path):
    """write_ide_config écrit le fichier au bon endroit avec le bon contenu."""
    gw = "http://localhost:4000"
    model = "gpt-oss"
    cfg = generate_ide_config("aider", gw, model)
    written = write_ide_config(cfg, tmp_path)
    expected_path = tmp_path / ".aider.conf.yml"
    assert written == expected_path.resolve()
    assert expected_path.exists()
    content = expected_path.read_text()
    assert gw in content


def test_cli_ide_list_et_configure(tmp_path, capsys):
    """Chemin CLI : forgeai ide list + configure écrit une config pointant vers le gateway."""
    from forgeai.cli import main

    assert main(["ide", "list"]) == 0
    out = capsys.readouterr().out
    assert "aider" in out and "cline" in out

    reg = tmp_path / "r.jsonl"
    assert main(["ide", "configure", "--ide", "aider", "--model", "gpt-oss",
                 "--gateway-url", "http://localhost:4000", "--dest", str(tmp_path),
                 "--registre", str(reg)]) == 0
    conf = tmp_path / ".aider.conf.yml"
    assert conf.exists()
    assert "http://localhost:4000" in conf.read_text(encoding="utf-8")
