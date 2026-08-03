"""I18N-031 — `--lang` doit réellement changer la sortie du CLI, pas seulement du wizard.

Mesuré avant correctif : 13 appels `t()` sur 134 littéraux français candidats dans `cli.py`
(81 réels après filtrage des faux positifs par AST), et `preflight.py` — dont le contenu
alimente directement `forgeai doctor` — n'utilisait `t()` nulle part. `--lang en` était donc
accepté par la CLI sans effet sur la quasi-totalité de sa propre sortie.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

RACINE = Path(__file__).resolve().parents[1]
LOCALES = RACINE / "src" / "forgeai" / "data" / "locales"
CLI = RACINE / "src" / "forgeai" / "cli.py"
PREFLIGHT = RACINE / "src" / "forgeai" / "preflight.py"
STACKS = RACINE / "src" / "forgeai" / "data" / "stacks"


@pytest.fixture(autouse=True)
def _isoler_locale_globale():
    """`set_locale()` modifie un état GLOBAL au module `forgeai.i18n`. Sans restauration,
    un test qui bascule en 'en' contaminerait tout test suivant du même process pytest —
    y compris, ailleurs dans le dépôt, des assertions sur un texte d'exception français
    exact (`pytest.raises(match=...)`). On capture la locale AVANT (via l'API publique,
    qui respecte FORGEAI_LANG) et on la restaure APRÈS, quel que soit le résultat du test."""
    from forgeai.i18n import get_translator, set_locale

    avant = get_translator().locale
    yield
    set_locale(avant)


def _cles_t_appelees(fichier: Path) -> set[str]:
    """Extrait par AST toutes les clés passées à `t("...")` — jamais par regex sur du texte,
    qui confond `str.split(".")`/`dict.get("docker")` avec de vrais appels `t(`."""
    tree = ast.parse(fichier.read_text(encoding="utf-8"))
    cles = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "t" and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)):
            cles.add(node.args[0].value)
    return cles


def test_g1_parite_stricte_entre_les_deux_locales():
    """CA — le mécanisme `t()` lève `MissingTranslation` si une clé manque : une locale en
    retard casserait silencieusement UNE des deux langues au premier utilisateur qui la choisit."""
    fr = json.loads((LOCALES / "fr.json").read_text(encoding="utf-8"))
    en = json.loads((LOCALES / "en.json").read_text(encoding="utf-8"))
    seulement_fr = set(fr) - set(en)
    seulement_en = set(en) - set(fr)
    assert not seulement_fr, f"clés présentes en fr, absentes en en : {seulement_fr}"
    assert not seulement_en, f"clés présentes en en, absentes en fr : {seulement_en}"


def test_g2_toute_cle_appelee_dans_cli_et_preflight_existe_dans_les_deux_locales():
    """CA — LE détecteur direct : sans ça, `--lang en` sur une commande donnée lèverait
    `MissingTranslation` en plein milieu de l'exécution."""
    fr = json.loads((LOCALES / "fr.json").read_text(encoding="utf-8"))
    en = json.loads((LOCALES / "en.json").read_text(encoding="utf-8"))
    utilisees = _cles_t_appelees(CLI) | _cles_t_appelees(PREFLIGHT)
    assert utilisees, "aucune clé t() détectée — le test lui-même serait vide de sens"
    manquantes_fr = utilisees - set(fr)
    manquantes_en = utilisees - set(en)
    assert not manquantes_fr, f"clés utilisées mais absentes de fr.json : {manquantes_fr}"
    assert not manquantes_en, f"clés utilisées mais absentes de en.json : {manquantes_en}"


def test_g3_doctor_produit_un_texte_reellement_different_entre_fr_et_en():
    """CA1 — le cas emblématique signalé : `doctor` avait du texte français codé en dur,
    entièrement insensible à `--lang`."""
    from forgeai.i18n import set_locale
    from forgeai.preflight import check_python

    set_locale("fr")
    fr = check_python()
    set_locale("en")
    en = check_python()

    assert fr.detail != en.detail or fr.enables != en.enables, (
        "check_python() doit produire un texte différent selon la locale — "
        f"fr={fr!r} en={en!r}"
    )
    assert "requis" in fr.enables and "requires" in en.enables, (
        "les mots caractéristiques de chaque langue doivent apparaître : "
        f"fr={fr.enables!r} en={en.enables!r}"
    )


