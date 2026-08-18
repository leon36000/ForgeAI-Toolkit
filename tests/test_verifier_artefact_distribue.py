from __future__ import annotations

import io
import re
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import verifier_artefact_distribue as vad  # noqa: E402


def _metadonnees_conformes() -> bytes:
    """Metadonnees RFC822 conformes aux constantes attendues du verifieur."""
    lignes = [
        "Metadata-Version: 2.1",
        "Name: forgeai-toolkit",
        "Version: 0.1.0",
        "Requires-Python: >=3.10",
        "Classifier: Programming Language :: Python :: 3.10",
        "Classifier: Programming Language :: Python :: 3.11",
        "Classifier: Programming Language :: Python :: 3.12",
        "Classifier: Programming Language :: Python :: 3.13",
        "",
        "Description factice du paquet.",
    ]
    return "\n".join(lignes).encode("utf-8")


def _chemins_complets() -> list[str]:
    """Jeu de chemins forgeai/ satisfaisant tous les minimums de package-data.

    4 locales + 8 stacks + 1 catalogue + 4 extra = 17 JSON (>= 16 requis) ;
    5 assets ; 2 smoke. Chaque categorie depasse son minimum afin que les tests
    d'echec puissent isoler une seule cause a la fois.
    """
    chemins = ["forgeai/__init__.py", "forgeai/cli.py"]
    chemins += [f"forgeai/data/locales/{code}.json" for code in ("fr", "en", "es", "de")]
    chemins += [f"forgeai/data/stacks/stack_{i}.json" for i in range(8)]
    chemins += [f"forgeai/web/assets/asset_{i}.txt" for i in range(5)]
    chemins += ["forgeai/data/smoke/scenario_a.md", "forgeai/data/smoke/scenario_b.md"]
    chemins.append("forgeai/data/catalogue.json")
    chemins += [f"forgeai/data/extra/extra_{i}.json" for i in range(4)]
    return chemins


def _membres_wheel_valides() -> dict[str, bytes]:
    """Membres d'un wheel factice complet et conforme (un seul METADATA)."""
    membres = {chemin: b"# contenu factice\n" for chemin in _chemins_complets()}
    membres["forgeai_toolkit-0.1.0.dist-info/METADATA"] = _metadonnees_conformes()
    return membres


def _membres_sdist_valides() -> dict[str, bytes]:
    """Membres d'un sdist factice complet et conforme (PKG-INFO racine + tests/)."""
    membres = {
        f"forgeai_toolkit-0.1.0/src/{chemin}": b"# contenu factice\n"
        for chemin in _chemins_complets()
    }
    membres["forgeai_toolkit-0.1.0/PKG-INFO"] = _metadonnees_conformes()
    membres["forgeai_toolkit-0.1.0/tests/test_cli.py"] = b"# tests factices\n"
    return membres


def _ecrire_wheel(chemin: Path, membres: dict[str, bytes]) -> Path:
    """Ecrit une archive zip (wheel factice) contenant `membres` et la retourne."""
    with zipfile.ZipFile(chemin, "w") as archive:
        for nom, contenu in membres.items():
            archive.writestr(nom, contenu)
    return chemin


def _ecrire_sdist(chemin: Path, membres: dict[str, bytes]) -> Path:
    """Ecrit une archive tar.gz (sdist factice) contenant `membres` et la retourne."""
    with tarfile.open(chemin, "w:gz") as archive:
        for nom, contenu in membres.items():
            info = tarfile.TarInfo(nom)
            info.size = len(contenu)
            archive.addfile(info, io.BytesIO(contenu))
    return chemin


# ---------------------------------------------------------------------------
# _nom_membre_sur
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "nom",
    [
        "forgeai/cli.py",
        "forgeai_toolkit-0.1.0/PKG-INFO",
        "a/b/c/d.txt",
        "a/..b/c.txt",
        "forgeai\\data\\catalogue.json",
    ],
)
def test_nom_membre_sur_accepte_les_noms_relatifs(nom: str) -> None:
    """Un nom relatif non vide sans segment exactement « .. » est sur.

    « ..b » n'est PAS une remontee de repertoire (segment different de « .. ») ;
    les separateurs Windows sont normalises avant controle.
    """
    assert vad._nom_membre_sur(nom) is True


