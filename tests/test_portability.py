import json
from pathlib import Path

import pytest

from forgeai.portability import (
    PortabilityError,
    export_setup,
    import_setup,
    load_bundle,
    verify_bundle,
    bundle_sha256,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
ROUTE_TEMPLATE = {
    "name": "test-route",
    "provenance": "openai",
    "base_url": "https://api.openai.com/v1",
    "model_id": "gpt-4",
    "key_fingerprint": "abc123",
    "created_at": "2025-01-01",
    "cache": False,
    "cache_ttl_s": None,
    "cache_prefix": None,
}

GATEWAY = {"base_url": "http://localhost:4000", "key_env": "OPENAI_API_KEY"}
STRATEGY = {"strategy_type": "round-robin"}
BUDGETS = [{"agent": "writer", "limit_usd": 10.0}]
WIRINGS = {"brick_a": "${GATEWAY_A}"}


def _write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestExportImportRoundtrip:
    """Complete round‑trip with a typical setup."""

    def test_export_import(self, tmp_path: Path):
        # 1. Create source home
        src_home = tmp_path / "source"
        _write_json(src_home / "routes.json", [ROUTE_TEMPLATE])
        _write_json(src_home / "gateway.json", GATEWAY)
        _write_json(src_home / "strategy.json", STRATEGY)
        _write_json(src_home / "budgets.json", BUDGETS)
        _write_json(src_home / "wirings.json", WIRINGS)

        # 2. Export to bundle file
        bundle_path = tmp_path / "exported_bundle.json"
        bundle = export_setup(str(src_home), out_path=str(bundle_path))
        assert isinstance(bundle, dict)
        assert bundle["version"] == 1
        assert "routes.json" in bundle["files"]

        # 3. Import into empty target home
        tgt_home = tmp_path / "target"
        report = import_setup(str(bundle_path), str(tgt_home))
        assert set(report["restored"]) == {"routes.json", "gateway.json", "strategy.json", "budgets.json", "wirings.json"}
        assert report["secrets_to_reprovision"] == ["test-route"]

        # 4. Check that restored files are identical to originals
        for fname in report["restored"]:
            orig = _read_json(src_home / fname)
            restored = _read_json(tgt_home / fname)
            assert orig == restored, f"Mismatch in {fname}"


class TestVaultExclusion:
    def test_vault_jamais_exporte(self, tmp_path: Path):
        home = tmp_path / "source"
        _write_json(home / "routes.json", [ROUTE_TEMPLATE])
        _write_json(home / "vault.json", {"secret": "do-not-leak"})

        bundle = export_setup(str(home))
        assert "vault.json" not in bundle["files"]

        # Also when writing to disk
        out = tmp_path / "out.json"
        export_setup(str(home), out_path=str(out))
        disk_bundle = _read_json(out)
        assert "vault.json" not in disk_bundle["files"]


class TestPlainTextSecretRejection:
    def test_export_refuse_cle_en_clair(self, tmp_path: Path):
        home = tmp_path / "source"
        route_leak = {**ROUTE_TEMPLATE, "api_key": "valeur-secrete-en-clair"}
        _write_json(home / "routes.json", [route_leak])

        with pytest.raises(PortabilityError, match="api_key"):
            export_setup(str(home))


class TestBundleIntegrity:
    def test_bundle_altere_detecte(self, tmp_path: Path):
        # 1. Create a valid bundle file
        src_home = tmp_path / "source"
        _write_json(src_home / "routes.json", [ROUTE_TEMPLATE])
        _write_json(src_home / "gateway.json", GATEWAY)
        bundle_path = tmp_path / "good.json"
        export_setup(str(src_home), out_path=str(bundle_path))

        # 2. Tamper with one file content without recomputing the hash
        bundle = _read_json(bundle_path)
        bundle["files"]["routes.json"][0]["name"] = "corrupted"
        _write_json(bundle_path, bundle)

        # 3. Loading must raise
        with pytest.raises(PortabilityError, match="altéré"):
            load_bundle(str(bundle_path))


class TestImportSafety:
    def test_import_refuse_ecrasement_sans_force(self, tmp_path: Path):
        # Prepare a bundle
        src_home = tmp_path / "source"
        _write_json(src_home / "routes.json", [ROUTE_TEMPLATE])
        _write_json(src_home / "gateway.json", GATEWAY)
        bundle_path = tmp_path / "bundle.json"
        export_setup(str(src_home), out_path=str(bundle_path))

        tgt_home = tmp_path / "target"

        # First import succeeds
        import_setup(str(bundle_path), str(tgt_home))

        # Second import without force must fail
        with pytest.raises(PortabilityError, match="force"):
            import_setup(str(bundle_path), str(tgt_home))

        # Force overwriting succeeds
        report = import_setup(str(bundle_path), str(tgt_home), force=True)
        assert "routes.json" in report["restored"]

        # Ensure content is still correct after force
        restored_route = _read_json(tgt_home / "routes.json")
        assert restored_route[0]["name"] == "test-route"


def test_cli_export_import_roundtrip(tmp_path):
    """Chemin CLI complet : forgeai export puis import recrée le setup, sans secrets."""
    import json
    from forgeai.cli import main

    home = tmp_path / "home"
    home.mkdir()
    (home / "gateway.json").write_text(
        '{"base_url": "http://localhost:4000", "key_env": "FORGEAI_GATEWAY_KEY"}',
        encoding="utf-8")
    (home / "strategy.json").write_text('{"strategy": "equipe"}', encoding="utf-8")
    (home / "vault.json").write_text('{"chiffre": "NE-DOIT-PAS-SORTIR"}', encoding="utf-8")
    reg = tmp_path / "r.jsonl"
    bundle = tmp_path / "bundle.json"

    assert main(["export", "--home", str(home), "--out", str(bundle),
                 "--registre", str(reg)]) == 0
    assert bundle.exists()

    target = tmp_path / "target"
    assert main(["import", "--bundle", str(bundle), "--home", str(target),
                 "--registre", str(reg)]) == 0
    assert json.loads((target / "gateway.json").read_text(encoding="utf-8")) == \
        json.loads((home / "gateway.json").read_text(encoding="utf-8"))
    assert not (target / "vault.json").exists()   # secrets jamais transportés


def test_verify_refuse_vault_json_dans_bundle_forge():
    """Bundle forgé contenant vault.json AVEC hash recalculé → rejeté (fail-closed).
    Prouve que le hash seul ne suffit pas : la liste blanche de noms protège l'import."""
    files = {"vault.json": {"secret": "x"}}
    forged = {"version": 1, "created_at": "2025-01-01", "files": files,
              "sha256": bundle_sha256(files, "2025-01-01")}
    with pytest.raises(PortabilityError, match="non autoris"):
        verify_bundle(forged)


def test_verify_refuse_chemin_traversal():
    """Noms de fichiers avec '..', séparateur ou chemin absolu → rejetés à la vérification."""
    for danger in ("../evil.json", "/etc/passwd", "sub/dir.json"):
        files = {danger: {"x": 1}}
        forged = {"version": 1, "created_at": "2025-01-01", "files": files,
                  "sha256": bundle_sha256(files, "2025-01-01")}
        with pytest.raises(PortabilityError, match="non autoris"):
            verify_bundle(forged)


def test_import_ne_restaure_pas_fichier_hors_whitelist(tmp_path):
    """import_setup (défense en profondeur) n'écrit jamais un nom hors whitelist, même si
    verify_bundle était contourné : ici on teste le round-trip sain (aucun fichier surprise)."""
    src = tmp_path / "src"
    _write_json(src / "gateway.json", GATEWAY)
    bundle_path = tmp_path / "b.json"
    export_setup(str(src), out_path=str(bundle_path))
    tgt = tmp_path / "tgt"
    report = import_setup(str(bundle_path), str(tgt))
    assert report["restored"] == ["gateway.json"]
    assert not (tgt / "vault.json").exists()


class TestValidateRouteChampsInconnus:
    def test_champ_inconnu_refuse(self, tmp_path: Path):
        home = tmp_path / "source"
        route_extra = {**ROUTE_TEMPLATE, "champ_surprise": "x"}
        _write_json(home / "routes.json", [route_extra])
        with pytest.raises(PortabilityError, match="non autorisés"):
            export_setup(str(home))


class TestExportFichierCorrompu:
    def test_json_illisible_leve_portability_error(self, tmp_path: Path):
        home = tmp_path / "source"
        home.mkdir()
        (home / "routes.json").write_text("{ceci n'est pas du json", encoding="utf-8")
        with pytest.raises(PortabilityError, match="Erreur lors du chargement"):
            export_setup(str(home))


class TestExportRoutesJsonMalForme:
    def test_routes_json_pas_une_liste(self, tmp_path: Path):
        home = tmp_path / "source"
        _write_json(home / "routes.json", {"pas": "une liste"})
        with pytest.raises(PortabilityError, match="doit être une liste"):
            export_setup(str(home))

    def test_route_pas_un_dict(self, tmp_path: Path):
        home = tmp_path / "source"
        _write_json(home / "routes.json", ["pas-un-dict"])
        with pytest.raises(PortabilityError, match="doit être un dict"):
            export_setup(str(home))


class TestExportFichierExcluDefenseEnProfondeur:
    def test_fichier_exclu_refuse_meme_si_dans_setup_files(self, tmp_path, monkeypatch):
        """SETUP_FILES/EXCLUDED_FILES n'ont aujourd'hui aucune intersection (vault.json
        n'est jamais itéré) — cette garde protège contre une dérive future de ces
        constantes. On la teste directement en simulant cette dérive."""
        import forgeai.portability as portability_mod

        home = tmp_path / "source"
        _write_json(home / "vault.json", {"secret": "x"})
        monkeypatch.setattr(portability_mod, "SETUP_FILES", ("vault.json",))
        with pytest.raises(PortabilityError, match="ne doit jamais être exporté"):
            export_setup(str(home))


class TestExportErreurEcriture:
    def test_ecriture_echoue_si_parent_est_un_fichier(self, tmp_path: Path):
        home = tmp_path / "source"
        _write_json(home / "gateway.json", GATEWAY)
        blocker = tmp_path / "blocker"
        blocker.write_text("je ne suis pas un dossier", encoding="utf-8")
        out_path = blocker / "bundle.json"
        with pytest.raises(PortabilityError, match="Erreur lors de l'écriture"):
            export_setup(str(home), out_path=str(out_path))


class TestVerifyVersionIncompatible:
    def test_version_future_refusee(self):
        files = {"gateway.json": GATEWAY}
        forged = {"version": 999, "created_at": "2025-01-01", "files": files,
                  "sha256": bundle_sha256(files, "2025-01-01")}
        with pytest.raises(PortabilityError, match="incompatible"):
            verify_bundle(forged)


class TestImportFilesMappingInvalide:
    def test_files_liste_au_lieu_de_dict(self, tmp_path: Path):
        """verify_bundle accepte 'files' tant que c'est un ITÉRABLE de noms autorisés (une
        liste de noms valides le satisfait) ; import_setup, lui, exige un vrai dict — la
        garde de type est plus stricte à ce niveau, et c'est elle qu'on teste ici."""
        files = ["gateway.json"]
        created_at = "2025-01-01"
        bundle_path = tmp_path / "b.json"
        _write_json(bundle_path, {
            "version": 1, "created_at": created_at, "files": files,
            "sha256": bundle_sha256(files, created_at),
        })
        with pytest.raises(PortabilityError, match="mapping"):
            import_setup(str(bundle_path), str(tmp_path / "target"))
