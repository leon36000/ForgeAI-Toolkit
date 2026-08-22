"""Validateur de clôtures de blocs de code Markdown (RC1-011, #441).

Périmètre volontairement étroit : structure des fences uniquement (pas markdownlint — importer
une dépendance violerait `dependencies=[]` stdlib pur du produit). Deux règles :
  R1 (exacte)      : bloc ouvert non refermé à EOF — convention DE CE DÉPÔT, pas de la spec
                      CommonMark (qui ferme implicitement en fin de document). Nommée
                      honnêtement comme telle dans le code, pas présentée comme un standard.
  R2 (heuristique) : une ligne en forme d'OUVERTURE (même marqueur, longueur >= celle du bloc
                      déjà ouvert, avec chaîne d'info) rencontrée À L'INTÉRIEUR d'un bloc ouvert
                      — elle ne peut structurellement jamais le fermer (une ligne de clôture ne
                      porte jamais de chaîne d'info en CommonMark). Une longueur INFÉRIEURE à
                      celle du bloc ouvert ne peut structurellement pas interagir avec lui : cas
                      légitime de fence imbriquée (voir
                      test_fence_plus_longue_imbriquee_dans_fence_plus_courte_legitime).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "check_md_packs", REPO / "scripts" / "governance" / "check_md_packs.py"
)
check_md_packs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_md_packs)


# ---------------------------------------------------------------------------
# analyser() — cas unitaires sur du texte synthétique
# ---------------------------------------------------------------------------

def test_bloc_ferme_correctement_aucun_defaut():
    texte = "texte\n```python\ncode = 1\n```\nsuite\n"
    assert check_md_packs.analyser(texte) == []


def test_bloc_tildes_ferme_correctement_aucun_defaut():
    texte = "texte\n~~~python\ncode = 1\n~~~\nsuite\n"
    assert check_md_packs.analyser(texte) == []


def test_r1_bloc_non_ferme_a_eof():
    texte = "texte\n```python\ncode = 1\n"
    defauts = check_md_packs.analyser(texte)
    assert len(defauts) == 1
    assert defauts[0]["regle"] == "R1"
    assert defauts[0]["ligne"] == 2


def test_r1_reproduit_impl_2b_civ_crochet_colle_aux_backticks():
    # Isole le MÉCANISME réel trouvé dans evidence/reviews/IMPL-2b-civ/pack.md:627 (pas une
    # reproduction bit-à-bit de la classification finale du fichier réel, qui est R2 — voir
    # stories/RC1-011.md : dans le fichier réel, une VRAIE fence ```diff rouvre plus loin
    # (ligne 630) après ce même bloc, ce qui change la règle imputée de R1 à R2). Ce test isole
    # le mécanisme sous-jacent seul : une ligne de contenu ']```' n'est PAS une ligne de clôture
    # CommonMark valide (elle porte du texte AVANT les backticks, donc ne matche même pas le
    # motif de fence) -> ignorée comme simple contenu -> si aucune fence valide ne suit ensuite
    # (cas synthétique ici), le bloc ouvert reste ouvert jusqu'à EOF -> R1. Voir
    # test_r2_ouverture_dans_bloc_ouvert_sans_fermeture_entre_les_deux pour le cas R2 correspondant.
    texte = 'avant\n```json\n["a", "b"]```\nsuite tronquée sans fermeture valide\n'
    defauts = check_md_packs.analyser(texte)
    assert len(defauts) == 1
    assert defauts[0]["regle"] == "R1"
    assert defauts[0]["ligne"] == 2


def test_r2_ouverture_dans_bloc_ouvert_sans_fermeture_entre_les_deux():
    # Reproduction exacte du défaut réel (S1-gpu-rocm-runtime/pack.md, S3-...) : deux sections
    # "## Diff intégral" consécutives, chacune ouvrant ```diff, sans ``` nu de fermeture entre
    # les deux -> la 2e ouverture ne peut pas fermer la 1re (elle porte une chaîne d'info).
    texte = (
        "## Diff intégral (tour 1)\n```diff\ndiff --git a b\n"
        "## Diff intégral (tour 2)\n```diff\ndiff --git c d\n```\n"
    )
    defauts = check_md_packs.analyser(texte)
    assert len(defauts) == 1
    assert defauts[0]["regle"] == "R2"
    assert defauts[0]["ligne"] == 2


def test_r2_ne_casse_pas_la_fermeture_valide_du_bloc_initial_par_un_closeur_plus_court():
    # Bug réel trouvé par revue scellée (GPT-5.6-Terra-Pro, RC1-011 round 10) : bloc_ouvert ne
    # doit PAS être réassigné à la pseudo-ouverture détectée par R2 — sinon un closeur valide
    # pour le bloc INITIAL (longueur 3) mais plus court que la pseudo-ouverture (longueur 4) ne
    # peut plus le fermer, et un FAUX R1 supplémentaire apparaît à EOF. Document ci-dessous
    # entièrement valide en CommonMark réel (la ligne 2, 4 backticks + info, est simple contenu
    # du bloc de 3 backticks ouvert en ligne 1 ; la ligne 3 le ferme validement) : SEUL le R2
    # (signal légitime — la ligne 2 a la forme d'une ouverture ratée) doit être rapporté, JAMAIS
    # de R1.
    texte = "```python\n````lang\n```\n"
    defauts = check_md_packs.analyser(texte)
    assert defauts == [{"regle": "R2", "ligne": 1}]


def test_backtick_dans_chaine_info_fence_backticks_nest_pas_une_ouverture_valide():
    # CommonMark §4.5 : la chaîne d'info d'une fence à BACKTICKS ne peut contenir aucun backtick
    # (restriction absente pour les fences à tildes). Sans cette vérification, la ligne centrale
    # ci-dessous (longueur et marqueur suffisants pour R2, mais backtick dans l'info "foo`")
    # serait à tort signalée R2 ; en réalité elle n'est ni ouverture ni fermeture valides, donc
    # simple contenu du bloc ouvert par la ligne 1, refermé proprement par la ligne 3.
    texte = "```text\n```foo`\n```\n"
    assert check_md_packs.analyser(texte) == []


def test_backtick_dans_chaine_info_fence_tildes_reste_une_ouverture_valide():
    # La restriction ci-dessus ne s'applique PAS aux fences à tildes : un backtick dans l'info
    # d'une fence ~~~ est un caractère de contenu ordinaire, sans effet sur la validité.
    texte = "~~~text\n~~~foo`\ncontenu\n~~~\n"
    defauts = check_md_packs.analyser(texte)
    assert len(defauts) == 1
    assert defauts[0]["regle"] == "R2"
    assert defauts[0]["ligne"] == 1


def test_nbsp_apres_fence_ne_ferme_pas_et_ne_declenche_pas_r2():
    # Bug réel trouvé par revue scellée (GPT-5.6-Terra-Pro, RC1-011 round 13) : CommonMark
    # n'autorise après une fence de clôture que des espaces/tabulations ASCII (spec §4.5), pas
    # la classe Unicode complète de `str.isspace()` — U+00A0 (NBSP) n'est PAS un espace/tabulation
    # ASCII. `str.strip()` nu traitait à tort une ligne "```<NBSP>" comme une clôture valide.
    # Attendu : le bloc reste ouvert jusqu'à EOF -> UN SEUL R1 (le NBSP n'est pas non plus une
    # vraie tentative de réouverture au sens R2 — c'est du résidu Unicode, pas une annotation de
    # langage : `info_r2`, qui juge R2, garde le strip Unicode complet et ne voit donc rien à
    # signaler).
    texte = "```python\nx\n```\xa0\n"
    assert check_md_packs.analyser(texte) == [{"regle": "R1", "ligne": 1}]


def test_fence_plus_longue_imbriquee_dans_fence_plus_courte_legitime():
    # Un bloc ouvert par 4 backticks peut légitimement contenir une ligne de 3 backticks comme
    # simple CONTENU (elle ne peut pas le fermer, trop courte) -> aucun défaut.
    texte = "avant\n````markdown\nexemple:\n```python\ncode\n```\n````\nsuite\n"
    assert check_md_packs.analyser(texte) == []


def test_indentation_jusqu_a_3_espaces_reste_une_fence_valide():
    texte = "texte\n   ```python\n   code = 1\n   ```\nsuite\n"
    assert check_md_packs.analyser(texte) == []


def test_indentation_4_espaces_est_un_bloc_indente_pas_une_fence():
    # >= 4 espaces = bloc de code indenté (règle CommonMark distincte) ; les ``` à l'intérieur
    # ne sont alors que du texte littéral, pas des marqueurs de fence.
    texte = "texte\n    ```python\n    code\nsuite normale\n"
    assert check_md_packs.analyser(texte) == []


def test_deux_blocs_sains_a_la_suite_aucun_defaut():
    texte = "a\n```python\nx = 1\n```\nb\n```diff\n+y\n```\nc\n"
    assert check_md_packs.analyser(texte) == []


# ---------------------------------------------------------------------------
# scanner() — sur le vrai dépôt, cliquet anti-régression
# ---------------------------------------------------------------------------

# Défauts CONNUS, mesurés et vérifiés manuellement (voir stories/RC1-011.md) — décision
# d'architecture : CLASSER ces 4 fichiers, pas les corriger (leurs octets sont dans la préimage
# du prompt_sha256 scellé par civ_review.py ; les modifier les rendrait non vérifiables contre
# leur propre sceau sans qu'aucun gate ne le détecte). Écrit À LA MAIN, chemin ET détail exact
# (règle + ligne, pas seulement l'ensemble des chemins) — un NOUVEAU défaut dans un fichier déjà
# connu (ligne/règle différente d'un round à l'autre, ou un 2e défaut apparu dans un fichier qui
# n'en portait qu'un) fait échouer ce test tout autant qu'un nouveau fichier jamais vu.
KNOWN_INVALID = {
    "evidence/reviews/IMPL-2b-civ/pack.md": [{"regle": "R2", "ligne": 29}],
    "evidence/reviews/S1-gpu-rocm-runtime/pack.md": [{"regle": "R2", "ligne": 25}],
    "evidence/reviews/S3-amd-runtimes-k3s-gpu/pack.md": [{"regle": "R2", "ligne": 29}],
    # 4e défaut, trouvé par ce scanner (rglob *.md, pas restreint au nom "pack.md" comme le
    # premier passage manuel) : ```markdown (L6) enveloppe un ADR entier qui contient ses
    # propres blocs ```python (L22) de MÊME longueur -> collision de fence classique (R2 en
    # L6), puis un ``` isolé (L317) jamais refermé (R1). Non liant (absent de BINDING.txt).
    "evidence/reviews/HEALTH-028A/REVIEW-PACK.md": [
        {"regle": "R2", "ligne": 6},
        {"regle": "R1", "ligne": 317},
    ],
}


def _scan_relatif() -> dict[str, list[dict]]:
    resultats = check_md_packs.scanner(REPO / "evidence" / "reviews")
    return {
        str(Path(chemin).relative_to(REPO)): defauts
        for chemin, defauts in resultats.items()
        if defauts
    }


def test_scanner_ne_depasse_pas_les_defauts_connus_sur_le_vrai_depot():
    chemins_defaillants = _scan_relatif()
    nouveaux = set(chemins_defaillants) - set(KNOWN_INVALID)
    assert not nouveaux, (
        f"nouveau(x) pack(s) Markdown à clôture invalide, non classé(s) dans "
        f"stories/RC1-011.md : {sorted(nouveaux)}"
    )


def test_scanner_trouve_exactement_les_4_defauts_connus_regle_et_ligne():
    chemins_defaillants = _scan_relatif()
    for chemin, attendu in KNOWN_INVALID.items():
        assert chemin in chemins_defaillants, (
            f"défaut connu disparu du scan réel — soit il a été corrigé (mettre à jour "
            f"KNOWN_INVALID + stories/RC1-011.md), soit le scanner a régressé : {chemin}"
        )
        assert chemins_defaillants[chemin] == attendu, (
            f"le détail du défaut a changé pour {chemin} : "
            f"{chemins_defaillants[chemin]} != {attendu} attendu — mettre à jour KNOWN_INVALID "
            f"+ stories/RC1-011.md si le changement est légitime, sinon le scanner a régressé"
        )


# ---------------------------------------------------------------------------
# main() — CLI
# ---------------------------------------------------------------------------

def test_main_retourne_0_si_aucun_nouveau_defaut(tmp_path, monkeypatch, capsys):
    sain = tmp_path / "sain.md"
    sain.write_text("```python\nx = 1\n```\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["check_md_packs.py", "--racine", str(tmp_path)])
    rc = check_md_packs.main()
    assert rc == 0


def test_main_retourne_1_si_defaut_non_connu(tmp_path, monkeypatch):
    casse = tmp_path / "casse.md"
    casse.write_text("```python\nx = 1\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["check_md_packs.py", "--racine", str(tmp_path)])
    rc = check_md_packs.main()
    assert rc == 1


def test_scanner_ignore_prompt_sol_genere_mais_scan_pack_voisin(tmp_path):
    dossier = tmp_path / "evidence" / "reviews" / "S-sol"
    dossier.mkdir(parents=True)
    prompt = dossier / "SOL-PROMPT.md"
    prompt.write_text("```diff\n+diff brut\n", encoding="utf-8")
    pack = dossier / "pack.md"
    pack.write_text("```diff\ndiff --git a b\n```\n", encoding="utf-8")
    decoy = tmp_path / "not-a-review" / "SOL-PROMPT.md"
    decoy.parent.mkdir(parents=True)
    decoy.write_text("```diff\nnon canonique\n", encoding="utf-8")

    resultats = check_md_packs.scanner(tmp_path)

    assert str(prompt) not in resultats
    assert resultats[str(pack)] == []
    assert resultats[str(decoy)] == [{"regle": "R1", "ligne": 1}]