@pytest.mark.parametrize(
    "nom",
    [
        "",
        "/etc/passwd",
        "../evil",
        "a/../b",
        "a/../../b",
        "..\\evil",
        "\\\\serveur\\partage",
    ],
)
def test_nom_membre_sur_rejette_les_noms_dangereux(nom: str) -> None:
    """Nom vide, absolu (y compris apres normalisation Windows) ou contenant une
    remontee « .. » : rejete."""
    assert vad._nom_membre_sur(nom) is False


# ---------------------------------------------------------------------------
# _membres_wheel
# ---------------------------------------------------------------------------

def test_membres_wheel_valide_retourne_noms_contenus_et_metadata(tmp_path: Path) -> None:
    """Un wheel bien forme retourne le triplet (noms, contenus, METADATA)."""
    chemin = _ecrire_wheel(
        tmp_path / "forgeai_toolkit-0.1.0-py3-none-any.whl", _membres_wheel_valides()
    )

    noms, contenus, metadata = vad._membres_wheel(chemin)

    assert "forgeai_toolkit-0.1.0.dist-info/METADATA" in noms
    assert "forgeai/cli.py" in noms
    assert set(contenus) == set(noms)
    assert contenus["forgeai/cli.py"] == b"# contenu factice\n"
    assert metadata == _metadonnees_conformes()


def test_membres_wheel_sans_metadata_leve(tmp_path: Path) -> None:
    """Aucun fichier *.dist-info/METADATA : ErreurVerification explicite."""
    chemin = _ecrire_wheel(tmp_path / "sans_metadata.whl", {"forgeai/cli.py": b"x"})

    with pytest.raises(vad.ErreurVerification, match="METADATA wheel introuvable ou ambigu"):
        vad._membres_wheel(chemin)


def test_membres_wheel_metadata_ambigue_leve(tmp_path: Path) -> None:
    """Deux fichiers *.dist-info/METADATA : ambiguite refusee."""
    membres = {
        "forgeai_toolkit-0.1.0.dist-info/METADATA": _metadonnees_conformes(),
        "autre-2.0.dist-info/METADATA": _metadonnees_conformes(),
        "forgeai/cli.py": b"x",
    }
    chemin = _ecrire_wheel(tmp_path / "ambigu.whl", membres)

    with pytest.raises(vad.ErreurVerification, match="METADATA wheel introuvable ou ambigu"):
        vad._membres_wheel(chemin)


def test_membres_wheel_zip_corrompu_leve(tmp_path: Path) -> None:
    """Un fichier .whl qui n'est pas une archive zip valide est rejete proprement."""
    chemin = tmp_path / "corrompu.whl"
    chemin.write_bytes(b"ceci n'est pas une archive zip valide")

    with pytest.raises(vad.ErreurVerification, match="wheel illisible"):
        vad._membres_wheel(chemin)


# ---------------------------------------------------------------------------
# _membres_sdist
# ---------------------------------------------------------------------------

def test_membres_sdist_valide_retourne_noms_contenus_et_pkginfo(tmp_path: Path) -> None:
    """Un sdist bien forme retourne le triplet (noms, contenus, PKG-INFO)."""
    chemin = _ecrire_sdist(tmp_path / "forgeai_toolkit-0.1.0.tar.gz", _membres_sdist_valides())

    noms, contenus, pkginfo = vad._membres_sdist(chemin)

    assert "forgeai_toolkit-0.1.0/PKG-INFO" in noms
    assert "forgeai_toolkit-0.1.0/tests/test_cli.py" in noms
    assert set(contenus) == set(noms)
    assert contenus["forgeai_toolkit-0.1.0/src/forgeai/cli.py"] == b"# contenu factice\n"
    assert pkginfo == _metadonnees_conformes()


def test_membres_sdist_sans_pkginfo_leve(tmp_path: Path) -> None:
    """Aucun PKG-INFO a la racine de l'archive : ErreurVerification explicite."""
    chemin = _ecrire_sdist(
        tmp_path / "sans_pkginfo.tar.gz",
        {"forgeai_toolkit-0.1.0/src/forgeai/cli.py": b"x"},
    )

    with pytest.raises(vad.ErreurVerification, match="PKG-INFO sdist introuvable ou ambigu"):
        vad._membres_sdist(chemin)


