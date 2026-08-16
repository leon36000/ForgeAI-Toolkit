import importlib.util
import pathlib

_MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "governance" / "check_doc_links.py"
_spec = importlib.util.spec_from_file_location("check_doc_links", _MODULE_PATH)
check_doc_links = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_doc_links)

REPO = pathlib.Path(__file__).resolve().parents[1]
_SCAN_GLOBS = [
    "Docs/**/*.md",
    "governance/**/*.md",
    "README.md",
    "AGENTS.md",
    "CLAUDE.md",
    "MASTER-PLAN.md",
    "CANON/**/*.md",
]


def test_extrait_lien_markdown():
    assert check_doc_links.extract_links("[texte](reference/cli.md)") == [
        ("reference/cli.md", 1)
    ]


def test_extrait_chemin_entre_backticks():
    liens = check_doc_links.extract_links(
        "voir `Docs/reference/cli.md` pour details"
    )

    assert ("Docs/reference/cli.md", 1) in liens


def test_ignore_url_externe():
    assert check_doc_links.extract_links("[site](https://example.com/x.md)") == []


def test_ignore_ancre_pure():
    assert check_doc_links.extract_links("[section](#introduction)") == []


def test_numero_de_ligne_correct():
    liens = check_doc_links.extract_links(
        "premiere ligne\n"
        "deuxieme ligne\n"
        "[texte](reference/cli.md)"
    )

    assert liens == [("reference/cli.md", 3)]


def test_resout_lien_relatif_au_referent():
    assert (
        check_doc_links.resolve_link("reference/cli.md", "Docs/README.md")
        == "Docs/reference/cli.md"
    )


def test_resout_lien_deja_absolu():
    assert (
        check_doc_links.resolve_link("governance/authority.json", "README.md")
        == "governance/authority.json"
    )


def test_resout_lien_avec_parent_relatif():
    assert (
        check_doc_links.resolve_link("../AGENTS.md", "Docs/how-to/x.md")
        == "AGENTS.md"
    )


def test_check_links_detecte_un_lien_mort():
    liens_morts = check_doc_links.check_links(
        paths=["a.md"],
        contents={"a.md": "[x](b/nexiste.md)"},
        known_paths={"a.md"},
    )

    assert len(liens_morts) == 1
    assert liens_morts[0]["resolved"] == "b/nexiste.md"


def test_check_links_lien_valide_absent_du_resultat():
    liens_morts = check_doc_links.check_links(
        paths=["a.md"],
        contents={"a.md": "[x](b/nexiste.md)"},
        known_paths={"a.md", "b/nexiste.md"},
    )

    assert liens_morts == []


def test_check_links_lien_non_resolvable_ignore():
    liens_morts = check_doc_links.check_links(
        paths=["a.md"],
        contents={"a.md": "[x](${var})"},
        known_paths={"a.md"},
    )

    assert liens_morts == []


def test_scan_repo_reel_detecte_les_references_mortes_connues():
    liens_morts = check_doc_links.scan_repo(REPO, _SCAN_GLOBS)

    # Lien mort réel et actuel, T3 (CANON/ réservé à Nathan) : correction hors périmètre de #509,
    # documentée en attente d'approbation T3. Ce test sera corrigé quand ce lien le sera.
    assert any(
        lien["referrer"] == "CANON/ETAT-SYSTEME.md"
        and lien["link"] == "Registres/mission.jsonl"
        for lien in liens_morts
    )


def test_scan_repo_reel_aucune_exception():
    liens_morts = check_doc_links.scan_repo(REPO, _SCAN_GLOBS)

    assert isinstance(liens_morts, list)


def test_main_retourne_1_avec_liens_morts_connus():
    assert check_doc_links.main(["--repo-root", str(REPO)]) == 1
