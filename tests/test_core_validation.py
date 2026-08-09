"""Tests pour src/forgeai/core/validation.py."""
import os
from pathlib import Path

import pytest

from forgeai.core.validation import (
    ValidationError,
    resolve_within,
    valider_nom_simple,
)


# --- valider_nom_simple ---


def test_valider_nom_simple_valide():
    assert valider_nom_simple("abc") is None
    assert valider_nom_simple("a-b") is None
    assert valider_nom_simple("a.b") is None
    assert valider_nom_simple("x") is None


def test_valider_nom_simple_slash():
    with pytest.raises(ValidationError):
        valider_nom_simple("a/b")


def test_valider_nom_simple_double_point():
    with pytest.raises(ValidationError):
        valider_nom_simple("..")


def test_valider_nom_simple_double_point_inclus():
    # "a..b" contient ".." donc rejeté par le prédicat `".." in name`.
    with pytest.raises(ValidationError):
        valider_nom_simple("a..b")


def test_valider_nom_simple_vide():
    with pytest.raises(ValidationError):
        valider_nom_simple("")


def test_valider_nom_simple_point():
    with pytest.raises(ValidationError):
        valider_nom_simple(".")


# --- resolve_within ---


def test_resolve_within_absolu_dans_racine(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    cible = root / "file"
    cible.write_text("x")
    result = resolve_within(cible, root)
    assert result == Path(os.path.realpath(cible))


def test_resolve_within_racine_ellememe(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    result = resolve_within(root, root)
    assert result == Path(os.path.realpath(root))


def test_resolve_within_relatif_avec_base(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    cible = root / "file"
    cible.write_text("x")
    result = resolve_within("file", root, base=root)
    assert result == Path(os.path.realpath(cible))


def test_resolve_within_double_point_sortant(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    cible = root / ".." / "other"
    with pytest.raises(ValidationError):
        resolve_within(cible, root)


def test_resolve_within_double_point_interne(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    cible = root / "a" / ".." / "b"
    result = resolve_within(cible, root)
    assert result == Path(os.path.realpath(root / "b"))


def test_resolve_within_symlink_sortant(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    dehors = tmp_path / "dehors"
    dehors.mkdir()
    lien = root / "lien"
    os.symlink(dehors, lien)
    with pytest.raises(ValidationError):
        resolve_within(lien, root)


def test_resolve_within_symlink_entrant(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    cible = root / "file"
    cible.write_text("x")
    lien_racine = tmp_path / "lien_racine"
    os.symlink(root, lien_racine)
    result = resolve_within(lien_racine / "file", lien_racine)
    assert result == Path(os.path.realpath(cible))


def test_resolve_within_cible_inexistante_dans_racine(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    cible = root / "future"
    result = resolve_within(cible, root)
    assert result == Path(os.path.realpath(cible))


def test_resolve_within_cible_inexistante_hors_racine(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    cible = tmp_path / "future"
    with pytest.raises(ValidationError):
        resolve_within(cible, root)


def test_resolve_within_message_erreur(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    cible = tmp_path / "dehors"
    with pytest.raises(ValidationError) as exc_info:
        resolve_within(cible, root)
    msg = str(exc_info.value)
    assert os.path.realpath(str(cible)) in msg
    assert os.path.realpath(str(root)) in msg


def test_resolve_within_rejette_repertoire_frere_prefixe_commun(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    repo_evil = tmp_path / "repo-evil"
    repo_evil.mkdir()
    cible_evil = repo_evil / "x.txt"
    cible_evil.write_text("x")
    with pytest.raises(ValidationError):
        resolve_within(cible_evil, repo)
    cible_ok = repo / "x.txt"
    cible_ok.write_text("x")
    result = resolve_within(cible_ok, repo)
    assert result == Path(os.path.realpath(cible_ok))


# --- valider_schema_url (CAND-001 : aucun controle de schema sur les 9 sites
# urlopen du produit — file:// permettait de lire un fichier local arbitraire) ---


def test_valider_schema_url_https_accepte():
    from forgeai.core.validation import valider_schema_url
    assert valider_schema_url("https://api.exemple.com/v1") is None


def test_valider_schema_url_http_accepte():
    from forgeai.core.validation import valider_schema_url
    assert valider_schema_url("http://127.0.0.1:11434/api") is None


def test_valider_schema_url_file_refuse():
    from forgeai.core.validation import valider_schema_url
    with pytest.raises(ValidationError):
        valider_schema_url("file:///etc/passwd")


def test_valider_schema_url_sans_schema_refuse():
    from forgeai.core.validation import valider_schema_url
    with pytest.raises(ValidationError):
        valider_schema_url("etc/passwd")


def test_valider_schema_url_ftp_refuse():
    from forgeai.core.validation import valider_schema_url
    with pytest.raises(ValidationError):
        valider_schema_url("ftp://exemple.com/fichier")


def test_valider_schema_url_data_refuse():
    with pytest.raises(pytest.importorskip("forgeai.core.validation").ValidationError):
        pytest.importorskip("forgeai.core.validation").valider_schema_url("data:text/plain;base64,eA==")


def test_valider_schema_url_message_erreur_nomme_le_schema():
    from forgeai.core.validation import valider_schema_url
    with pytest.raises(ValidationError) as exc_info:
        valider_schema_url("file:///secret.txt")
    assert "file" in str(exc_info.value)


def test_download_verified_refuse_file_scheme_sur_le_chemin_public(tmp_path):
    """REPRODUCTION EXACTE de CAND-001 : download_verified() est le point
    d'entree public reel (cli.py -> LocalModel.download_url -> ici). Avant
    le fix, un `download_url="file:///secret"` lisait le fichier local et
    l'ecrivait dans la destination — reproduit dans l'audit v7.1 sur pc4."""
    import hashlib
    from forgeai.models.local import LocalModel, UrllibFetcher, download_verified

    fichier_prive = tmp_path / "hors-perimetre.txt"
    fichier_prive.write_bytes(b"CONTENU QUI NE DOIT JAMAIS ETRE LU PAR UN TELECHARGEMENT\n")
    empreinte = hashlib.sha256(fichier_prive.read_bytes()).hexdigest()
    dest = tmp_path / "dest"; dest.mkdir()
    modele = LocalModel(name="modele-piege", engine="llamacpp", model_ref="x",
                        vram_required_mb=0, download_url="file://%s" % fichier_prive,
                        sha256=empreinte)
    with pytest.raises(ValidationError):
        download_verified(modele, dest, UrllibFetcher())
    assert not (dest / "modele-piege.bin").exists(), \
        "le fichier local a ete lu et ecrit malgre le schema file://"