@pytest.mark.parametrize(
    "nom_pkginfo",
    ["PKG-INFO", "forgeai_toolkit-0.1.0/docs/PKG-INFO"],
)
def test_membres_sdist_pkginfo_profondeur_incorrecte_leve(
    tmp_path: Path, nom_pkginfo: str
) -> None:
    """Un PKG-INFO a une profondeur differente de 1 (racine nue ou trop profond)
    n'est pas reconnu : l'archive est rejetee."""
    membres = {
        "forgeai_toolkit-0.1.0/src/forgeai/cli.py": b"x",
        nom_pkginfo: _metadonnees_conformes(),
    }
    chemin = _ecrire_sdist(tmp_path / "profondeur.tar.gz", membres)

    with pytest.raises(vad.ErreurVerification, match="PKG-INFO sdist introuvable ou ambigu"):
        vad._membres_sdist(chemin)


def test_membres_sdist_pkginfo_ambigu_leve(tmp_path: Path) -> None:
    """Deux PKG-INFO a profondeur 1 : ambiguite refusee."""
    membres = {
        "paquet_a-1.0/PKG-INFO": _metadonnees_conformes(),
        "paquet_b-2.0/PKG-INFO": _metadonnees_conformes(),
        "paquet_a-1.0/src/forgeai/cli.py": b"x",
    }
    chemin = _ecrire_sdist(tmp_path / "ambigu.tar.gz", membres)

    with pytest.raises(vad.ErreurVerification, match="PKG-INFO sdist introuvable ou ambigu"):
        vad._membres_sdist(chemin)


def test_membres_sdist_tar_corrompu_leve(tmp_path: Path) -> None:
    """Un fichier .tar.gz qui n'est pas une archive tar gzip valide est rejete."""
    chemin = tmp_path / "corrompu.tar.gz"
    chemin.write_bytes(b"ceci n'est pas une archive tar gzip valide")

    with pytest.raises(vad.ErreurVerification, match="sdist illisible"):
        vad._membres_sdist(chemin)


@pytest.mark.parametrize("nom_dangereux", ["../evil", "/etc/passwd", "a/../../b"])
def test_membres_sdist_nom_membre_non_sur_leve(
    tmp_path: Path, nom_dangereux: str
) -> None:
    """Un sdist portant UN SEUL nom dangereux (absolu ou remontee « .. ») est
    integralement rejete, avec le nom fautif cite dans le message — meme si le
    reste de l'archive est parfaitement conforme."""
    membres = _membres_sdist_valides()
    membres[nom_dangereux] = b"contenu malveillant"
    chemin = _ecrire_sdist(tmp_path / "malveillant.tar.gz", membres)

    with pytest.raises(
        vad.ErreurVerification, match=re.escape(nom_dangereux)
    ):
        vad._membres_sdist(chemin)


def test_membres_sdist_plusieurs_noms_non_surs_tous_listes(tmp_path: Path) -> None:
    """Tous les noms dangereux sont enumeres dans le message de rejet."""
    membres = _membres_sdist_valides()
    membres["../evil"] = b"x"
    membres["/etc/passwd"] = b"y"
    chemin = _ecrire_sdist(tmp_path / "malveillant.tar.gz", membres)

    with pytest.raises(vad.ErreurVerification, match="non sûr") as excinfo:
        vad._membres_sdist(chemin)

    message = str(excinfo.value)
    assert "../evil" in message
    assert "/etc/passwd" in message