def test_g4_chemin_reel_doctor_bout_en_bout(capsys):
    """CA1 — bout en bout via `forgeai.cli.main`, le point d'entrée réel : c'est CE chemin
    que tape un utilisateur avec `--lang en doctor`. Aucun mock : `doctor` sonde la vraie
    machine (docker/kubectl/ollama/matériel), exactement comme en production."""
    from forgeai.cli import main

    assert main(["--lang", "fr", "doctor"]) == 0
    sortie_fr = capsys.readouterr().out
    assert main(["--lang", "en", "doctor"]) == 0
    sortie_en = capsys.readouterr().out

    assert sortie_fr != sortie_en, "la sortie de `doctor` doit différer selon --lang"
    assert "environnement" in sortie_fr
    assert "environment" in sortie_en


def test_g5_node_cluster_vide_bilingue():
    """CA1 — un second point d'entrée réel, indépendant de doctor/preflight, pour prouver que
    la couverture n'est pas un cas isolé mais systématique sur le lot cli.py."""
    import argparse
    from forgeai.cli import _node_cluster
    from forgeai.i18n import set_locale

    args = argparse.Namespace(registre="Registres/inexistant-pour-ce-test.jsonl")

    import io, contextlib
    for lang, mot_attendu in (("fr", "cluster"), ("en", "cluster")):
        set_locale(lang)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            _node_cluster(args)
        assert mot_attendu in buf.getvalue()

    set_locale("fr")
    buf_fr = io.StringIO()
    with contextlib.redirect_stdout(buf_fr):
        _node_cluster(args)
    set_locale("en")
    buf_en = io.StringIO()
    with contextlib.redirect_stdout(buf_en):
        _node_cluster(args)
    assert buf_fr.getvalue() != buf_en.getvalue(), (
        f"fr={buf_fr.getvalue()!r} en={buf_en.getvalue()!r}"
    )


def test_g6_aucun_print_francais_ne_survit_hors_du_mecanisme_t(monkeypatch):
    """CA — le détecteur de complétude : recense par AST tout `print()` dont l'argument
    contient un caractère accentué et ne passe pas par `t(...)`. Ignore les faux positifs
    connus (sérialisation JSON, jointure de données déjà calculées)."""
    import re

    restants = []
    for fichier in (CLI, PREFLIGHT):
        src = fichier.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "print" and node.args):
                continue
            segment = ast.get_source_segment(src, node.args[0]) or ""
            if segment.startswith("t("):
                continue
            if "json.dumps" in segment or '"\\n".join' in segment:
                continue
            if re.search(r"[À-ÿ]", segment):
                restants.append((fichier.name, node.lineno, segment[:80]))

    assert not restants, f"texte français hors du mécanisme t() : {restants}"


def test_g7_chaque_stack_a_une_description_en_non_vide():
    """CA5 — objection round 2 (Qwen3.8-Max) : `_template_show` retombe sur `description_fr`
    si `description_en` manque pour un stack donné, ce qui ferait fuiter du français sous
    `--lang en`. Round 1 avait vérifié les 6 fichiers manuellement sans figer la garantie dans
    un test ; ce test la rend structurelle — toute stack future sans `description_en` casse ici,
    pas silencieusement en production."""
    fichiers = sorted(STACKS.glob("*.json"))
    assert fichiers, "aucun fichier de stack trouvé — le test lui-même serait vide de sens"
    manquants = []
    for f in fichiers:
        data = json.loads(f.read_text(encoding="utf-8"))
        if not data.get("description_en", "").strip():
            manquants.append(f.name)
    assert not manquants, f"stacks sans description_en : {manquants}"


