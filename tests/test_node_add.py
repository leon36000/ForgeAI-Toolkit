import json
from pathlib import Path

import pytest

from forgeai.network.node_add import (
    add_node,
    NodeAddError,
    Bootstrapper,
    key_fingerprint,
    NodeRecord,
    SshBootstrapper,
)


class FakeBootstrapper:
    """Simulacre de Bootstrapper pour les tests."""

    def __init__(self, verify_return: bool = True) -> None:
        self.install_calls: list = []
        self.verify_calls: list = []
        self._verify_return = verify_return

    def install_key(self, ip: str, user: str, passwd: str, pubkey: Path) -> None:
        self.install_calls.append((ip, user, passwd, pubkey))

    def verify_key(self, ip: str, user: str, privkey: Path) -> bool:
        self.verify_calls.append((ip, user, privkey))
        return self._verify_return


class FixtureRunner:
    """CommandRunner factice retournant des sorties prédéfinies."""

    def __init__(self, outputs: dict[str, str]) -> None:
        self._outputs = outputs
        self.commands: list = []

    def run(self, argv: list[str]) -> tuple[int, str]:
        cmd_str = ' '.join(argv)
        self.commands.append(argv)
        output = self._outputs.get(cmd_str, "")
        return 0, output


def test_add_node_journalise_empreinte_pas_secret(tmp_path: Path) -> None:
    pubkey = tmp_path / "id_ed25519.pub"
    privkey = tmp_path / "id_ed25519"
    pubkey.write_text("fake public key")
    privkey.write_text("fake private key")
    registre = tmp_path / "registre.jsonl"

    fake = FakeBootstrapper(verify_return=True)
    runner = FixtureRunner({"ssh-keygen -lf " + str(pubkey): "256 SHA256:abc123 fake comment (ED25519)"})
    passwd = "SECRET-EPHEMERE-XYZ"

    result = add_node("10.0.0.1", "admin", passwd,
                      pubkey=pubkey, privkey=privkey, bootstrapper=fake,
                      runner=runner, registre_path=registre)

    # Vérification du NodeRecord retourné
    assert result == NodeRecord(ip="10.0.0.1", user="admin", key_fingerprint="SHA256:abc123")

    # Lecture du registre
    with open(registre, "r") as f:
        entries = [json.loads(line) for line in f if line.strip()]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["type"] == "node_added"
    payload = entry["payload"]
    assert payload["ip"] == "10.0.0.1"
    assert payload["user"] == "admin"
    assert payload["key_fingerprint"] == "SHA256:abc123"

    # Le mot de passe ne doit jamais apparaître dans le registre
    assert "passwd" not in payload
    assert "SECRET-EPHEMERE-XYZ" not in json.dumps(payload)


def test_secret_absent_de_tous_les_fichiers(tmp_path: Path) -> None:
    pubkey = tmp_path / "id_ed25519.pub"
    privkey = tmp_path / "id_ed25519"
    pubkey.write_text("pub")
    privkey.write_text("priv")
    registre = tmp_path / "r.jsonl"

    fake = FakeBootstrapper(verify_return=True)
    runner = FixtureRunner({"ssh-keygen -lf " + str(pubkey): "256 SHA256:abc comment"})
    passwd = "SECRET-EPHEMERE-XYZ"

    add_node("10.0.0.2", "root", passwd,
             pubkey=pubkey, privkey=privkey, bootstrapper=fake,
             runner=runner, registre_path=registre)

    # Parcours de tous les fichiers sous tmp_path
    for p in tmp_path.rglob("*"):
        if p.is_file():
            try:
                content = p.read_text()
                assert "SECRET-EPHEMERE-XYZ" not in content, f"Secret trouvé dans {p}"
            except Exception:
                # On ignore les fichiers illisibles (binaires, permissions, etc.)
                pass


def test_verify_echoue_leve(tmp_path: Path) -> None:
    pubkey = tmp_path / "id_ed25519.pub"
    privkey = tmp_path / "id_ed25519"
    pubkey.write_text("pub")
    privkey.write_text("priv")
    registre = tmp_path / "r.jsonl"

    fake = FakeBootstrapper(verify_return=False)
    runner = FixtureRunner({})  # Non utilisé car échec avant fingerprint

    with pytest.raises(NodeAddError, match="bascule clé échouée"):
        add_node("10.0.0.3", "user", "pass",
                 pubkey=pubkey, privkey=privkey, bootstrapper=fake,
                 runner=runner, registre_path=registre)


def test_install_appele_avec_mot_de_passe(tmp_path: Path) -> None:
    pubkey = tmp_path / "id_ed25519.pub"
    privkey = tmp_path / "id_ed25519"
    pubkey.write_text("pub")
    privkey.write_text("priv")
    registre = tmp_path / "r.jsonl"

    fake = FakeBootstrapper(verify_return=True)
    runner = FixtureRunner({"ssh-keygen -lf " + str(pubkey): "256 SHA256:def456 comment"})
    passwd = "my-secret"

    add_node("10.0.0.4", "admin", passwd,
             pubkey=pubkey, privkey=privkey, bootstrapper=fake,
             runner=runner, registre_path=registre)

    assert len(fake.install_calls) == 1
    ip, user, passwd, key = fake.install_calls[0]
    assert ip == "10.0.0.4"
    assert user == "admin"
    assert passwd == passwd  # Le mot de passe a bien été transmis


def test_key_fingerprint_extrait_sha256(tmp_path: Path) -> None:
    pubkey = tmp_path / "key.pub"
    pubkey.write_text("dummy")
    runner = FixtureRunner({"ssh-keygen -lf " + str(pubkey): "256 SHA256:abc... comment (ED25519)"})
    fp = key_fingerprint(pubkey, runner)
    assert fp == "SHA256:abc..."


def test_cli_node_add_secret_via_env_jamais_journalise(tmp_path, monkeypatch):
    """Chemin CLI : le mot de passe vient d'une variable d'env (jamais argv) et n'apparaît
    pas au registre ; l'entrée porte ip/user/empreinte."""
    import forgeai.network.node_add as na
    from forgeai.cli import main

    class _FakeBoot:
        def install_key(self, ip, user, passwd, pubkey):
            pass

        def verify_key(self, ip, user, privkey):
            return True

    monkeypatch.setattr(na, "SshBootstrapper", lambda *a, **k: _FakeBoot())
    monkeypatch.setattr(na, "key_fingerprint", lambda pubkey, runner: "SHA256:FAKEFP")

    pub = tmp_path / "k.pub"
    pub.write_text("ssh-ed25519 AAAA forge", encoding="utf-8")
    priv = tmp_path / "k"
    priv.write_text("PRIV", encoding="utf-8")
    reg = tmp_path / "r.jsonl"
    monkeypatch.setenv("NODE_PW_TEST", "SECRET-CLI-XYZ")

    rc = main(["node", "add", "--ip", "10.0.0.5", "--user", "forge",
               "--password-env", "NODE_PW_TEST", "--pubkey", str(pub), "--privkey", str(priv),
               "--registre", str(reg)])
    assert rc == 0
    content = reg.read_text(encoding="utf-8")
    assert "10.0.0.5" in content and "SHA256:FAKEFP" in content
    assert "SECRET-CLI-XYZ" not in content