def test_membres_sdist_membre_non_sur_rejete_avant_toute_lecture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La validation des noms precede TOUTE lecture de contenu : extractfile ne
    doit jamais etre appele quand un membre est dangereux."""
    membres = _membres_sdist_valides()
    membres["../evil"] = b"contenu malveillant"
    chemin = _ecrire_sdist(tmp_path / "malveillant.tar.gz", membres)

    lectures: list[str] = []
    originale = tarfile.TarFile.extractfile

    def espion(self: tarfile.TarFile, member: object) -> object:
        lectures.append(getattr(member, "name", str(member)))
        return originale(self, member)

    monkeypatch.setattr(tarfile.TarFile, "extractfile", espion)

    with pytest.raises(vad.ErreurVerification, match="non sûr"):
        vad._membres_sdist(chemin)

    assert lectures == []


# ---------------------------------------------------------------------------
# _chemins_paquet
# ---------------------------------------------------------------------------

def test_chemins_paquet_extrait_depuis_racine_sdist() -> None:
    """Les chemins sont ramenes a leur racine forgeai/ depuis un layout de sdist."""
    noms = {
        "forgeai_toolkit-0.1.0/src/forgeai/cli.py",
        "forgeai_toolkit-0.1.0/src/forgeai/data/catalogue.json",
    }

    assert vad._chemins_paquet(noms) == {
        "forgeai/cli.py",
        "forgeai/data/catalogue.json",
    }


def test_chemins_paquet_gere_les_separateurs_windows() -> None:
    """Les separateurs « \\ » sont normalises en « / » avant extraction."""
    noms = {"forgeai_toolkit-0.1.0\\src\\forgeai\\cli.py"}

    assert vad._chemins_paquet(noms) == {"forgeai/cli.py"}


def test_chemins_paquet_ignore_les_noms_sans_forgeai() -> None:
    """Les noms ne contenant pas « forgeai/ » sont ignores (PKG-INFO, tests, etc.)."""
    noms = {
        "forgeai_toolkit-0.1.0/PKG-INFO",
        "forgeai_toolkit-0.1.0/tests/test_cli.py",
        "README.md",
    }

    assert vad._chemins_paquet(noms) == set()


# ---------------------------------------------------------------------------
# _verifier_metadonnees
# ---------------------------------------------------------------------------

def test_verifier_metadonnees_conformes_passent(tmp_path: Path) -> None:
    """Des metadonnees conformes a toutes les constantes attendues passent."""
    assert (
        vad._verifier_metadonnees(tmp_path / "a.whl", _metadonnees_conformes()) is None
    )


def test_verifier_metadonnees_nom_incorrect_leve(tmp_path: Path) -> None:
    """Un champ Name different de « forgeai-toolkit » est refuse."""
    contenu = _metadonnees_conformes().replace(
        b"Name: forgeai-toolkit", b"Name: autre-paquet"
    )

    with pytest.raises(vad.ErreurVerification, match="nom de paquet attendu"):
        vad._verifier_metadonnees(tmp_path / "a.whl", contenu)


def test_verifier_metadonnees_version_incorrecte_leve(tmp_path: Path) -> None:
    """Un champ Version different de « 0.1.0 » est refuse."""
    contenu = _metadonnees_conformes().replace(b"Version: 0.1.0", b"Version: 9.9.9")

    with pytest.raises(vad.ErreurVerification, match="version attendue"):
        vad._verifier_metadonnees(tmp_path / "a.whl", contenu)


def test_verifier_metadonnees_requires_python_incorrect_leve(tmp_path: Path) -> None:
    """Un champ Requires-Python different de « >=3.10 » est refuse."""
    contenu = _metadonnees_conformes().replace(
        b"Requires-Python: >=3.10", b"Requires-Python: >=3.8"
    )

    with pytest.raises(vad.ErreurVerification, match="Requires-Python attendu"):
        vad._verifier_metadonnees(tmp_path / "a.whl", contenu)


def test_verifier_metadonnees_classifier_manquant_leve(tmp_path: Path) -> None:
    """Un classifier Python attendu absent (ici 3.13) est signale explicitement."""
    contenu = _metadonnees_conformes().replace(
        b"Classifier: Programming Language :: Python :: 3.13\n", b""
    )

    with pytest.raises(
        vad.ErreurVerification, match="classifiers Python manquants"
    ) as excinfo:
        vad._verifier_metadonnees(tmp_path / "a.whl", contenu)

    assert "Programming Language :: Python :: 3.13" in str(excinfo.value)


def test_verifier_metadonnees_contenu_illisible_leve(tmp_path: Path) -> None:
    """Un contenu non analysable en message RFC822 declenche la branche defensive
    « metadonnees illisibles » (ici un str la ou le parseur attend des bytes)."""
    with pytest.raises(vad.ErreurVerification, match="métadonnées illisibles"):
        vad._verifier_metadonnees(tmp_path / "a.whl", "contenu non binaire")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# _compter
# ---------------------------------------------------------------------------

def test_compter_avec_prefixe_seul() -> None:
    """Sans suffixe, tous les chemins sous le prefixe sont comptes."""
    chemins = {
        "forgeai/web/assets/a.txt",
        "forgeai/web/assets/b.css",
        "forgeai/cli.py",
    }

    assert vad._compter(chemins, "forgeai/web/assets/") == 2


def test_compter_avec_prefixe_et_suffixe() -> None:
    """Prefixe ET suffixe : seuls les chemins satisfaisant les deux comptent."""
    chemins = {
        "forgeai/data/locales/fr.json",
        "forgeai/data/locales/lisezmoi.md",
        "forgeai/cli.py",
    }

    assert vad._compter(chemins, "forgeai/data/locales/", ".json") == 1


def test_compter_sans_correspondance_retourne_zero() -> None:
    """Aucun chemin sous le prefixe : 0."""
    assert vad._compter({"forgeai/cli.py"}, "forgeai/data/stacks/", ".json") == 0


# ---------------------------------------------------------------------------
# _verifier_package_data
# ---------------------------------------------------------------------------

def test_verifier_package_data_complet_passe(tmp_path: Path) -> None:
    """Un jeu de chemins satisfaisant tous les minimums passe sans erreur."""
    assert (
        vad._verifier_package_data(tmp_path / "a.whl", set(_chemins_complets())) is None
    )


def test_verifier_package_data_locales_sous_le_minimum_leve(tmp_path: Path) -> None:
    """Moins de 2 locales : rejete, meme si le total JSON reste suffisant."""
    chemins = set(_chemins_complets())
    chemins -= {
        "forgeai/data/locales/en.json",
        "forgeai/data/locales/es.json",
        "forgeai/data/locales/de.json",
    }
    chemins |= {f"forgeai/data/extra/compensation_{i}.json" for i in range(3)}

    with pytest.raises(vad.ErreurVerification, match="locales"):
        vad._verifier_package_data(tmp_path / "a.whl", chemins)


def test_verifier_package_data_stacks_sous_le_minimum_leve(tmp_path: Path) -> None:
    """Moins de 6 stacks : rejete, meme si le total JSON reste suffisant."""
    chemins = set(_chemins_complets())
    chemins -= {f"forgeai/data/stacks/stack_{i}.json" for i in (5, 6, 7)}
    chemins |= {f"forgeai/data/extra/compensation_{i}.json" for i in range(3)}

    with pytest.raises(vad.ErreurVerification, match="stacks"):
        vad._verifier_package_data(tmp_path / "a.whl", chemins)


def test_verifier_package_data_assets_sous_le_minimum_leve(tmp_path: Path) -> None:
    """Moins de 5 assets web : rejete."""
    chemins = set(_chemins_complets())
    chemins.remove("forgeai/web/assets/asset_4.txt")

    with pytest.raises(vad.ErreurVerification, match="assets"):
        vad._verifier_package_data(tmp_path / "a.whl", chemins)


def test_verifier_package_data_smoke_sous_le_minimum_leve(tmp_path: Path) -> None:
    """Moins de 2 scenarios smoke : rejete."""
    chemins = set(_chemins_complets())
    chemins.remove("forgeai/data/smoke/scenario_b.md")

    with pytest.raises(vad.ErreurVerification, match="smoke"):
        vad._verifier_package_data(tmp_path / "a.whl", chemins)


def test_verifier_package_data_catalogue_absent_leve(tmp_path: Path) -> None:
    """catalogue.json absent : rejete, meme avec un total JSON suffisant."""
    chemins = set(_chemins_complets())
    chemins.remove("forgeai/data/catalogue.json")
    chemins.add("forgeai/data/extra/compensation.json")

    with pytest.raises(vad.ErreurVerification, match="catalogue absent"):
        vad._verifier_package_data(tmp_path / "a.whl", chemins)


def test_verifier_package_data_json_insuffisant_leve(tmp_path: Path) -> None:
    """Tous les minimums par categorie tenus mais moins de 16 JSON au total :
    rejete (le filet global est independant des minimums par categorie)."""
    chemins = {
        "forgeai/data/locales/fr.json",
        "forgeai/data/locales/en.json",
        *[f"forgeai/data/stacks/stack_{i}.json" for i in range(6)],
        *[f"forgeai/web/assets/asset_{i}.txt" for i in range(5)],
        "forgeai/data/smoke/scenario_a.md",
        "forgeai/data/smoke/scenario_b.md",
        "forgeai/data/catalogue.json",
    }

    with pytest.raises(vad.ErreurVerification, match="package-data JSON incomplet"):
        vad._verifier_package_data(tmp_path / "a.whl", chemins)


# ---------------------------------------------------------------------------
# _contient_tests
# ---------------------------------------------------------------------------

def test_contient_tests_detecte_repertoire_tests() -> None:
    """Un segment « tests » n'importe ou dans le chemin est detecte."""
    assert vad._contient_tests(["forgeai_toolkit-0.1.0/tests/test_cli.py"]) is True