def test_g8_template_list_show_resolve_bilingues(tmp_path, capsys):
    """CA5 — `_template_list`/`_template_show`/`_template_resolve` n'étaient exercées par
    AUCUN test avant I18N-031 (0% de couverture sur leur corps entier) : la note de
    dépréciation et la description de stack sélectionnée par locale n'étaient donc jamais
    vérifiées en exécution réelle, seulement par une commande manuelle ponctuelle."""
    from forgeai.cli import main

    registre = tmp_path / "reg.jsonl"
    sorties_show = {}
    for lang in ("fr", "en"):
        assert main(["--lang", lang, "template", "list"]) == 0
        sortie_list = capsys.readouterr().out
        assert "agentique" in sortie_list

        assert main(["--lang", lang, "template", "show", "agentique"]) == 0
        sorties_show[lang] = capsys.readouterr().out
        assert "Agentique" in sorties_show[lang]

        assert main(["--lang", lang, "template", "resolve", "agentique",
                     "--registre", str(registre)]) == 0
        sortie_resolve = capsys.readouterr().out
        assert "Agentique" in sortie_resolve

    assert sorties_show["fr"] != sorties_show["en"], (
        "la description de stack affichée par `template show` doit différer selon --lang "
        f"(description_fr vs description_en) : {sorties_show}"
    )

    assert main(["--lang", "fr", "template", "show", "stack-inexistante-xyz"]) == 12
    erreur_fr = capsys.readouterr().err
    assert main(["--lang", "en", "template", "show", "stack-inexistante-xyz"]) == 12
    erreur_en = capsys.readouterr().err
    assert erreur_fr != erreur_en, "le message d'erreur template show doit différer selon --lang"


def test_g9_node_prepare_bilingue_titre_statut_et_repli_defensif(monkeypatch, capsys, tmp_path):
    """CA7 — objection round 3 (Qwen3.8-Max) : `_node_prepare` n'était exercée par aucun test
    à travers le CLI (seul `network.prepare.preparer_noeud` l'était, directement). Le repli
    défensif sur `MissingTranslation` (statut de domaine imprévu -> texte brut plutôt qu'un
    crash) n'avait jamais été exécuté par un test automatisé, seulement vérifié à la main."""
    import argparse
    from forgeai.cli import _node_prepare
    from forgeai.i18n import set_locale

    def fake_preparer_noeud(runner, hostname, *, appliquer, helm_present):
        return {
            "hostname": hostname,
            "receptacle": "pret",
            "etapes": [
                {"id": "diagnostic", "titre_fr": "Diagnostic", "titre_en": "Diagnostic check",
                 "statut": "ok"},
                {"id": "label-cpu", "titre_fr": "Étiqueter", "titre_en": "Label",
                 "statut": "planifiee"},
                {"id": "helm-x", "titre_fr": "Installer", "titre_en": "Install",
                 "statut": "echec"},
                {"id": "y", "titre_fr": "Y", "titre_en": "Y", "statut": "sautee"},
                {"id": "z", "titre_fr": "Z", "titre_en": "Z", "statut": "statut-jamais-vu-avant"},
            ],
        }

    monkeypatch.setattr("forgeai.network.prepare.preparer_noeud", fake_preparer_noeud)
    args = argparse.Namespace(hostname="n1", apply=False,
                              registre=str(tmp_path / "test-g9.jsonl"))

    set_locale("fr")
    assert _node_prepare(args) == 0
    sortie_fr = capsys.readouterr().out
    assert "Diagnostic" in sortie_fr
    assert "statut-jamais-vu-avant" in sortie_fr, (
        "un statut inconnu doit s'afficher en repli brut, jamais lever MissingTranslation"
    )

    set_locale("en")
    assert _node_prepare(args) == 0
    sortie_en = capsys.readouterr().out
    assert "Label" in sortie_en
    assert sortie_fr != sortie_en


def test_g10_node_discover_local_reel(capsys):
    """CA — `_node_discover` (hors branche SSH) n'était exercée par aucun test malgré son
    usage de `t()` sur 4 clés (endpoint/via/service/hostkey_requis). Sonde la VRAIE machine
    locale (comme `doctor`), pas un simulacre — cohérent avec le reste de la suite bilingue."""
    from forgeai.cli import main

    assert main(["--lang", "fr", "node", "discover", "local"]) == 0
    sortie_fr = capsys.readouterr().out
    assert main(["--lang", "en", "node", "discover", "local"]) == 0
    sortie_en = capsys.readouterr().out

    assert sortie_fr
    assert sortie_en
