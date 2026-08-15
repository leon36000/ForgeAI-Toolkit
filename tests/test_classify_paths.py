import importlib.util
import pathlib
import unicodedata

_MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "governance" / "classify_paths.py"
_spec = importlib.util.spec_from_file_location("classify_paths", _MODULE_PATH)
classify_paths = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(classify_paths)


def test_collision_casse_docs_majuscule_minuscule() -> None:
    paths = ["Docs/a.md", "docs/a.md"]

    collisions = classify_paths.detect_collisions(paths)

    assert len(collisions["case"]) == 1
    assert set(collisions["case"][0]["paths"]) == set(paths)
    assert collisions["case"][0]["description"]


def test_collision_unicode_precompose_vs_decompose() -> None:
    precompose = "docs/café.md"
    decompose = "docs/cafe\u0301.md"

    collisions = classify_paths.detect_collisions([precompose, decompose])

    assert collisions["case"] == []
    assert len(collisions["unicode"]) >= 1
    assert any(
        {precompose, decompose}.issubset(set(entry["paths"]))
        and entry["description"]
        for entry in collisions["unicode"]
    )


def test_anomalie_normalisation_nfc_signalee() -> None:
    path = "docs/cafe\u0301.md"

    collisions = classify_paths.detect_collisions([path])

    assert unicodedata.normalize("NFC", path) != path
    assert any(
        entry["kind"] == "non_nfc"
        and path in entry["paths"]
        and entry["description"]
        for entry in collisions["unicode"]
    )


def test_caractere_invisible_rejete() -> None:
    violations = classify_paths.check_portability("docs/a\u200bb.md")

    assert any(
        violation["rule"] == "invisible_character"
        and violation["segment"] == "a\u200bb.md"
        and violation["detail"]
        for violation in violations
    )


def test_aucune_collision_sur_ensemble_sans_probleme() -> None:
    collisions = classify_paths.detect_collisions(["a/b.py", "a/c.py", "d/e.md"])

    assert collisions == {"case": [], "unicode": [], "portability": []}


def test_collision_cible_contre_chemin_non_deplace() -> None:
    paths = ["a/x.md", "b/y.md"]
    targets = {"a/x.md": "b/Y.md"}

    collisions = classify_paths.detect_collisions(paths, targets)

    assert any(
        {"b/Y.md", "b/y.md"}.issubset(set(entry["paths"]))
        and entry["description"]
        for entry in collisions["case"]
    )


def test_caractere_interdit_windows_deux_points() -> None:
    violations = classify_paths.check_portability("a:b.md")

    assert any(
        violation["rule"] == "windows_forbidden_character"
        and violation["segment"] == "a:b.md"
        and violation["detail"]
        for violation in violations
    )


def test_nom_reserve_windows_aux() -> None:
    lower_violations = classify_paths.check_portability("aux.md")
    upper_violations = classify_paths.check_portability("AUX.TXT")

    assert any(
        violation["rule"] == "windows_reserved_name"
        and violation["segment"] == "aux.md"
        for violation in lower_violations
    )
    assert any(
        violation["rule"] == "windows_reserved_name"
        and violation["segment"] == "AUX.TXT"
        for violation in upper_violations
    )


def test_nom_reserve_windows_com1() -> None:
    violations = classify_paths.check_portability("COM1.txt")

    assert any(
        violation["rule"] == "windows_reserved_name"
        and violation["segment"] == "COM1.txt"
        and violation["detail"]
        for violation in violations
    )


def test_segment_termine_par_point_ou_espace() -> None:
    point_violations = classify_paths.check_portability("dossier./f.md")
    espace_violations = classify_paths.check_portability("dossier /f.md")

    assert any(
        violation["rule"] == "windows_trailing_dot_or_space"
        and violation["segment"] == "dossier."
        for violation in point_violations
    )
    assert any(
        violation["rule"] == "windows_trailing_dot_or_space"
        and violation["segment"] == "dossier "
        for violation in espace_violations
    )


def test_segment_dotgit_interdit() -> None:
    violations = classify_paths.check_portability("archives/.git/config")

    assert any(
        violation["rule"] == "reserved_git_segment"
        and violation["segment"] == ".git"
        and violation["detail"]
        for violation in violations
    )


def test_chemin_legal_aucune_violation() -> None:
    violations = classify_paths.check_portability("src/forgeai/core/models.py")

    assert violations == []


def test_chemin_trop_long_echoue() -> None:
    path = "a" * 245

    violations = classify_paths.check_portability(path)

    assert any(
        violation["rule"] == "path_length"
        and violation["severity"] == "error"
        and violation["detail"]
        for violation in violations
    )


def test_chemin_longueur_avertissement() -> None:
    # La plage préventive autour de 205 caractères est un avertissement, distinct
    # de l'erreur bloquante appliquée aux chemins de 245 caractères et plus.
    path = "a" * 205

    violations = classify_paths.check_portability(path)

    assert any(
        violation["rule"] == "path_length"
        and violation["severity"] == "warning"
        and violation["detail"]
        for violation in violations
    )