def test_contient_tests_insensible_a_la_casse() -> None:
    """La detection est insensible a la casse (« TESTS » vaut « tests »)."""
    assert vad._contient_tests(["projet/TESTS/test_cli.py"]) is True


def test_contient_tests_gere_les_separateurs_windows() -> None:
    """Les separateurs « \\ » sont normalises avant la detection."""
    assert vad._contient_tests(["projet\\tests\\test_cli.py"]) is True


def test_contient_tests_absent_retourne_faux() -> None:
    """Aucun segment exactement « tests » : False (« contest » ne compte pas)."""
    assert vad._contient_tests(["forgeai/cli.py", "contest/utils.py"]) is False


# ---------------------------------------------------------------------------
# _verifier_absences_interdites
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("est_sdist", [False, True])
def test_verifier_absences_interdites_pycache_interdit(
    tmp_path: Path, est_sdist: bool
) -> None:
    """Un segment __pycache__ est interdit dans un wheel COMME dans un sdist."""
    noms = ["forgeai/__pycache__/cli.cpython-312.pyc"]
    if est_sdist:
        noms.append("tests/test_cli.py")

    with pytest.raises(vad.ErreurVerification, match="compilé interdit"):
        vad._verifier_absences_interdites(tmp_path / "a", noms, est_sdist=est_sdist)


@pytest.mark.parametrize("est_sdist", [False, True])
def test_verifier_absences_interdites_pyc_interdit(
    tmp_path: Path, est_sdist: bool
) -> None:
    """Un fichier .pyc (meme hors __pycache__) est interdit partout."""
    noms = ["forgeai/cli.pyc"]
    if est_sdist:
        noms.append("tests/test_cli.py")

    with pytest.raises(vad.ErreurVerification, match="compilé interdit"):
        vad._verifier_absences_interdites(tmp_path / "a", noms, est_sdist=est_sdist)


@pytest.mark.parametrize("repertoire", ["reviews", "registres", "governance", ".github"])
@pytest.mark.parametrize("est_sdist", [False, True])
def test_verifier_absences_interdites_repertoires_interdits_levent(
    tmp_path: Path, repertoire: str, est_sdist: bool
) -> None:
    """reviews/, registres/, governance/ et .github/ sont interdits dans les
    DEUX formats de distribution."""
    noms = [f"{repertoire}/fichier.txt"]
    if est_sdist:
        noms.append("tests/test_cli.py")

    with pytest.raises(vad.ErreurVerification, match="fichier inattendu") as excinfo:
        vad._verifier_absences_interdites(tmp_path / "a", noms, est_sdist=est_sdist)

    assert repertoire in str(excinfo.value)


def test_verifier_absences_interdites_tests_interdits_dans_wheel(tmp_path: Path) -> None:
    """tests/ est interdit dans un WHEEL : le paquet distribue ne embarque pas les tests."""
    with pytest.raises(vad.ErreurVerification, match="fichier inattendu"):
        vad._verifier_absences_interdites(
            tmp_path / "a.whl", ["tests/test_cli.py"], est_sdist=False
        )


def test_verifier_absences_interdites_tests_toleres_dans_sdist(tmp_path: Path) -> None:
    """tests/ est TOLERE (et meme exige) dans un sdist."""
    assert (
        vad._verifier_absences_interdites(
            tmp_path / "a.tar.gz",
            ["forgeai/cli.py", "tests/test_cli.py"],
            est_sdist=True,
        )
        is None
    )


def test_verifier_absences_interdites_sdist_sans_tests_leve(tmp_path: Path) -> None:
    """Un sdist SANS tests/ est rejete : l'archive source doit permettre de tester."""
    with pytest.raises(vad.ErreurVerification, match="tests/ absent du sdist"):
        vad._verifier_absences_interdites(
            tmp_path / "a.tar.gz", ["forgeai/cli.py"], est_sdist=True
        )


def test_verifier_absences_interdites_wheel_sans_tests_passe(tmp_path: Path) -> None:
    """Un wheel sans tests/ n'a pas cette exigence : il passe."""
    assert (
        vad._verifier_absences_interdites(
            tmp_path / "a.whl", ["forgeai/cli.py"], est_sdist=False
        )
        is None
    )


# ---------------------------------------------------------------------------
# verifier_artefact — integration bout en bout sur archives factices reelles
# ---------------------------------------------------------------------------

def test_verifier_artefact_wheel_valide_passe(tmp_path: Path) -> None:
    """Un wheel complet et conforme passe toutes les verifications."""
    chemin = _ecrire_wheel(
        tmp_path / "forgeai_toolkit-0.1.0-py3-none-any.whl", _membres_wheel_valides()
    )

    assert vad.verifier_artefact(chemin) is None


def test_verifier_artefact_sdist_valide_passe(tmp_path: Path) -> None:
    """Un sdist complet et conforme (PKG-INFO racine + tests/) passe."""
    chemin = _ecrire_sdist(tmp_path / "forgeai_toolkit-0.1.0.tar.gz", _membres_sdist_valides())

    assert vad.verifier_artefact(chemin) is None


def test_verifier_artefact_tgz_valide_passe(tmp_path: Path) -> None:
    """L'extension .tgz est acceptee au meme titre que .tar.gz."""
    chemin = _ecrire_sdist(tmp_path / "forgeai_toolkit-0.1.0.tgz", _membres_sdist_valides())

    assert vad.verifier_artefact(chemin) is None


def test_verifier_artefact_extension_inconnue_leve(tmp_path: Path) -> None:
    """Une extension hors .whl/.tar.gz/.tgz est refusee sans inspection."""
    chemin = tmp_path / "artefact.zip"
    chemin.write_bytes(b"donnees quelconques")

    with pytest.raises(vad.ErreurVerification, match="format non pris en charge"):
        vad.verifier_artefact(chemin)


def test_verifier_artefact_fichier_introuvable_leve(tmp_path: Path) -> None:
    """Un chemin inexistant est rejete proprement."""
    with pytest.raises(vad.ErreurVerification, match="artefact introuvable"):
        vad.verifier_artefact(tmp_path / "absent.whl")


def test_verifier_artefact_sdist_malveillant_rejete_bout_en_bout(tmp_path: Path) -> None:
    """Bout en bout : un sdist contenant une remontee « .. » est integralement rejete."""
    membres = _membres_sdist_valides()
    membres["forgeai_toolkit-0.1.0/../../evil.py"] = b"malveillant"
    chemin = _ecrire_sdist(tmp_path / "forgeai_toolkit-0.1.0.tar.gz", membres)

    with pytest.raises(vad.ErreurVerification, match="non sûr"):
        vad.verifier_artefact(chemin)


# ---------------------------------------------------------------------------
# main — integration CLI (capsys)
# ---------------------------------------------------------------------------

def test_main_artefacts_valides_retourne_zero_et_imprime_ok(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Tous les artefacts valides : retour 0 et une ligne « OK : <chemin> » chacun."""
    wheel = _ecrire_wheel(
        tmp_path / "forgeai_toolkit-0.1.0-py3-none-any.whl", _membres_wheel_valides()
    )
    sdist = _ecrire_sdist(tmp_path / "forgeai_toolkit-0.1.0.tar.gz", _membres_sdist_valides())

    assert vad.main([str(wheel), str(sdist)]) == 0

    sortie = capsys.readouterr()
    assert f"OK : {wheel}" in sortie.out
    assert f"OK : {sdist}" in sortie.out
    assert sortie.err == ""


def test_main_artefact_invalide_retourne_un_et_imprime_erreur(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Un artefact invalide : retour 1 et « ERREUR : ... » sur stderr."""
    wheel = _ecrire_wheel(tmp_path / "mauvais.whl", {"forgeai/cli.py": b"x"})

    assert vad.main([str(wheel)]) == 1

    sortie = capsys.readouterr()
    assert "ERREUR :" in sortie.err
    assert str(wheel) in sortie.err
    assert sortie.out == ""


def test_main_arrete_au_premier_artefact_invalide(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Le premier manquement interrompt la boucle : l'artefact valide deja traite
    a son « OK », l'invalide produit « ERREUR » et le retour est 1."""
    valide = _ecrire_wheel(
        tmp_path / "forgeai_toolkit-0.1.0-py3-none-any.whl", _membres_wheel_valides()
    )
    invalide = _ecrire_wheel(tmp_path / "mauvais.whl", {"forgeai/cli.py": b"x"})

    assert vad.main([str(valide), str(invalide)]) == 1

    sortie = capsys.readouterr()
    assert f"OK : {valide}" in sortie.out
    assert f"OK : {invalide}" not in sortie.out
    assert "ERREUR :" in sortie.err
    assert str(invalide) in sortie.err
