"""Périmètre du scan de secrets GitGuardian (RC1-015, #445).

Contexte : `.gitguardian.yaml` excluait globalement `**/*.md` — prompts, rapports, revues et
documents pouvaient donc contenir des valeurs sensibles sans jamais être scannés. Gitleaks
(gate CI toujours actif, indépendamment de cette config) réduisait le risque mais ne prouve pas
l'équivalence : ses détecteurs et sa politique de validation en ligne (AWS/GitHub/... : clé
vérifiée active ou non) diffèrent de ceux de GitGuardian.

Décision (voir stories/RC1-015.md) : retirer l'exclusion globale SANS la remplacer par une
exclusion de remplacement — vérification réelle locale (`ggshield secret scan path --recursive`,
CLI installée dans un venv scratch, sans authentification requise pour la détection par motifs)
montre 0 nouvel incident sur les 251 fichiers `.md` avant exclus (1961 fichiers scannés vs 1710
avec l'ancienne exclusion, mêmes 4 incidents pré-existants dans `tests/*.py`, tous `known: true`,
sans rapport avec le Markdown). Ce module vérifie STRUCTURELLEMENT que `.gitguardian.yaml` ne
réintroduit jamais cette exclusion globale, sans dépendre de `ggshield` (outil de dev optionnel,
absent de `dependencies=[]` — voir capabilities.py).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "check_gitguardian_scope", REPO / "scripts" / "governance" / "check_gitguardian_scope.py"
)
check_gitguardian_scope = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_gitguardian_scope)


# ---------------------------------------------------------------------------
# parser_ignored_paths() — extraction minimale, sans dépendance YAML
# ---------------------------------------------------------------------------

def test_parser_extrait_la_liste_ignored_paths(tmp_path):
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'version: 2\n'
        'secret:\n'  # proof:allow — clé de schéma YAML GitGuardian dans une fixture de test, pas un secret réel
        '  ignored_paths:\n'
        '    - "tests/fixtures/**"\n'
        '    - "LICENSE"\n',
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == [
        "tests/fixtures/**",
        "LICENSE",
    ]


def test_parser_reconnait_ignored_paths_meme_avec_un_commentaire_yaml_a_droite(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 1) : sans cette tolérance, un
    # contributeur ajoutant un commentaire sur la ligne `ignored_paths:` (motif déjà présent
    # ailleurs dans ce fichier, ex. `secret:  # proof:allow — ...`) ferait retourner une liste
    # vide à `parser_ignored_paths` — `verifier()` répondrait alors (True, []) même si
    # `**/*.md` est présent plus bas, masquant silencieusement une régression.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n'  # proof:allow — clé de schéma YAML GitGuardian dans une fixture de test, pas un secret réel
        '  ignored_paths:  # liste de chemins exclus\n'
        '    - "**/*.md"\n',
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_reconnait_les_items_meme_avec_un_commentaire_yaml_a_droite(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 5) : le round 1 ne couvrait que le
    # commentaire sur la ligne `ignored_paths:` — un commentaire sur un ITEM de la liste
    # (`- "tests/fixtures/**" # commentaire`, syntaxe YAML valide) faisait échouer `_LIGNE_ITEM`,
    # ce qui terminait l'analyse de la liste PRÉMATURÉMENT (ligne traitée comme "fin de liste")
    # et masquait silencieusement tout item suivant, y compris une réintroduction de `**/*.md`.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n'  # proof:allow — clé de schéma YAML GitGuardian dans une fixture de test, pas un secret réel
        '  ignored_paths:\n'
        '    - "tests/fixtures/**" # commentaire sur un item\n'
        '    - "**/*.md"\n',
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == [
        "tests/fixtures/**",
        "**/*.md",
    ]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_reconnait_les_items_separes_par_une_ligne_vide(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 6) : une ligne vide entre deux items
    # est du YAML valide au sein d'une séquence, mais faisait terminer prématurément l'analyse
    # (traitée comme "fin de liste"), masquant silencieusement tout item suivant.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n'  # proof:allow — clé de schéma YAML GitGuardian dans une fixture de test, pas un secret réel
        '  ignored_paths:\n'
        '    - "tests/fixtures/**"\n'
        '\n'
        '    - "**/*.md"\n',
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == [
        "tests/fixtures/**",
        "**/*.md",
    ]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_reconnait_les_items_separes_par_un_commentaire_seul(tmp_path):
    # Même bug (RC1-015 round 6), variante ligne de commentaire SEULE (pas en fin d'item).
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n'  # proof:allow — clé de schéma YAML GitGuardian dans une fixture de test, pas un secret réel
        '  ignored_paths:\n'
        '    - "tests/fixtures/**"\n'
        '    # commentaire seul sur sa propre ligne\n'
        '    - "**/*.md"\n',
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == [
        "tests/fixtures/**",
        "**/*.md",
    ]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_s_arrete_a_la_fin_de_la_liste_indentee(tmp_path):
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'version: 2\n'
        'secret:\n'  # proof:allow — clé de schéma YAML GitGuardian dans une fixture de test, pas un secret réel
        '  ignored_paths:\n'
        '    - "a"\n'
        '    - "b"\n'
        'autre_cle: valeur\n',
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["a", "b"]


def test_parser_fichier_sans_ignored_paths_retourne_liste_vide(tmp_path):
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text("version: 2\n", encoding="utf-8")
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == []


def test_parser_accepte_les_guillemets_simples(tmp_path):
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        "secret:\n  ignored_paths:\n    - 'a/b/**'\n",  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["a/b/**"]


# ---------------------------------------------------------------------------
# est_exclusion_markdown_globale() — détecte le motif problématique
# ---------------------------------------------------------------------------

def test_detecte_double_etoile_slash_etoile_md():
    assert check_gitguardian_scope.est_exclusion_markdown_globale("**/*.md") is True


def test_detecte_etoile_md_nu():
    assert check_gitguardian_scope.est_exclusion_markdown_globale("*.md") is True


def test_ne_detecte_pas_un_chemin_specifique_se_terminant_en_md():
    # Un chemin de fixture précis se terminant par .md n'est PAS une exclusion globale.
    assert check_gitguardian_scope.est_exclusion_markdown_globale("tests/fixtures/exemple.md") is False


def test_ne_detecte_pas_un_glob_de_sous_dossier_borne():
    # evidence/reviews/**/*.md : borné à un sous-arbre précis, structurellement différent
    # d'une exclusion racine ("**/*.md" couvre TOUT le dépôt, celui-ci un seul sous-arbre).
    assert check_gitguardian_scope.est_exclusion_markdown_globale("evidence/reviews/**/*.md") is False


def test_ne_detecte_pas_les_autres_exceptions_legitimes():
    for chemin in ["tests/fixtures/**", "src/forgeai/data/catalogue.json", "LICENSE", ".gitignore"]:
        assert check_gitguardian_scope.est_exclusion_markdown_globale(chemin) is False


def test_detecte_exclusion_totale_du_depot_comme_exclusion_markdown(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 77, GPT-5.6-Terra-Pro) :
    # `est_exclusion_markdown_globale()` ne reconnaissait que `**/*.md`/`*.md`, laissant passer
    # une exclusion PLUS LARGE qui exclut LITTÉRALEMENT TOUT le dépôt (donc tout le Markdown
    # comme sous-ensemble). Reproduction exacte du reviewer, vérifiée RÉELLEMENT contre le
    # moteur `ggshield.core.filter` (venv scratch, outil de dev optionnel) : `**/*` matche bien
    # `foo.md`, `stories/bar.md`, tout fichier du dépôt.
    for motif in ("*", "**", "**/*", "**/**"):
        assert check_gitguardian_scope.est_exclusion_markdown_globale(motif) is True, motif
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  ignored_paths:\n    - "**/*"\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*"]


def test_ggshield_reel_toute_forme_excluant_tout_le_depot_exclut_aussi_markdown():
    # Non-régression/preuve : les mêmes 4 motifs, testés RÉELLEMENT contre le moteur GitGuardian
    # (skip propre si `ggshield` absent, jamais une dépendance du produit `dependencies=[]`),
    # matchent bien un échantillon de fichiers Markdown réels — confirmant que reconnaître ces
    # motifs comme exclusion Markdown globale est justifié, pas une sur-approximation.
    filtre = pytest.importorskip(
        "ggshield.core.filter", reason="ggshield est un outil de dev optionnel (voir capabilities.py)"
    )
    fichiers_markdown_reels = ["foo.md", "stories/bar.md", "evidence/reviews/x.md"]
    for motif in ("*", "**", "**/*", "**/**"):
        assert filtre.is_pattern_valid(motif)
        regexes = filtre.init_exclusion_regexes([motif])
        for fichier in fichiers_markdown_reels:
            assert any(regex.search(fichier) for regex in regexes), (
                f"{motif!r} devrait matcher {fichier!r} via le moteur GitGuardian réel"
            )


def test_gitguardian_yaml_reel_du_depot_toujours_conforme_apres_round77():
    # Non-régression directe sur le fichier réel du dépôt, après le round 77 (exclusion totale
    # du dépôt reconnue comme exclusion Markdown globale) : le verdict ne doit rien changer.
    ok, motifs = check_gitguardian_scope.verifier(REPO / ".gitguardian.yaml")
    assert ok is True, f"exclusion(s) markdown globale(s) réintroduite(s) : {motifs}"


def test_detecte_glob_wildcard_inedit_excluant_tout_le_markdown(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 78, GPT-5.6-Terra-Pro) : les rounds
    # 73/77 avaient étendu une liste FINIE de chaînes littérales reconnues — approche condamnée
    # à rater toute NOUVELLE construction glob valide. `**/*.m*` (exemple réel du reviewer)
    # utilise UNIQUEMENT les deux vrais méta-caractères GitGuardian (`*`/`**/`) et matche
    # pourtant tout fichier `.md` réel — vérifié RÉELLEMENT contre le moteur
    # `ggshield.core.filter` (venv scratch). `est_exclusion_markdown_globale()` traduit
    # désormais tout motif en regex (vendorisation fidèle de l'algorithme réel) et teste s'il
    # matche un échantillon représentatif de chemins Markdown — approche COMPUTATIONNELLE, pas
    # une liste de chaînes à faire grossir indéfiniment.
    assert check_gitguardian_scope.est_exclusion_markdown_globale("**/*.m*") is True
    assert check_gitguardian_scope.est_exclusion_markdown_globale("**/*.*") is True
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  ignored_paths:\n    - "**/*.m*"\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.m*"]


def test_traduction_glob_vendorisee_identique_au_moteur_ggshield_reel():
    # Preuve que la vendorisation (`_traduire_pattern_glob_ggshield`) est FIDÈLE au moteur réel
    # de GitGuardian, pas une réimplémentation approximative — comparaison BYTE-POUR-BYTE des
    # regex produites, sur un échantillon couvrant toutes les formes déjà rencontrées dans
    # cette story (littérales, méta-caractères seuls, bornées, inédites). Skip propre si
    # `ggshield` absent, jamais une dépendance du produit.
    filtre = pytest.importorskip(
        "ggshield.core.filter", reason="ggshield est un outil de dev optionnel (voir capabilities.py)"
    )
    candidats = [
        "**/*.md",
        "*.md",
        "*",
        "**",
        "**/*",
        "**/**",
        "**/*.m*",
        "**/*.*",
        "evidence/reviews/**/*.md",
        "tests/fixtures/exemple.md",
        "stories/*",
        "**/*.py",
    ]
    for candidat in candidats:
        assert check_gitguardian_scope._traduire_pattern_glob_ggshield(candidat) == filtre.translate_user_pattern(
            candidat
        ), candidat
        assert check_gitguardian_scope._pattern_glob_ggshield_valide(
            candidat
        ) == filtre.is_pattern_valid(candidat), candidat


def test_ne_detecte_pas_un_glob_borne_meme_avec_wildcard_supplementaire():
    # Non-régression : un glob borné à un sous-arbre précis, même enrichi d'un wildcard
    # supplémentaire (`**/*.py`, autre extension), reste correctement `False` — l'approche
    # computationnelle ne sur-détecte pas.
    for chemin in ("**/*.py", "stories/*", "evidence/reviews/**/*.m*"):
        assert check_gitguardian_scope.est_exclusion_markdown_globale(chemin) is False, chemin


def test_gitguardian_yaml_reel_du_depot_toujours_conforme_apres_round78():
    # Non-régression directe sur le fichier réel du dépôt, après le round 78 (détection
    # computationnelle via traduction glob→regex, plus une liste de chaînes littérales) : le
    # verdict ne doit rien changer.
    ok, motifs = check_gitguardian_scope.verifier(REPO / ".gitguardian.yaml")
    assert ok is True, f"exclusion(s) markdown globale(s) réintroduite(s) : {motifs}"


def test_parser_resout_alias_utilise_comme_nom_de_cle_explicite(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 80, GPT-5.6-Terra-Pro) : un alias YAML
    # peut être utilisé comme NOM DE CLÉ explicite (`? *k`, où `&k` ancre la chaîne littérale
    # `"ignored_paths"` ailleurs dans le fichier) — YAML valide, vérifié empiriquement contre
    # PyYAML : GitGuardian résout alors `secret.ignored_paths` normalement. Le cliquet
    # comparait le texte BRUT capturé (`"*k"` littéral) à `"ignored_paths"`, jamais résolu via
    # la table d'ancres.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'nom: &k ignored_paths\nsecret:\n  ? *k\n  :\n    - >-\n      **/*.md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_resout_alias_utilise_comme_nom_de_cle_bloc_non_explicite(tmp_path):
    # Même famille, forme BLOC non explicite (`*k:` directement, sans `?`) — YAML également
    # valide, vérifié empiriquement contre PyYAML, même mécanisme de résolution
    # (`_decoder_nom_cle` reçoit désormais `ancres`).
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'nom: &k ignored_paths\nsecret:\n  *k:\n    - >-\n      **/*.md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_alias_nom_de_cle_combine_avec_alias_valeur_flow(tmp_path):
    # Non-régression/généralisation : le nom de clé ET la valeur sont TOUS DEUX exprimés par
    # alias sur la même ligne — les deux résolutions (round précédent pour la valeur, round 80
    # pour le nom) doivent coopérer sans se marcher dessus.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'nomcle: &k ignored_paths\nmd: &md >-\n  **/*.md\nsecret:\n  *k: [*md]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_ancre_liste_non_resolue_comme_nom_de_cle_reste_litterale(tmp_path):
    # Non-régression : une ancre dont la valeur est une LISTE (pas un scalaire) ne peut
    # sémantiquement pas servir de nom de clé — `_decoder_nom_cle` ne la résout pas (repli sur
    # le texte brut `*k`), comportement inchangé, aucune fausse résolution.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'k: &k\n  - a\n  - b\nsecret:\n  ignored_paths:\n    - safe\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_gitguardian_yaml_reel_du_depot_toujours_conforme_apres_round80():
    # Non-régression directe sur le fichier réel du dépôt, après le round 80 (alias résolu
    # comme nom de clé `ignored_paths`, via `_decoder_nom_cle(..., ancres)`) : le verdict ne
    # doit rien changer.
    ok, motifs = check_gitguardian_scope.verifier(REPO / ".gitguardian.yaml")
    assert ok is True, f"exclusion(s) markdown globale(s) réintroduite(s) : {motifs}"


def test_parser_resout_alias_utilise_comme_nom_de_cle_racine_secret(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 81, GPT-5.6-Terra-Pro) — EXACTEMENT la
    # limite documentée au round 80 : un alias YAML utilisé comme nom de la clé RACINE `secret`
    # elle-même (`*k:` où `&k` ancre la chaîne `"secret"`) n'était pas résolu, contrairement au
    # nom de `ignored_paths` (round 80). Reproduction exacte du reviewer, vérifiée
    # empiriquement contre PyYAML.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'nom: &k secret\n*k:\n  ignored_paths:\n    - >-\n      **/*.md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_resout_alias_utilise_comme_nom_de_cle_racine_explicite(tmp_path):
    # Même famille, forme EXPLICITE de la clé racine (`? *k\n:`) — YAML également valide,
    # vérifiée empiriquement contre PyYAML.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'nom: &k secret\n? *k\n:\n  ignored_paths:\n    - >-\n      **/*.md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_resout_alias_nom_de_cle_racine_combine_avec_fusion(tmp_path):
    # Non-régression/généralisation : la clé racine ALIASÉE porte elle-même une FUSION
    # (`<<: *cfg`) — deux mécanismes distincts (round 81 pour le nom, round 31/56/72 pour la
    # fusion) doivent coopérer correctement, sans threading supplémentaire spécifique à cette
    # combinaison (ressort naturellement de l'extension `ancres` déjà en place).
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'nom: &k secret\ncfg: &cfg\n  ignored_paths:\n    - >-\n      **/*.md\n*k:\n  <<: *cfg\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_alias_nom_de_cle_racine_homonyme_hors_secret_reste_ignore(tmp_path):
    # Non-régression : un alias résolvant vers un nom SANS RAPPORT (`"autre"`, pas `"secret"`)
    # ne doit pas être confondu avec la clé racine — le vrai `secret` (littéral, plus loin)
    # reste la seule occurrence pertinente.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'nom: &k autre\n*k:\n  ignored_paths:\n    - safe\nsecret:\n  ignored_paths:\n    - >-\n      **/*.md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_gitguardian_yaml_reel_du_depot_toujours_conforme_apres_round81():
    # Non-régression directe sur le fichier réel du dépôt, après le round 81 (alias résolu
    # comme nom de la clé RACINE `secret` elle-même, `ancres` transmis à travers
    # `_est_descendante_de_secret`/`_est_ligne_secret_explicite`/`_noms_ancres_aliasees_secret`
    # et consorts) : le verdict ne doit rien changer.
    ok, motifs = check_gitguardian_scope.verifier(REPO / ".gitguardian.yaml")
    assert ok is True, f"exclusion(s) markdown globale(s) réintroduite(s) : {motifs}"


def test_parser_resout_alias_nom_de_cle_ignored_paths_dans_mapping_flow(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 82, GPT-5.6-Terra-Pro) :
    # `_resoudre_ignored_paths_dans_mapping_flow()` RECEVAIT déjà `ancres` (utilisé pour
    # résoudre la VALEUR) mais ne le transmettait pas à `_decoder_nom_cle()` pour le NOM de
    # clé — un alias utilisé comme nom `ignored_paths` DANS un mapping flow (`{*k: [*md]}`, où
    # `&k` ancre `"ignored_paths"`) n'était donc pas résolu, contrairement aux formes
    # bloc/explicite (round 80). Reproduction exacte du reviewer, vérifiée empiriquement
    # contre PyYAML.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'nom: &k ignored_paths\nmd: &md >-\n  **/*.md\nsecret: {*k: [*md]}\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_resout_alias_nom_de_cle_flow_via_ancre_indirecte(tmp_path):
    # Non-régression/généralisation : le même mécanisme, atteint via le pré-passage round 57
    # (ancre-mapping-flow référencée par un alias racine indirect) plutôt que directement à la
    # racine — même fonction partagée (`_resoudre_ignored_paths_dans_mapping_flow`), corrigée
    # une seule fois pour les deux chemins d'appel.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'nom: &k ignored_paths\nmd: &md >-\n  **/*.md\ncfg: &cfg {*k: [*md]}\nsecret: *cfg\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_gitguardian_yaml_reel_du_depot_toujours_conforme_apres_round82():
    # Non-régression directe sur le fichier réel du dépôt, après le round 82 (alias résolu
    # comme nom de clé `ignored_paths` DANS un mapping flow) : le verdict ne doit rien changer.
    ok, motifs = check_gitguardian_scope.verifier(REPO / ".gitguardian.yaml")
    assert ok is True, f"exclusion(s) markdown globale(s) réintroduite(s) : {motifs}"


def test_est_descendante_de_secret_ignore_marqueur_ancre_dans_cle_guillemetee(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 83, GPT-5.6-Terra-Pro) : la remontée
    # d'ascendance de `_est_descendante_de_secret()` scannait la ligne parente via
    # `_DEF_ANCRE.finditer()` BRUT, sans filtrer les spans guillemetés — contrairement à TOUTE
    # autre reconnaissance d'ancre du fichier. Un marqueur `&nom` à l'intérieur d'une chaîne
    # guillemetée SANS RAPPORT (une clé littéralement nommée `"&cfg"`, pas une vraie ancre)
    # pouvait donc être confondu avec une VRAIE ancre équivalente à `secret`. Reproduction
    # construite et vérifiée empiriquement contre PyYAML (le YAML suggéré par le reviewer était
    # lui-même invalide — corrigé en une forme équivalente valide).
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        '"&cfg":\n  ignored_paths:\n    - safe\ncfg: &cfg\n  ignored_paths:\n    - >-\n      **/*.md\nsecret: *cfg\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_est_descendante_de_secret_ignore_marqueur_ancre_dans_commentaire(tmp_path):
    # Même famille : un marqueur `&nom` DANS un commentaire (même bug que rounds 23/24 pour
    # `_construire_table_ancres`, jamais rétro-appliqué à cette fonction jusqu'ici).
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'other: # &cfg\n  ignored_paths:\n    - safe\ncfg: &cfg\n  ignored_paths:\n    - >-\n      **/*.md\nsecret: *cfg\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_est_descendante_de_secret_vraie_ancre_fonctionne_toujours(tmp_path):
    # Non-régression : une VRAIE définition d'ancre (non guillemetée, hors commentaire) reste
    # correctement reconnue par la remontée d'ascendance après le passage à
    # `_trouver_definition_ancre_valide()`.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'cfg: &cfg\n  ignored_paths:\n    - >-\n      **/*.md\nsecret: *cfg\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_gitguardian_yaml_reel_du_depot_toujours_conforme_apres_round83():
    # Non-régression directe sur le fichier réel du dépôt, après le round 83 (marqueur d'ancre
    # dans une chaîne guillemetée/un commentaire n'est plus confondu avec une vraie ancre lors
    # de la remontée d'ascendance) : le verdict ne doit rien changer.
    ok, motifs = check_gitguardian_scope.verifier(REPO / ".gitguardian.yaml")
    assert ok is True, f"exclusion(s) markdown globale(s) réintroduite(s) : {motifs}"


def test_filet_ne_bloque_plus_un_motif_interdit_cite_dans_un_commentaire(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 84, GPT-5.6-Terra-Pro) : le filet
    # textuel (`_chaines_guillemetees_decodees()`) balayait TOUTES les chaînes guillemetées du
    # texte brut sans exclure celles situées à l'intérieur d'un COMMENTAIRE — un commentaire
    # documentaire citant le motif interdit à titre d'exemple (`# exemple "**/*.md"`) bloquait
    # donc à tort un `.gitguardian.yaml` par ailleurs parfaitement conforme. Un commentaire
    # n'est JAMAIS une donnée YAML active pour aucun parseur conforme — l'exclure ne réduit
    # donc pas la couverture réelle du filet.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  ignored_paths:\n    - safe\n# exemple "**/*.md"\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_filet_detecte_toujours_un_motif_interdit_actif_sans_commentaire(tmp_path):
    # Non-régression : une chaîne guillemetée ACTIVE (pas dans un commentaire) portant le motif
    # interdit, à l'intérieur de la session `secret`, reste détectée normalement — le filet
    # garde sa couverture réelle DANS son périmètre (round 89 : reproduction déplacée d'une clé
    # racine SANS RAPPORT vers une clé nichée SOUS `secret`, la clé racine sans rapport n'étant
    # plus un faux positif depuis le correctif réel du round 89 — voir
    # `test_filet_ne_bloque_plus_une_cle_racine_sans_rapport_avec_secret`).
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  note: "**/*.md"\n  ignored_paths:\n    - safe\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_filet_detecte_motif_interdit_actif_precedant_un_commentaire_meme_ligne(tmp_path):
    # Non-régression : une chaîne guillemetée ACTIVE suivie d'un commentaire sur la MÊME ligne
    # reste détectée — seule la partie APRÈS le `#` est exclue, pas la valeur active qui la
    # précède (round 89 : reproduction déplacée sous `secret`, même raison que ci-dessus).
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  note: "**/*.md" # actif malgré le commentaire après\n  ignored_paths:\n    - safe\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_filet_ne_bloque_plus_une_cle_racine_sans_rapport_avec_secret(tmp_path):
    # RC1-015 round 89, correctif RÉEL du finding round 87/89 (revue scellée
    # GPT-5.6-Terra-Pro) : une clé racine SANS RAPPORT avec `secret.ignored_paths` (ex. `note`)
    # ne bloque plus à tort une configuration par ailleurs conforme — le filet se restreint
    # désormais à la session du mapping racine `secret` quand elle est délimitable sans
    # ambiguïté (`_lignes_dans_bloc_secret_racine`).
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'note: "**/*.md"\nsecret:\n  ignored_paths:\n    - safe\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_gitguardian_yaml_reel_du_depot_toujours_conforme_apres_round84():
    # Non-régression directe sur le fichier réel du dépôt, après le round 84 (filet textuel
    # exclut les chaînes guillemetées à l'intérieur d'un commentaire) : le verdict ne doit rien
    # changer.
    ok, motifs = check_gitguardian_scope.verifier(REPO / ".gitguardian.yaml")
    assert ok is True, f"exclusion(s) markdown globale(s) réintroduite(s) : {motifs}"


def test_pyyaml_reel_refute_nom_de_cle_multiligne_dans_mapping_flow():
    # Réfutation avec preuve d'un finding majeur (RC1-015 round 85, revue scellée
    # GPT-5.6-Terra-Pro) : le finding évoquait un nom de clé `ignored_paths` double-guillemets
    # RÉPARTI SUR PLUSIEURS LIGNES au sein d'un mapping FLOW (`{"ignored_\` + continuation
    # échappée + `paths": [...]}`), non couvert par `_NOM_CLE_QUELCONQUE_FLOW` (sans
    # `re.DOTALL`). La reproduction fournie était elle-même invalide YAML. Vérifié
    # EMPIRIQUEMENT (skip propre si `pyyaml` absent — dépendance CI du job `tests`, pas du
    # produit) que PyYAML rejette catégoriquement TOUT nom de clé guillemets multi-ligne dans
    # un mapping flow, quelle que soit la syntaxe exacte — et même en syntaxe BLOC classique
    # (non explicite). SEULE la forme EXPLICITE (`? "nom\\n"\n:`) le supporte, déjà gérée
    # depuis les rounds 58/63. Aucune construction YAML valide ne peut donc exploiter cette
    # forme dans un mapping flow.
    yaml = pytest.importorskip("yaml", reason="pyyaml est installé par le job `tests` de la CI")

    # Reproduction exacte du reviewer : invalide.
    with pytest.raises(yaml.YAMLError):
        yaml.safe_load('md: &md >-\n  **/*.md\nsecret: {"ignored_\\\n  paths": [*md]}\n')  # proof:allow — clé de schéma YAML, pas un secret réel

    # Variantes sans continuation échappée (simple fold, autre indentation) : invalides aussi.
    for texte in (
        'secret: {"ignored_\\\n paths": safe}\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        'secret: {"ignored\n_paths": safe}\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        "secret: {'ignored\n_paths': safe}\n",  # proof:allow — clé de schéma YAML, pas un secret réel
    ):
        with pytest.raises(yaml.YAMLError):
            yaml.safe_load(texte)

    # Même en syntaxe BLOC non explicite (pas seulement flow) : invalide aussi.
    with pytest.raises(yaml.YAMLError):
        yaml.safe_load('secret:\n  "ignored_\\\n    paths": safe\n')  # proof:allow — clé de schéma YAML, pas un secret réel

    # Seule la forme EXPLICITE le supporte — déjà couverte depuis les rounds 58/63.
    assert yaml.safe_load('? "ignored_\\\n  paths"\n: safe\n') == {"ignored_paths": "safe"}


def test_read_text_normalise_toujours_les_fins_de_ligne_avant_analyse(tmp_path):
    # Réfutation avec preuve d'un finding majeur (RC1-015 round 86, revue scellée
    # GPT-5.6-Terra-Pro) : le finding évoquait un fichier `.gitguardian.yaml` en fins de ligne
    # CRLF, où les positions absolues calculées par `_position_debut_ligne()`/les boucles
    # `offset += len(ligne) + 1` (qui supposent un séparateur `\n` D'UN SEUL CARACTÈRE)
    # dériveraient d'un octet par ligne précédente par rapport aux positions RÉELLES dans
    # `texte` (CRLF = deux caractères). Vérifié EMPIRIQUEMENT que cette hypothèse est
    # STRUCTURELLEMENT IMPOSSIBLE : `Path.read_text()` (les deux appels de ce fichier, aucun ne
    # passe de paramètre `newline`) utilise le mode « universal newlines » par défaut de
    # Python, qui normalise SILENCIEUSEMENT `\r\n` ET `\r` seul en `\n` DÈS LA LECTURE — quelle
    # que soit la convention de fin de ligne réelle du fichier sur disque, `texte` ne peut
    # jamais contenir de caractère `\r`.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_bytes(b"a: 1\rb: 2\r\nc: 3\nd: 4\r")
    texte_lu = fichier.read_text(encoding="utf-8")
    assert "\r" not in texte_lu
    assert texte_lu == "a: 1\nb: 2\nc: 3\nd: 4\n"

    # Reproduction exacte du reviewer (fichier écrit en octets bruts CRLF) : détectée
    # correctement, l'exclusion globale portée par l'alias vers le scalaire bloc est bien vue.
    fichier_crlf = tmp_path / ".gitguardian-crlf.yaml"
    fichier_crlf.write_bytes(
        b"defaults: &md >-\r\n  **/*.md\r\nsecret:\r\n  ignored_paths: [*md]\r\n"  # proof:allow — clé de schéma YAML, pas un secret réel
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier_crlf) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier_crlf)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_pyyaml_reel_confirme_pourquoi_le_filet_suit_la_profondeur_flow_pas_lindentation():
    # RC1-015 round 87→89 : un correctif NAÏF (restreindre le filet aux lignes indentées, en
    # excluant toute ligne à indentation ZÉRO qui n'est pas elle-même la clé racine `secret`,
    # sur l'hypothèse que `ignored_paths` est toujours un DESCENDANT indenté de la clé racine)  # proof:allow — clé de schéma YAML, pas un secret réel
    # a été ÉCARTÉ round 87 : cette hypothèse est FAUSSE en YAML flow valide — une syntaxe flow
    # multiligne place ses lignes de continuation à indentation ZÉRO tout en restant un vrai
    # descendant de la clé racine. Vérifié empiriquement (skip propre si `pyyaml` absent —
    # dépendance CI du job `tests`, pas du produit).
    #
    # Le correctif RÉEL du round 89 (`_lignes_dans_bloc_secret_racine`) suit la PROFONDEUR FLOW
    # (`_profondeurs_flow`, déjà robuste depuis le round 35) plutôt que la seule indentation —
    # ce test prouve qu'il n'est PAS exposé au contre-exemple ci-dessus : la ligne de
    # continuation reste correctement détectée comme motif interdit.
    yaml = pytest.importorskip("yaml", reason="pyyaml est installé par le job `tests` de la CI")

    texte = 'secret: {\nignored_paths: ["**/*.md"]\n}\n'  # proof:allow — clé de schéma YAML, pas un secret réel
    assert yaml.safe_load(texte) == {"secret": {"ignored_paths": ["**/*.md"]}}

    import tempfile
    from pathlib import Path as _Path

    fichier = _Path(tempfile.mktemp(suffix=".yaml"))
    try:
        fichier.write_text(texte, encoding="utf-8")
        ok, motifs = check_gitguardian_scope.verifier(fichier)
        assert ok is False
        assert motifs == ["**/*.md"]
    finally:
        fichier.unlink(missing_ok=True)


def test_filet_replie_sur_balayage_integral_si_racine_secret_fournie_par_alias(tmp_path):
    # RC1-015 round 89 : quand la clé racine `secret` est fournie par ALIAS (valeur `*cfg`), le  # proof:allow — clé de schéma YAML, pas un secret réel
    # contenu réel du mapping vit ailleurs dans le fichier (potentiellement AVANT cette ligne) —
    # `_lignes_dans_bloc_secret_racine` ne peut PAS le délimiter par un balayage à sens unique et
    # retourne `None` : repli sur le balayage intégral (comportement identique à avant round 89),
    # jamais moins couvrant. Ici la clé racine sans rapport reste donc détectée (repli actif),
    # contrairement au cas simple (round 89, voir
    # `test_filet_ne_bloque_plus_une_cle_racine_sans_rapport_avec_secret`).
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'note: "**/*.md"\ncfg: &cfg\n  ignored_paths:\n    - safe\nsecret: *cfg\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_filet_replie_sur_balayage_integral_si_cle_racine_explicite_presente(tmp_path):
    # RC1-015 round 89 : la présence d'UNE SEULE clé racine en forme EXPLICITE (`? nom\n:`,
    # nom potentiellement `secret`) suffit à faire retourner `None` par
    # `_lignes_dans_bloc_secret_racine` (résolution du nom non dupliquée ici, par prudence) —
    # repli sur le balayage intégral. Ici la vraie clé racine `secret` est en forme bloc
    # classique ; SEULE une clé racine SANS RAPPORT (`autre`) est en forme explicite — le repli
    # reste correct et sûr (jamais moins couvrant qu'avant round 89).
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'note: "**/*.md"\n? autre\n: valeur\nsecret:\n  ignored_paths:\n    - safe\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_ggshield_reel_ignored_paths_seules_deux_formes_couvrent_tout_markdown():
    # Réfutation avec preuve d'un finding mineur (RC1-015 round 73, revue scellée
    # GPT-5.6-Terra-Pro) : « d'autres syntaxes de glob éventuellement acceptées par
    # GitGuardian et sémantiquement équivalentes (par exemple des classes de caractères dans
    # le suffixe) » pourraient ne pas être détectées par `est_exclusion_markdown_globale()`.
    # Vérifié FAUX contre le moteur RÉEL de GitGuardian (`ggshield.core.filter`, outil de dev
    # optionnel — SKIP si absent, jamais une dépendance du produit `dependencies=[]`) : son
    # `REGEX_SPECIAL_CHARS` échappe `[`, `]`, `{`, `}`, `?` en caractères LITTÉRAUX avant
    # compilation — seuls `*` et `**/` portent un sens de glob. Aucun des candidats
    # « classe de caractères » ci-dessous (dont l'exemple même suggéré par le finding,
    # `*.[m][d]`) ne matche donc un fichier Markdown réel via ce moteur : il n'y a rien à
    # détecter en plus dans CETTE dimension précise (classes de caractères) — round 77 a
    # depuis élargi les formes reconnues sur une dimension DIFFÉRENTE (exclusion totale du
    # dépôt), sans rapport avec ce test.
    filtre = pytest.importorskip(
        "ggshield.core.filter", reason="ggshield est un outil de dev optionnel (voir capabilities.py)"
    )
    candidats_hypothetiques = [
        "*.[m][d]",
        "**/*.[m]d",
        "*.{md}",
        "**/*.M?",
        "[Mm][Dd]/**",
        "**/*.m[d]",
    ]
    fichiers_markdown_reels = ["foo.md", "stories/bar.md", "evidence/reviews/x.md"]
    for candidat in candidats_hypothetiques:
        assert filtre.is_pattern_valid(candidat), f"{candidat!r} rejeté par ggshield lui-même"
        regexes = filtre.init_exclusion_regexes([candidat])
        for fichier in fichiers_markdown_reels:
            matche = any(regex.search(fichier) for regex in regexes)
            assert not matche, (
                f"{candidat!r} matche {fichier!r} via le moteur GitGuardian réel — "
                f"est_exclusion_markdown_globale() devrait alors le reconnaître aussi"
            )


def test_ggshield_reel_scalaire_explicite_nest_pas_une_exclusion_fonctionnelle(tmp_path):
    # RC1-015 round 108, revue scellée GPT-5.6-Terra-Pro (mineure, RÉFUTÉE avec preuve
    # exécutable réelle) : le cliquet ne traite pas `? ignored_paths\n: >-\n  **/*.md` (valeur
    # SCALAIRE bloc après le séparateur d'une clé explicite) — le reviewer note lui-même que
    # « l'acceptation de ce scalaire par le schéma précis GitGuardian n'est pas démontrée ».
    # PyYAML confirme la forme SYNTAXIQUEMENT valide (résout en `ignored_paths: '**/*.md'`, une
    # CHAÎNE, pas une liste) — mais ggshield RÉEL (v2.169.1, exécutable CLI, outil de dev
    # optionnel — SKIP si absent, jamais une dépendance du produit `dependencies=[]`) prouve que
    # cette forme n'exclut RIEN en pratique : comparaison directe de deux dépôts minimaux,
    # `ignored_paths` en LISTE propre exclut réellement `tests_docs/foo.md` du scan (absent de
    # `entities_with_incidents`), tandis que la MÊME forme en scalaire explicite laisse le
    # fichier scanné (présent dans `entities_with_incidents`) — GitGuardian exige une LISTE pour
    # `ignored_paths`, un scalaire nu est silencieusement ignoré. Le cliquet n'a donc aucune
    # raison de détecter cette forme : elle ne réintroduit aucun risque réel.
    import json
    import shutil
    import subprocess

    pytest.importorskip("ggshield", reason="ggshield est un outil de dev optionnel (voir capabilities.py)")
    executable = shutil.which("ggshield")
    if executable is None:
        pytest.skip(
            "exécutable ggshield introuvable sur PATH (outil de dev optionnel, voir "
            "evidence/registres/mission.jsonl seq 490 pour la justification round 108)"
        )

    def _scanner(nom_depot: str, config_yaml: str) -> list[str]:
        # Round 108 : `ggshield` applique `ignored_paths` par rapport à la RACINE scannée — le
        # chemin cible doit être « . » avec le répertoire courant DANS le dépôt (comme la
        # reproduction manuelle originale), pas un chemin absolu passé de l'extérieur, sous
        # peine de comparer `ignored_paths` à un chemin absolu qui ne matche jamais le glob.
        depot = tmp_path / nom_depot
        (depot / "tests_docs").mkdir(parents=True)
        (depot / "tests_docs" / "foo.md").write_text("contenu inoffensif\n", encoding="utf-8")
        (depot / ".gitguardian.yaml").write_text(config_yaml, encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(depot)], check=True)
        subprocess.run(["git", "-C", str(depot), "add", "-A"], check=True)
        rapport = depot / "rapport.json"
        subprocess.run(
            [executable, "secret", "scan", "path", "--recursive", "--yes",
             "--format", "json", "-o", str(rapport), "."],
            check=False, capture_output=True, text=True, cwd=str(depot),
        )
        donnees = json.loads(rapport.read_text(encoding="utf-8"))
        return [e["filename"] for e in donnees["entities_with_incidents"] if "foo.md" in e["filename"]]

    config_liste = 'version: 2\nsecret:\n  ignored_paths:\n    - "**/*.md"\n'  # proof:allow — clé de schéma YAML, pas un secret réel
    fichiers_liste = _scanner("depot-liste", config_liste)
    assert fichiers_liste == [], "ggshield devrait exclure foo.md avec ignored_paths en liste"

    config_scalaire = 'secret:\n  ? ignored_paths\n  : >-\n    **/*.md\n'  # proof:allow — clé de schéma YAML, pas un secret réel
    fichiers_scalaire = _scanner("depot-scalaire", config_scalaire)
    assert len(fichiers_scalaire) == 1, (
        "ggshield ne devrait PAS exclure foo.md avec ignored_paths en scalaire explicite "
        "(confirme que cette forme n'est pas une exclusion fonctionnelle)"
    )


# ---------------------------------------------------------------------------
# verifier() — vérification bout en bout
# ---------------------------------------------------------------------------

def test_verifier_echoue_si_exclusion_globale_presente(tmp_path):
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  ignored_paths:\n    - "tests/fixtures/**"\n    - "**/*.md"\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert "**/*.md" in motifs


def test_verifier_reussit_sans_exclusion_globale(tmp_path):
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  ignored_paths:\n    - "tests/fixtures/**"\n    - "LICENSE"\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_verifier_reussit_meme_avec_une_exclusion_de_sous_arbre_bornee(tmp_path):
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  ignored_paths:\n    - "evidence/reviews/**/*.md"\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True


def test_verifier_detecte_une_syntaxe_yaml_flow(tmp_path):
    # Syntaxe YAML "flow" valide (jamais rencontrée dans ce dépôt, block-style partout).
    # Depuis le round 12 (`_LIGNE_CLE_FLOW_OUVERTE`, étendue au texte complet round 17),
    # l'analyseur structurel couvre DIRECTEMENT ce cas (avant round 12 : hors de portée de
    # `_LIGNE_CLE`, seul le filet textuel brut la détectait).
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  ignored_paths: ["**/*.md"]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_verifier_filet_textuel_decode_un_point_echappe_en_unicode(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 7, GPT-5.6-Terra-Pro) : `"**/*.md"`
    # est sémantiquement `**/*.md` pour tout parseur YAML conforme (`.` = `.`), donc
    # réintroduirait l'exclusion globale sans être reconnu par une comparaison sur le texte brut
    # NON décodé. Le filet doit décoder les échappements `\uNNNN` avant de comparer.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  ignored_paths:\n    - "**/*\\u002emd"\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_verifier_filet_textuel_ne_confond_pas_un_glob_borne_avec_le_litteral_interdit(tmp_path):
    # Le filet textuel compare la valeur DÉCODÉE de chaque chaîne guillemetée, jamais un
    # sous-texte — sinon "evidence/reviews/**/*.md" (légitime, borné) serait un faux positif.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  ignored_paths:\n    - "evidence/reviews/**/*.md"\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_decoder_echappements_yaml_retombe_sur_la_valeur_brute_si_invalide():
    # `\u12zz` est un échappement `\uNNNN` TRONQUÉ (moins de 4 chiffres hexadécimaux valides) —
    # lève UnicodeDecodeError chez le décodeur Python sous-jacent. Le décodeur ne doit jamais
    # laisser fuir cette exception : il retombe sur la valeur brute plutôt que de faire planter
    # le gate sur une entrée YAML malformée.
    assert check_gitguardian_scope._decoder_echappements_yaml("a\\u12zzb") == "a\\u12zzb"


def test_verifier_filet_textuel_decode_un_slash_echappe(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 10, GPT-5.6-Terra-Pro) : `\/` est un
    # échappement YAML valide d'un `/` littéral (vérifié empiriquement contre PyYAML :
    # yaml.safe_load('secret:\n  ignored_paths:\n    - "**\\/*.md"\n') résout bien en  # proof:allow — clé de schéma YAML dans un commentaire, pas un secret réel
    # {'secret': {'ignored_paths': ['**/*.md']}}), mais l'ancien décodeur fondé sur
    # str.encode(...).decode("unicode_escape") sur la valeur ENTIÈRE ne reconnaît pas `\/`
    # (absent du jeu d'échappements Python) et le laissait tel quel.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  ignored_paths:\n    - "**\\/*.md"\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_decoder_echappements_yaml_ne_confond_pas_backslash_litteral_et_slash_echappe():
    # Non-régression de la conception en un seul passage (`_ECHAPPEMENT_YAML.sub`, jamais un
    # `.replace("\\/", "/")` post-hoc) : un `\\` authentique (backslash littéral échappé) suivi
    # d'un `/` littéral SÉPARÉ ne doit PAS être confondu avec l'échappement atomique `\/`. Le
    # `\\` consomme ses 2 caractères et redevient un unique `\`, laissant le `/` qui suit intact
    # comme caractère littéral (pas de fusion en un seul `/`).
    assert check_gitguardian_scope._decoder_echappements_yaml("a\\\\/b") == "a\\/b"


def test_verifier_filet_textuel_detecte_une_continuation_de_ligne_echappee(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 11, GPT-5.6-Terra-Pro) : un scalaire
    # double-guillemets YAML peut s'étendre sur PLUSIEURS lignes physiques via une continuation
    # de ligne échappée (`\` immédiatement suivi d'un saut de ligne) — le saut de ligne ET
    # l'indentation de tête de la ligne suivante sont retirés SANS espace de remplacement
    # (vérifié empiriquement contre PyYAML : yaml.safe_load résout ce cas en `**/*.md`). Ni
    # l'analyseur structurel (ligne par ligne, ne peut pas voir un item multi-ligne) ni l'ancien
    # filet (`_CHAINE_DOUBLE_GUILLEMETS` sans DOTALL, `.` ne matche pas `\n`) ne le détectaient.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  ignored_paths:\n    - "**/*.\\\n      md"\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_decoder_echappements_yaml_retire_indentation_de_la_ligne_de_continuation():
    # La continuation de ligne échappée retire aussi l'indentation de TÊTE de la ligne suivante
    # (pas seulement le saut de ligne lui-même) — sans quoi "**/*.\n      md" redeviendrait
    # "**/*.      md" (avec les espaces), jamais reconnu comme `**/*.md`.
    assert check_gitguardian_scope._decoder_echappements_yaml("a\\\n    b") == "ab"


# ---------------------------------------------------------------------------
# ancres/alias YAML (`&nom` / `*nom`) et syntaxe flow — round 12
# ---------------------------------------------------------------------------

def test_parser_resout_un_alias_flow_vers_une_ancre_scalaire_bloc(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 12, GPT-5.6-Terra-Pro) : une ancre YAML
    # (`&nom`) définie AILLEURS dans le fichier, référencée par alias (`*nom`) au sein d'une
    # liste `ignored_paths` en syntaxe flow, réintroduit sémantiquement l'exclusion globale sans
    # qu'aucun littéral `**/*.md` n'apparaisse dans le contexte `ignored_paths` — vérifié
    # empiriquement contre PyYAML (`yaml.safe_load` résout `ignored_paths: [*md]` en
    # `['**/*.md']` quand `&md` est ancré à un scalaire bloc `**/*.md`).
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md >-\n  **/*.md\nsecret:\n  ignored_paths: [*md]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_resout_un_alias_de_bloc_vers_une_ancre_guillemetee(tmp_path):
    # Même bug, alias exprimé comme item de BLOC (`- *nom`) plutôt qu'en syntaxe flow, ancre
    # définie sur une chaîne guillemetée plutôt qu'un scalaire bloc.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md "**/*.md"\nsecret:\n  ignored_paths:\n    - *md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_alias_ne_confond_pas_un_glob_borne_avec_le_litteral_interdit(tmp_path):
    # Non-régression : un alias résolu vers un glob BORNÉ légitime (evidence/reviews/**/*.md)
    # ne doit pas être classé comme exclusion globale.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &b >-\n  evidence/reviews/**/*.md\nsecret:\n  ignored_paths: [*b]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_alias_indefini_retombe_sur_le_jeton_brut_sans_planter(tmp_path):
    # Un alias référençant une ancre INDÉFINIE (YAML invalide en toute rigueur, mais notre
    # analyseur ne doit ni planter ni le confondre avec un motif interdit) retombe sur le jeton
    # brut (`*inconnu`), qui ne matche jamais `est_exclusion_markdown_globale`.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  ignored_paths: [*inconnu]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["*inconnu"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_flow_avec_plusieurs_items_guillemetes_et_virgule_interne(tmp_path):
    # `_decouper_liste_flow` doit respecter les guillemets : une virgule À L'INTÉRIEUR d'une
    # chaîne n'est pas un séparateur d'items.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  ignored_paths: ["a,b/**", "LICENSE"]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["a,b/**", "LICENSE"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


# ---------------------------------------------------------------------------
# tags YAML explicites (`!!str`) — round 13 (finding réfuté, comportement déjà correct)
# ---------------------------------------------------------------------------

def test_verifier_detecte_un_tag_explicite_suivi_d_une_chaine_guillemetee_en_bloc(tmp_path):
    # Round 13 (GPT-5.6-Terra-Pro, REJECT) : la reproduction EXACTE fournie par le reviewer
    # (`- !!str **/*.md`, SANS guillemets) est en réalité INVALIDE en YAML — vérifié
    # empiriquement : PyYAML lève `ScannerError` ("expected alphabetic or numeric character,
    # but found '*'"), car un scalaire NU (non guillemeté) ne peut jamais commencer par `*`
    # (réservé comme indicateur d'ALIAS par la grammaire YAML) — ceci est vrai pour TOUT
    # scalaire nu, tag ou non, et s'applique aux DEUX littéraux interdits (`**/*.md`, `*.md`),
    # qui commencent tous deux par `*`. Un tel item ne peut donc JAMAIS apparaître non guillemeté
    # en YAML valide.
    #
    # La variante réellement valide — `- !!str "**/*.md"` (tag + chaîne guillemetée) — est déjà
    # détectée SANS aucun changement de code : le filet `_chaines_guillemetees_decodees` balaie
    # l'intégralité du texte brut pour toute chaîne guillemetée, indépendamment d'un tag qui la
    # précède. Ce test verrouille et documente ce comportement déjà correct.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  ignored_paths:\n    - !!str "**/*.md"\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_verifier_detecte_un_tag_explicite_suivi_d_une_chaine_guillemetee_en_flow(tmp_path):
    # Même comportement déjà correct en syntaxe flow.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  ignored_paths: [!!str "**/*.md"]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_verifier_detecte_la_meme_ancre_reutilisee_par_deux_alias_distincts(tmp_path):
    # Round 14 (GPT-5.6-Terra-Pro, REJECT) : la reproduction fournie pour un « alias chaîné »
    # (`&b *a` — une ancre posée directement sur un alias existant) est en réalité INVALIDE en
    # YAML — vérifié empiriquement : PyYAML lève `ParserError` ("expected <block end>, but found
    # '<alias>'"). La grammaire YAML n'autorise pas d'attacher une propriété d'ancre à un nœud
    # qui est déjà entièrement un alias — un « chaînage » au sens du reviewer n'est donc pas
    # syntaxiquement exprimable. La forme réellement valide voisine — la MÊME ancre d'origine
    # réutilisée par deux alias DISTINCTS (pas un second nom d'ancre) — reste une résolution à
    # un seul niveau, déjà correcte sans changement de code. Ce test la verrouille.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &a >-\n  **/*.md\nautre: *a\nsecret:\n  ignored_paths: [*a]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_resout_une_ancre_tag_explicite_avant_scalaire_bloc(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 15, GPT-5.6-Terra-Pro) : un tag YAML
    # explicite (`!!str`) précédant un scalaire bloc ancré (`&nom !!str >-`) n'était pas résolu —
    # `_construire_table_ancres` stockait le texte brut `"!!str >-"` littéralement, empêchant
    # `_BLOC_ANCRE` de reconnaître l'indicateur de scalaire bloc juste après. Vérifié
    # empiriquement contre PyYAML : `defaults: &md !!str >-\n  **/*.md` résout bien l'ancre en
    # `**/*.md`.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md !!str >-\n  **/*.md\nsecret:\n  ignored_paths: [*md]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_resout_une_ancre_tag_explicite_avant_chaine_guillemetee(tmp_path):
    # Même bug, tag suivi d'une chaîne guillemetée (pas un scalaire bloc) sur l'ancre.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md !!str "**/*.md"\nsecret:\n  ignored_paths: [*md]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_ancre_tag_explicite_ne_confond_pas_un_glob_borne(tmp_path):
    # Non-régression : une ancre taguée résolue vers un glob BORNÉ légitime reste conforme.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &b !!str >-\n  evidence/reviews/**/*.md\nsecret:\n  ignored_paths: [*b]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_ancre_nom_avec_point_est_capture_integralement_round20():
    # Round 16 (GPT-5.6-Terra-Pro, REJECT) avait été RÉFUTÉ : `&md.glob` semblait invalide car
    # PyYAML lève `ScannerError` dessus. Round 20 (GPT-5.6-Terra-Pro, REJECT, même reproduction)
    # a forcé une vérification plus poussée qui a INFIRMÉ cette conclusion : le source de PyYAML
    # documente explicitement que sa restriction ([A-Za-z0-9_-]) est un choix de
    # désambiguïsation PyYAML, PAS une exigence de la spec YAML (6.9.2 : ns-anchor-char exclut
    # seulement les indicateurs flow `,[]{}` et les blancs — un point est parfaitement valide
    # selon le spec). `_DEF_ANCRE`/`_REF_ALIAS` capturent désormais le jeu de caractères
    # spec-conforme (`_CARACTERE_ANCRE`, borné aux terminateurs reconnus par le scanner PyYAML
    # lui-même). Ce test verrouille le comportement CORRIGÉ ; les formes déjà valides restent
    # gérées identiquement.
    assert check_gitguardian_scope._DEF_ANCRE.search("&md.glob").group(1) == "md.glob"
    assert check_gitguardian_scope._REF_ALIAS.match("*md.glob") is not None
    assert check_gitguardian_scope._DEF_ANCRE.search("&md_glob").group(1) == "md_glob"
    assert check_gitguardian_scope._DEF_ANCRE.search("&md-glob").group(1) == "md-glob"
    assert check_gitguardian_scope._DEF_ANCRE.search("&md1").group(1) == "md1"
    assert check_gitguardian_scope._REF_ALIAS.match("*md_glob") is not None
    # terminateurs spec/PyYAML toujours respectés : le nom s'arrête au premier caractère exclu
    assert check_gitguardian_scope._DEF_ANCRE.search("&md:x").group(1) == "md"
    assert check_gitguardian_scope._DEF_ANCRE.search("&md,x").group(1) == "md"
    assert check_gitguardian_scope._DEF_ANCRE.search("&md]x").group(1) == "md"


def test_verifier_resout_un_alias_dont_le_nom_d_ancre_contient_un_point(tmp_path):
    # Reproduction exacte du round 20 (identique au round 16, mais avec la conclusion corrigée) :
    # `defaults: &md.glob >-\n  **/*.md\nsecret:\n  ignored_paths: [*md.glob]\n` est un YAML  # proof:allow — clé de schéma YAML dans un commentaire, pas un secret réel
    # spec-conforme (un point est un `ns-anchor-char` valide) — l'alias `*md.glob` doit
    # maintenant se résoudre en `**/*.md`.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md.glob >-\n  **/*.md\nsecret:\n  ignored_paths: [*md.glob]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


# ---------------------------------------------------------------------------
# syntaxe flow multi-ligne + tag sur item de bloc direct — round 17
# ---------------------------------------------------------------------------

def test_parser_resout_une_liste_flow_repartie_sur_plusieurs_lignes(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 17, GPT-5.6-Terra-Pro) : une liste YAML
    # flow VALIDE peut s'étendre sur plusieurs lignes physiques (`ignored_paths: [\n  *md\n]`) —
    # hors de portée de l'ancienne regex `_LIGNE_CLE_FLOW` (round 12), ancrée à une seule ligne
    # (`^...\[(.*)\]...$`). Vérifié empiriquement contre PyYAML : résout bien `ignored_paths` en
    # `['**/*.md']`. Corrigé en détectant la syntaxe flow sur le TEXTE COMPLET
    # (`_LIGNE_CLE_FLOW_OUVERTE` + `_trouver_fermeture_flow`, quote-aware, pas ligne par ligne).
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md >-\n  **/*.md\nsecret:\n  ignored_paths: [\n    *md\n  ]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_flow_multi_ligne_ne_confond_pas_un_glob_borne(tmp_path):
    # Non-régression : une liste flow multi-ligne résolue vers un glob BORNÉ légitime reste
    # conforme.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  ignored_paths: [\n    "evidence/reviews/**/*.md"\n  ]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_resout_un_tag_explicite_avant_scalaire_bloc_sur_item_direct(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 17, Qwen3.7-Max) : un tag YAML explicite
    # (`!!str`) précédant un scalaire bloc sur un ITEM DIRECT de `ignored_paths` (`- !!str >-`,
    # pas une définition d'ancre) n'était pas reconnu par `_LIGNE_ITEM_BLOC` — le round 15 avait
    # corrigé ce cas pour `_construire_table_ancres` (ancres) mais pas pour les items directs de
    # bloc. Vérifié empiriquement contre PyYAML : `- !!str >-\n  **/*.md` résout bien en
    # `**/*.md`.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  ignored_paths:\n    - !!str >-\n      **/*.md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_tag_sur_item_direct_ne_confond_pas_un_glob_borne(tmp_path):
    # Non-régression : un item taggé résolu vers un glob BORNÉ légitime reste conforme.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  ignored_paths:\n    - !!str >-\n      evidence/reviews/**/*.md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


# ---------------------------------------------------------------------------
# faux positif structurel : contenu d'un scalaire bloc sans rapport — round 18
# ---------------------------------------------------------------------------

def test_parser_ignore_une_fausse_cle_flow_dans_le_contenu_d_un_autre_scalaire_bloc(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 18, GPT-5.6-Terra-Pro) : la recherche de
    # `ignored_paths: [` introduite au round 17 balayait le TEXTE ENTIER sans distinguer une
    # vraie clé YAML du CONTENU d'un scalaire bloc d'une clé sans rapport. Un YAML valide comme
    # `note: |-\n  ignored_paths: [safe]\nsecret:\n  ignored_paths:\n    - *md` fait matcher la  # proof:allow — clé de schéma YAML dans un commentaire, pas un secret réel
    # ligne de contenu du bloc `note` en premier, retournant `['safe']` — la VRAIE liste
    # `secret.ignored_paths` (résolue via alias vers `**/*.md`) n'était alors jamais examinée.
    # Vérifié empiriquement contre PyYAML. Corrigé : `_lignes_contenu_bloc` exclut désormais
    # toute ligne qui est le contenu d'un AUTRE scalaire bloc (mapping ou item de liste) avant
    # toute recherche structurelle de la clé `ignored_paths`.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md >-\n  **/*.md\nnote: |-\n  ignored_paths: [safe]\nsecret:\n  ignored_paths:\n    - *md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_ignore_une_fausse_cle_flow_dans_un_item_de_liste_bloc(tmp_path):
    # Même bug, contenu déceptif dans le scalaire bloc d'un ITEM DE LISTE (pas une clé de
    # mapping) sans rapport.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'other:\n  - >-\n    ignored_paths: [safe]\nsecret:\n  ignored_paths:\n    - "**/*.md"\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_fausse_cle_flow_dans_bloc_ne_masque_pas_un_glob_borne_reel(tmp_path):
    # Non-régression : quand la VRAIE liste (après exclusion de la fausse clé) est un glob
    # BORNÉ légitime, le résultat reste conforme.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'note: |-\n  ignored_paths: [safe]\nsecret:\n  ignored_paths: ["evidence/reviews/**/*.md"]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["evidence/reviews/**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


# ---------------------------------------------------------------------------
# clé `ignored_paths` homonyme sous un autre parent — round 19
# ---------------------------------------------------------------------------

def test_parser_ignore_une_cle_ignored_paths_homonyme_flow_sous_un_autre_parent(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 19, GPT-5.6-Terra-Pro) : le cliquet
    # analysait la PREMIÈRE clé `ignored_paths` rencontrée dans le fichier, sans vérifier son
    # appartenance au mapping `secret`. Un YAML valide où une clé `ignored_paths` homonyme
    # existe sous un AUTRE parent (`autre:`), placée AVANT la vraie `secret.ignored_paths`,
    # masquait donc la vraie liste (ici résolue via un alias vers un scalaire bloc — le filet
    # de chaînes guillemetées ne peut structurellement pas la rattraper, la valeur n'étant
    # jamais guillemetée). Vérifié empiriquement contre PyYAML.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md >-\n  **/*.md\nautre:\n  ignored_paths: [safe]\nsecret:\n  ignored_paths: [*md]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_ignore_une_cle_ignored_paths_homonyme_bloc_sous_un_autre_parent(tmp_path):
    # Même bug, forme BLOC (pas flow) pour la fausse clé homonyme.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'autre:\n  ignored_paths:\n    - "safe"\nsecret:\n  ignored_paths:\n    - "**/*.md"\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_cle_homonyme_ne_masque_pas_un_glob_borne_reel(tmp_path):
    # Non-régression : quand la VRAIE liste (sous le mapping secret) est un glob BORNÉ légitime,
    # malgré une clé homonyme AVANT elle sous un autre parent, le résultat reste conforme.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'autre:\n  ignored_paths: ["safe"]\nsecret:\n  ignored_paths: ["evidence/reviews/**/*.md"]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["evidence/reviews/**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_ignore_une_fausse_hierarchie_secret_ignored_paths_dans_un_scalaire_bloc(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 22, GPT-5.6-Terra-Pro) : le correctif du
    # round 18 (`lignes_exclues`, contenu d'un scalaire bloc sans rapport) n'était appliqué QUE
    # dans la boucle de recherche flow, pas dans la boucle block-style qui cherche `_LIGNE_CLE`.
    # Un scalaire bloc sans rapport (`note: |-`) peut donc contenir une FAUSSE hiérarchie
    # complète — la clé `secret` suivie de sa propre sous-clé `ignored_paths: [safe]` — que la
    # boucle block-style reconnaissait à tort comme la vraie liste —
    # `_est_descendante_de_secret()` trouvait bien une occurrence précédente de la clé `secret`,
    # mais c'était la FAUSSE occurrence, à l'intérieur du scalaire bloc. Vérifié empiriquement
    # contre PyYAML.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'note: |-\n  secret:\n    ignored_paths:\n      - safe\ndefaults: &md >-\n  **/*.md\nsecret:\n  ignored_paths:\n    - *md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_fausse_hierarchie_dans_bloc_ne_masque_pas_un_glob_borne_reel(tmp_path):
    # Non-régression : quand la VRAIE liste (après exclusion de la fausse hiérarchie) est un
    # glob BORNÉ légitime, le résultat reste conforme.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'note: |-\n  secret:\n    ignored_paths:\n      - safe\nsecret:\n  ignored_paths:\n    - "evidence/reviews/**/*.md"\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["evidence/reviews/**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_ignore_un_marqueur_ancre_a_l_interieur_d_une_chaine_ordinaire(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 23, GPT-5.6-Terra-Pro) : un `&nom`
    # apparaissant À L'INTÉRIEUR d'une chaîne guillemetée ORDINAIRE (texte littéral, pas une
    # vraie définition d'ancre) écrasait à tort une ancre légitime définie plus tôt dans le
    # fichier. `note: "&md safe"` n'est PAS une redéfinition de `&md` — YAML l'ignore
    # entièrement (les guillemets rendent tout le contenu littéral, aucune syntaxe d'ancre n'y
    # est interprétée). Vérifié empiriquement contre PyYAML : `*md` résout bien vers `**/*.md`
    # (la VRAIE ancre, définie avant `note`), pas vers le texte de `note`.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md >-\n  **/*.md\nnote: "&md safe"\nsecret:\n  ignored_paths: [*md]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_marqueur_ancre_dans_chaine_ne_masque_pas_un_glob_borne_reel(tmp_path):
    # Non-régression : quand la VRAIE ancre résout vers un glob BORNÉ légitime, malgré un faux
    # marqueur d'ancre dans une chaîne ordinaire placée entre les deux, le résultat reste
    # conforme.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md >-\n  evidence/reviews/**/*.md\nnote: "&md safe"\nsecret:\n  ignored_paths: [*md]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_ignore_un_marqueur_ancre_a_l_interieur_d_un_commentaire(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 24, GPT-5.6-Terra-Pro) : même bug que le
    # round 23, mais pour un `&nom` apparaissant dans un COMMENTAIRE (`# &md safe`) plutôt qu'une
    # chaîne guillemetée. `# &md safe` est un commentaire YAML — le `&md` qu'il contient n'est
    # pas une redéfinition. Vérifié empiriquement contre PyYAML : `*md` résout bien vers la VRAIE
    # ancre définie avant le commentaire.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md >-\n  **/*.md\n# &md safe\nsecret:\n  ignored_paths: [*md]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_marqueur_ancre_dans_commentaire_ne_masque_pas_un_glob_borne_reel(tmp_path):
    # Non-régression : quand la VRAIE ancre résout vers un glob BORNÉ légitime, malgré un faux
    # marqueur d'ancre dans un commentaire placé entre les deux, le résultat reste conforme.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md >-\n  evidence/reviews/**/*.md\n# &md safe\nsecret:\n  ignored_paths: [*md]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_ignore_un_marqueur_ancre_a_l_interieur_d_un_scalaire_bloc_sans_rapport(tmp_path):
    # Bug réel trouvé PROACTIVEMENT (RC1-015, même famille que les rounds 23/24, avant qu'un
    # round de revue supplémentaire ne le relève) : un `&nom` apparaissant dans le CONTENU d'un
    # scalaire bloc d'une AUTRE clé (`note: |-\n  &md safe`) souffrait de la même confusion —
    # `_construire_table_ancres` ne consultait pas `lignes_exclues` (déjà calculé pour la
    # recherche de `ignored_paths`, rounds 18/22). Vérifié empiriquement contre PyYAML : `&md`
    # dans le contenu du scalaire bloc `note` est du texte littéral, ignoré par YAML ; l'alias
    # résout bien vers la VRAIE ancre définie avant `note`.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md >-\n  **/*.md\nnote: |-\n  &md safe\nsecret:\n  ignored_paths: [*md]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_marqueur_ancre_dans_bloc_sans_rapport_ne_masque_pas_un_glob_borne_reel(tmp_path):
    # Non-régression : quand la VRAIE ancre résout vers un glob BORNÉ légitime, malgré un faux
    # marqueur d'ancre dans le contenu d'un scalaire bloc sans rapport placé entre les deux, le
    # résultat reste conforme.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md >-\n  evidence/reviews/**/*.md\nnote: |-\n  &md safe\nsecret:\n  ignored_paths: [*md]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_resout_ignored_paths_alias_direct_vers_une_sequence_ancree(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 25, GPT-5.6-Terra-Pro) : `ignored_paths`
    # peut être un ALIAS DIRECT (sans crochets ni tiret, comme valeur SCALAIRE de la clé
    # elle-même) vers une séquence entière ANCRÉE (`defaults: &md\n  - >-\n    **/*.md`). Aucun
    # mécanisme existant (parseur structurel, filet, résolution d'ancres scalaires) ne couvrait
    # ce cas — les ancres ne portaient jusqu'ici que des scalaires. Vérifié empiriquement contre
    # PyYAML : `ignored_paths` résout bien en `['**/*.md']`.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md\n  - >-\n    **/*.md\nsecret:\n  ignored_paths: *md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_ignored_paths_alias_sequence_avec_plusieurs_items(tmp_path):
    # La séquence ancrée peut contenir plusieurs items, mélangeant formes guillemetée et
    # scalaire bloc — tous doivent être résolus dans `chemins`.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md\n  - "LICENSE"\n  - >-\n    **/*.md\nsecret:\n  ignored_paths: *md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["LICENSE", "**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_ignored_paths_alias_sequence_ne_masque_pas_un_glob_borne_reel(tmp_path):
    # Non-régression : quand la séquence ancrée résolue ne contient qu'un glob BORNÉ légitime,
    # le résultat reste conforme.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md\n  - >-\n    evidence/reviews/**/*.md\nsecret:\n  ignored_paths: *md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_detecte_ignored_paths_avec_ancre_directe_sur_la_cle(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 26, GPT-5.6-Terra-Pro) : `ignored_paths`
    # elle-même peut porter une ancre DIRECTE (`ignored_paths: &paths`, valide YAML), suivie
    # normalement de ses items de bloc habituels. `_LIGNE_CLE` n'admettait aucun marqueur
    # d'ancre après les deux-points, seulement un commentaire éventuel — la clé n'était donc
    # jamais reconnue, `parser_ignored_paths()` retournait `[]`. Vérifié empiriquement contre
    # PyYAML : `ignored_paths` résout bien en `['**/*.md']` (le scalaire bloc non guillemeté
    # du premier item, hors de portée du filet textuel).
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  ignored_paths: &paths\n    - >-\n      **/*.md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_ignored_paths_ancre_directe_ne_masque_pas_un_glob_borne_reel(tmp_path):
    # Non-régression : quand la liste de `ignored_paths` (ancrée sur la clé elle-même) ne
    # contient qu'un glob BORNÉ légitime, le résultat reste conforme.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  ignored_paths: &paths\n    - >-\n      evidence/reviews/**/*.md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_detecte_ignored_paths_flow_avec_ancre_directe_sur_la_cle(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 27, GPT-5.6-Terra-Pro) : combinaison du
    # round 26 (ancre directe sur la clé `ignored_paths`) et de la syntaxe flow —
    # `ignored_paths: &paths [*md]` (YAML valide) n'était reconnu ni comme flow
    # (`_LIGNE_CLE_FLOW_OUVERTE` exigeait `[` immédiatement après les deux-points) ni comme
    # bloc (`_LIGNE_CLE` n'admettait un marqueur d'ancre que suivi de fin de ligne/commentaire,
    # pas de `[`). Vérifié empiriquement contre PyYAML : `ignored_paths` résout bien en
    # `['**/*.md']`.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md >-\n  **/*.md\nsecret:\n  ignored_paths: &paths [*md]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_ignored_paths_flow_ancre_directe_ne_masque_pas_un_glob_borne_reel(tmp_path):
    # Non-régression : quand la liste flow de `ignored_paths` (ancrée sur la clé elle-même) ne
    # résout qu'un glob BORNÉ légitime, le résultat reste conforme.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md >-\n  evidence/reviews/**/*.md\nsecret:\n  ignored_paths: &paths [*md]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_detecte_secret_avec_ancre_directe_sur_la_cle(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 28, GPT-5.6-Terra-Pro) : le mapping
    # `secret` lui-même peut porter une ancre (`&cfg` juste après ses deux-points, YAML valide),
    # suivi normalement de sa sous-clé `ignored_paths` habituelle. `_LIGNE_CLE_SECRET`
    # n'admettait après les deux-points qu'un commentaire éventuel — `ignored_paths` n'était
    # donc jamais reconnue comme descendante du mapping `secret`. Vérifié empiriquement contre
    # PyYAML : `ignored_paths` résout bien en `['**/*.md']`. Testé aussi avec un TAG (`!!map`)
    # et les deux ordres ancre/tag (`&cfg !!map` et `!!map &cfg`) — tous valides selon PyYAML.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret: &cfg\n  ignored_paths:\n    - >-\n      **/*.md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_detecte_secret_avec_tag_direct_sur_la_cle(tmp_path):
    # Même bug, TAG (`!!map`) au lieu d'une ancre sur la clé `secret`.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret: !!map\n  ignored_paths:\n    - >-\n      **/*.md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_detecte_secret_avec_ancre_et_tag_dans_les_deux_ordres(tmp_path):
    # Le spec YAML autorise les DEUX ordres pour les propriétés d'un nœud (ancre puis tag, ou
    # tag puis ancre) — vérifié empiriquement contre PyYAML pour les deux.
    for contenu in (
        'secret: &cfg !!map\n  ignored_paths:\n    - >-\n      **/*.md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        'secret: !!map &cfg\n  ignored_paths:\n    - >-\n      **/*.md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
    ):
        fichier = tmp_path / ".gitguardian.yaml"
        fichier.write_text(contenu, encoding="utf-8")
        ok, motifs = check_gitguardian_scope.verifier(fichier)
        assert ok is False
        assert motifs == ["**/*.md"]


def test_parser_secret_ancre_directe_ne_masque_pas_un_glob_borne_reel(tmp_path):
    # Non-régression : quand `ignored_paths` (sous un mapping `secret` ancré) ne contient qu'un
    # glob BORNÉ légitime, le résultat reste conforme.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret: &cfg\n  ignored_paths:\n    - >-\n      evidence/reviews/**/*.md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_detecte_ignored_paths_avec_tag_direct_bloc(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 29, GPT-5.6-Terra-Pro) : `ignored_paths`
    # elle-même peut porter un TAG explicite (`ignored_paths: !!seq`, YAML valide), pas
    # seulement une ancre (rounds 26/27). `_LIGNE_CLE`/`_LIGNE_CLE_FLOW_OUVERTE` ne toléraient
    # qu'une ancre, jamais un tag — asymétrie avec `_LIGNE_CLE_SECRET` (round 28), qui tolérait
    # déjà les deux. Corrigé en unifiant les trois regex sur un fragment partagé
    # `_PROPRIETES_NOEUD` (ancre et/ou tag, deux ordres). Vérifié empiriquement contre PyYAML :
    # `ignored_paths` résout bien en `['**/*.md']`.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  ignored_paths: !!seq\n    - >-\n      **/*.md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_detecte_ignored_paths_avec_tag_direct_flow(tmp_path):
    # Même bug, syntaxe flow (`ignored_paths: !!seq [*md]`) — vérifie que le fragment partagé
    # `_PROPRIETES_NOEUD` fonctionne aussi pour `_LIGNE_CLE_FLOW_OUVERTE`, sans round distinct.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md >-\n  **/*.md\nsecret:\n  ignored_paths: !!seq [*md]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_ignored_paths_tag_direct_ne_masque_pas_un_glob_borne_reel(tmp_path):
    # Non-régression : quand `ignored_paths` (taguée directement) ne contient qu'un glob BORNÉ
    # légitime, le résultat reste conforme.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  ignored_paths: !!seq\n    - >-\n      evidence/reviews/**/*.md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_detecte_secret_alias_direct_vers_mapping_ancre(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 30, GPT-5.6-Terra-Pro) : le mapping
    # `secret` tout entier peut être un ALIAS DIRECT (valeur réduite à une référence `*cfg`,
    # YAML valide) vers un mapping ANCRÉ ailleurs dans le fichier, qui contient lui-même la clé
    # `ignored_paths` habituelle (`defaults: &cfg\n  ignored_paths:\n    - >-\n      **/*.md`).
    # Aucune ligne du fichier ne porte littéralement le nom de clé `secret` avec des enfants —
    # `_est_descendante_de_secret` ne pouvait donc jamais trouver de correspondance. Vérifié
    # empiriquement contre PyYAML : la liste finale résout bien en `['**/*.md']`.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &cfg\n  ignored_paths:\n    - >-\n      **/*.md\nsecret: *cfg\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_secret_alias_mapping_ne_confond_pas_une_cle_homonyme_sans_alias(tmp_path):
    # Non-régression : une clé homonyme `ignored_paths` sous un mapping ANCRÉ mais dont
    # l'ancre n'est référencée par AUCUN alias en valeur de la clé `secret` (aucun alias vers ce
    # mapping précis) ne doit pas être confondue avec une vraie descendante de `secret`.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'autre: &autre\n  ignored_paths:\n    - >-\n      **/*.md\nsecret:\n  ignored_paths:\n    - "evidence/reviews/**/*.md"\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["evidence/reviews/**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_secret_alias_mapping_ne_masque_pas_un_glob_borne_reel(tmp_path):
    # Non-régression : quand le mapping ancré référencé par l'alias en valeur de la clé
    # `secret` ne contient qu'un glob BORNÉ légitime, le résultat reste conforme.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &cfg\n  ignored_paths:\n    - >-\n      evidence/reviews/**/*.md\nsecret: *cfg\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_detecte_fusion_yaml_dans_secret(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 31, GPT-5.6-Terra-Pro) : une clé de
    # FUSION YAML (`<<: *nom`, extension `tag:yaml.org,2002:merge` largement supportée dont
    # PyYAML) dans le mapping `secret` fusionne les paires clé-valeur du mapping ancré référencé
    # — si celui-ci porte une clé `ignored_paths`, elle devient effectivement
    # `secret.ignored_paths` sans qu'aucune ligne `ignored_paths` ne soit textuellement
    # descendante de `secret`. Vérifié empiriquement contre PyYAML : la liste finale résout bien
    # en `['**/*.md']`.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &cfg\n  ignored_paths:\n    - >-\n      **/*.md\nsecret:\n  <<: *cfg\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_fusion_hors_de_secret_ne_declenche_pas_de_faux_positif(tmp_path):
    # Non-régression : une fusion `<<: *nom` qui n'est PAS elle-même descendante de `secret`
    # (donc sans rapport avec la question d'ascendance de `ignored_paths`) ne doit pas être
    # confondue avec le cas ciblé par ce correctif.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &cfg\n  ignored_paths:\n    - >-\n      **/*.md\nautre:\n  <<: *cfg\nsecret:\n  ignored_paths:\n    - "evidence/reviews/**/*.md"\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["evidence/reviews/**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_fusion_dans_secret_ne_masque_pas_un_glob_borne_reel(tmp_path):
    # Non-régression : quand le mapping fusionné dans `secret` ne contient qu'un glob BORNÉ
    # légitime, le résultat reste conforme.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &cfg\n  ignored_paths:\n    - >-\n      evidence/reviews/**/*.md\nsecret:\n  <<: *cfg\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_detecte_secret_mapping_flow_avec_alias(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 32, GPT-5.6-Terra-Pro) : le mapping
    # `secret` peut être exprimé en syntaxe FLOW (accolades, avec `ignored_paths` en son
    # sein comme alias non guillemeté — YAML valide) — aucune ligne ne commence par
    # `ignored_paths`, donc aucune des recherches
    # existantes (bloc ou flow niveau `ignored_paths`) ne la détectait. Vérifié empiriquement
    # contre PyYAML : `secret.ignored_paths` résout bien en `['**/*.md']`.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md >-\n  **/*.md\nsecret: {ignored_paths: [*md]}\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_detecte_secret_mapping_flow_avec_chaine_guillemetee(tmp_path):
    # Même forme, valeur guillemetée directe plutôt qu'un alias.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret: {ignored_paths: ["**/*.md"]}\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_detecte_secret_mapping_flow_avec_autre_cle_avant(tmp_path):
    # `ignored_paths` peut ne pas être la première clé du mapping flow — la recherche ne doit
    # pas être ancrée au tout début du contenu entre accolades.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret: {other: 1, ignored_paths: ["**/*.md"]}\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_secret_mapping_flow_ne_masque_pas_un_glob_borne_reel(tmp_path):
    # Non-régression : quand `secret` en syntaxe flow ne contient qu'un glob BORNÉ légitime,
    # le résultat reste conforme.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret: {ignored_paths: ["evidence/reviews/**/*.md"]}\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_mapping_flow_ignore_une_fausse_cle_dans_une_chaine_guillemetee(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 33, GPT-5.6-Terra-Pro) : la recherche de
    # `ignored_paths` au sein d'un mapping flow parent en syntaxe accolades (round 32) était un
    # simple `.search()` sur l'INTÉGRALITÉ du contenu entre accolades — un texte `ignored_paths:`
    # apparaissant dans la valeur guillemetée d'une AUTRE clé, AVANT la vraie clé, était pris à
    # tort pour la vraie clé, dont la valeur (ici l'alias `*md` réintroduisant l'exclusion
    # globale) n'était alors jamais examinée. Vérifié empiriquement contre PyYAML :
    # `secret.ignored_paths` résout bien en `['**/*.md']` (via l'alias), `secret.note` reste la
    # chaîne littérale `'ignored_paths: [safe]'`.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md >-\n  **/*.md\nsecret: {note: "ignored_paths: [safe]", ignored_paths: [*md]}\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_mapping_flow_ignore_une_fausse_cle_dans_un_commentaire(tmp_path):
    # Même famille de bug que ci-dessus, trouvée PROACTIVEMENT en vérifiant le correctif round
    # 33 : un mapping flow YAML peut légitimement s'étendre sur plusieurs lignes physiques et
    # contenir des commentaires sur ses lignes internes (vérifié empiriquement contre PyYAML —
    # le commentaire est entièrement ignoré, `secret.ignored_paths` résout en `['**/*.md']` via
    # l'alias, jamais en `['fake']`). Une clé factice à l'intérieur d'un commentaire ne doit pas
    # davantage être prise pour la vraie clé.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md >-\n  **/*.md\nsecret: {\n  # ignored_paths: [fake]\n  note: x,\n  ignored_paths: [*md]\n}\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_mapping_flow_avec_fausse_cle_guillemetee_ne_masque_pas_un_glob_borne_reel(tmp_path):
    # Non-régression : la même forme (fausse clé `ignored_paths:` dans une chaîne guillemetée
    # AVANT la vraie clé), mais avec la vraie clé ne portant qu'un glob BORNÉ légitime — le
    # résultat doit rester conforme (pas de faux positif introduit par le correctif round 33).
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret: {note: "ignored_paths: [danger]", ignored_paths: ["evidence/reviews/**/*.md"]}\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_mapping_flow_avec_collection_imbriquee_avant_ignored_paths(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 34, GPT-5.6-Terra-Pro) :
    # `_trouver_fermeture_flow()` ne suivait pas la profondeur d'imbrication — le premier `}`
    # non guillemeté rencontré (celui d'un mapping flow IMBRIQUÉ dans `secret`, placé AVANT
    # `ignored_paths`) était pris à tort pour la fermeture du mapping `secret` lui-même,
    # tronquant le contenu examiné et masquant la vraie clé plus loin. Vérifié empiriquement
    # contre PyYAML : `secret.ignored_paths` résout bien en `['**/*.md']` (via l'alias) malgré
    # la collection imbriquée.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md >-\n  **/*.md\nsecret: {other: {x: safe}, ignored_paths: [*md]}\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_mapping_flow_avec_liste_imbriquee_avant_ignored_paths(tmp_path):
    # Même famille de bug, variante liste flow imbriquée (`[...]`) plutôt que mapping.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md >-\n  **/*.md\nsecret: {other: [1, 2, 3], ignored_paths: [*md]}\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_mapping_flow_avec_collection_imbriquee_ne_masque_pas_un_glob_borne_reel(tmp_path):
    # Non-régression : la même forme (collection imbriquée avant `ignored_paths`), mais avec la
    # vraie clé ne portant qu'un glob BORNÉ légitime — le résultat doit rester conforme (pas de
    # faux positif introduit par le correctif round 34).
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret: {other: {x: safe}, ignored_paths: ["evidence/reviews/**/*.md"]}\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_mapping_flow_ignore_une_cle_homonyme_imbriquee(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 35, GPT-5.6-Terra-Pro) : le filtrage par
    # spans (guillemets/commentaires, round 33) ne suffisait pas — une clé `ignored_paths` RÉELLE
    # (ni guillemetée ni commentée) mais située DANS une collection flow imbriquée (`other: {
    # ignored_paths: [safe] }`, placée AVANT la vraie clé de premier niveau) était prise à tort
    # pour la vraie clé, dont la valeur (l'alias `*md` réintroduisant l'exclusion globale)
    # n'était alors jamais examinée. Vérifié empiriquement contre PyYAML : la valeur de la clé
    # de PREMIER NIVEAU (`secret.ignored_paths`) résout bien en `['**/*.md']`, sans aucun rapport
    # avec la clé homonyme imbriquée dans `other` (`other.ignored_paths` reste `['safe']`).
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md >-\n  **/*.md\nsecret: {other: {ignored_paths: [safe]}, ignored_paths: [*md]}\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_mapping_flow_avec_cle_homonyme_imbriquee_ne_masque_pas_un_glob_borne_reel(tmp_path):
    # Non-régression : la même forme (clé homonyme imbriquée avant la vraie clé de premier
    # niveau), mais avec la vraie clé ne portant qu'un glob BORNÉ légitime — le résultat doit
    # rester conforme (pas de faux positif introduit par le correctif round 35).
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret: {other: {ignored_paths: ["danger"]}, ignored_paths: ["evidence/reviews/**/*.md"]}\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_reconnait_la_cle_ignored_paths_guillemetee_doubles(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 36, GPT-5.6-Terra-Pro) : le NOM d'une clé
    # YAML peut être écrit entre guillemets doubles — sémantiquement indiscernable de la forme
    # nue pour tout parseur YAML conforme (vérifié empiriquement contre PyYAML). Aucune des
    # recherches existantes n'exigeait qu'un nom de clé littéral NU — une exclusion globale
    # portée par une clé guillemetée passait donc inaperçue.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  "ignored_paths":\n    - >-\n      **/*.md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_reconnait_la_cle_secret_guillemetee_doubles(tmp_path):
    # Même bug, variante sur la clé `secret` elle-même (mentionnée explicitement par le
    # reviewer) plutôt que sur `ignored_paths`.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        '"secret":\n  ignored_paths:\n    - >-\n      **/*.md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_reconnait_les_cles_guillemetees_simples(tmp_path):
    # Non-régression de forme : guillemets SIMPLES plutôt que doubles, sur les deux clés à la
    # fois (`secret` et `ignored_paths`) dans le même fichier.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        "'secret':\n  'ignored_paths':\n    - >-\n      **/*.md\n",  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_cle_ignored_paths_guillemetee_ne_masque_pas_un_glob_borne_reel(tmp_path):
    # Non-régression : la clé guillemetée reste correctement résolue pour un glob BORNÉ
    # légitime — pas de faux positif introduit par le correctif round 36.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  "ignored_paths":\n    - "evidence/reviews/**/*.md"\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_gitguardian_yaml_reel_du_depot_toujours_conforme_apres_round36(tmp_path):
    # Non-régression directe sur le fichier réel du dépôt : le correctif round 36 (tolérance des
    # clés guillemetées) ne doit rien changer à son verdict — il n'utilise aucune clé
    # guillemetée.
    ok, motifs = check_gitguardian_scope.verifier(REPO / ".gitguardian.yaml")
    assert ok is True, f"exclusion(s) markdown globale(s) réintroduite(s) : {motifs}"


def test_parser_reconnait_la_cle_ignored_paths_guillemetee_dans_un_mapping_flow(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 37, GPT-5.6-Terra-Pro) : le filtrage par
    # spans du round 33 excluait purement et simplement TOUT candidat commençant dans un span
    # guillemeté — y compris une clé `"ignored_paths"` légitimement guillemetée (round 36) dans
    # un mapping flow, dont le `"` d'ouverture EST le premier caractère consommé par le candidat
    # lui-même, pas une occurrence fortuite à l'intérieur d'une chaîne sans rapport. Vérifié
    # empiriquement contre PyYAML : `secret.ignored_paths` résout bien en `['**/*.md']` (via
    # l'alias) malgré la clé guillemetée.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md >-\n  **/*.md\nsecret: {"ignored_paths": [*md]}\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_reconnait_la_cle_ignored_paths_guillemetee_simple_dans_un_mapping_flow(tmp_path):
    # Même forme, guillemets SIMPLES plutôt que doubles.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        "defaults: &md >-\n  **/*.md\nsecret: {'ignored_paths': [*md]}\n",  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_mapping_flow_avec_cle_guillemetee_ne_masque_pas_un_glob_borne_reel(tmp_path):
    # Non-régression : la clé guillemetée dans un mapping flow reste correctement résolue pour
    # un glob BORNÉ légitime — pas de faux positif introduit par le correctif round 37.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret: {"ignored_paths": ["evidence/reviews/**/*.md"]}\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_mapping_flow_fausse_cle_guillemetee_dans_valeur_reste_bloquee(tmp_path):
    # Non-régression du correctif round 33 : une occurrence de texte `ignored_paths:` FORTUITE
    # à l'intérieur de la valeur guillemetée d'une AUTRE clé (donc STRICTEMENT à l'intérieur du
    # span guillemeté, pas à son ouverture) doit rester ignorée — le correctif round 37 exempte
    # UNIQUEMENT un candidat commençant EXACTEMENT à l'ouverture d'un guillemet, jamais un
    # candidat strictement à l'intérieur.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md >-\n  **/*.md\nsecret: {note: "ignored_paths: [safe]", ignored_paths: [*md]}\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_dieze_dans_scalaire_nu_sans_espace_n_est_pas_un_commentaire(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 38, GPT-5.6-Terra-Pro) : `_spans_commentaires`
    # traitait TOUT `#` non guillemeté comme démarrant un commentaire, sans vérifier le caractère
    # précédent. Or en YAML, `#` ne démarre un commentaire que s'il est séparé du contenu
    # précédent (blanc, indicateur structurel, début de ligne) — à l'intérieur d'un scalaire nu
    # SANS séparation, il fait partie de la valeur littérale. Vérifié empiriquement contre
    # PyYAML : `foo#bar` est la valeur `'foo#bar'`, jamais `'foo'` suivi d'un commentaire. Le `#`
    # de `note` masquait donc à tort la vraie clé `ignored_paths` sur la même ligne physique.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md >-\n  **/*.md\nsecret: {note: foo#bar, ignored_paths: [*md]}\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_dieze_apres_accolade_ouvrante_reste_un_commentaire(tmp_path):
    # Non-régression : un `#` immédiatement après un indicateur structurel flow (`{`, sans
    # espace) reste bien reconnu comme un commentaire — vérifié empiriquement contre PyYAML.
    # Le correctif round 38 ne doit PAS régresser ce cas déjà couvert par le round 33.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md >-\n  **/*.md\nsecret: {#ignored_paths: [fake]\n  note: x,\n  ignored_paths: [*md]\n}\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_dieze_apres_virgule_sans_espace_reste_un_commentaire(tmp_path):
    # Non-régression, variante virgule : un `#` immédiatement après une virgule (sans espace)
    # reste bien reconnu comme un commentaire — vérifié empiriquement contre PyYAML.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md >-\n  **/*.md\nsecret: {note: x,#ignored_paths: [fake]\n  ignored_paths: [*md]\n}\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_dieze_dans_scalaire_nu_ne_masque_pas_un_glob_borne_reel(tmp_path):
    # Non-régression : la même forme (`#` sans espace dans un scalaire nu AVANT la vraie clé),
    # mais avec la vraie clé ne portant qu'un glob BORNÉ légitime — le résultat doit rester
    # conforme (pas de faux positif introduit par le correctif round 38).
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret: {note: foo#bar, ignored_paths: ["evidence/reviews/**/*.md"]}\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_accolade_dans_commentaire_ne_tronque_pas_le_mapping_flow(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 39, GPT-5.6-Terra-Pro) : un commentaire
    # interne à un mapping flow multi-lignes (légitime, round 33) peut lui-même contenir un `}`
    # littéral (`# } commentaire`) — `_trouver_fermeture_flow` ne reconnaissait pas les
    # commentaires et prenait ce caractère pour la fermeture du mapping, tronquant le contenu
    # avant la vraie clé. Vérifié empiriquement contre PyYAML : le commentaire est entièrement
    # ignoré, `secret.ignored_paths` résout normalement en `['**/*.md']`.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md >-\n  **/*.md\nsecret: {\n  # } commentaire\n  ignored_paths: [*md]\n}\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_crochet_dans_commentaire_ne_perturbe_pas_une_liste_flow(tmp_path):
    # Même famille de bug, trouvée PROACTIVEMENT en vérifiant le correctif round 39 : une liste
    # flow multi-lignes (round 17) peut contenir un `]` littéral dans un commentaire interne —
    # vérifié empiriquement contre PyYAML, le commentaire est entièrement ignoré.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md >-\n  **/*.md\nsecret:\n  ignored_paths: [\n    # ] commentaire\n    *md\n  ]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_virgule_dans_commentaire_ne_scinde_pas_un_jeton_de_liste_flow(tmp_path):
    # Variante : une virgule à l'intérieur d'un commentaire de liste flow ne doit pas être
    # traitée comme un séparateur de premier niveau.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md >-\n  **/*.md\nsecret:\n  ignored_paths: [\n    # a, b\n    *md\n  ]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_accolade_dans_commentaire_ne_masque_pas_un_glob_borne_reel(tmp_path):
    # Non-régression : la même forme (accolade dans un commentaire interne au mapping flow),
    # mais avec la vraie clé ne portant qu'un glob BORNÉ légitime — le résultat doit rester
    # conforme (pas de faux positif introduit par le correctif round 39).
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret: {\n  # } commentaire\n  ignored_paths: ["evidence/reviews/**/*.md"]\n}\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_reconnait_la_cle_ignored_paths_avec_echappement_yaml(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 40, GPT-5.6-Terra-Pro) : les alternatives
    # littérales du round 36 ne reconnaissaient qu'une orthographe guillemetée EXACTE — une clé
    # double-guillemets contenant un échappement YAML valide sur le caractère `_` (souligné bas)
    # est pourtant sémantiquement identique à `ignored_paths` pour tout parseur conforme.
    # Vérifié empiriquement contre PyYAML.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  "ignored\\u005fpaths":\n    - >-\n      **/*.md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_reconnait_la_cle_secret_avec_echappement_yaml(tmp_path):
    # Même bug, variante sur la clé `secret` elle-même — une clé double-guillemets contenant un
    # échappement YAML valide sur le caractère `e` reste sémantiquement `secret` pour tout
    # parseur YAML conforme.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        '"secr\\u0065t":\n  ignored_paths:\n    - >-\n      **/*.md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_cle_avec_echappement_yaml_ne_masque_pas_un_glob_borne_reel(tmp_path):
    # Non-régression : la même forme (clé guillemetée avec échappement), mais avec la vraie clé
    # ne portant qu'un glob BORNÉ légitime — le résultat doit rester conforme (pas de faux
    # positif introduit par le correctif round 40).
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  "ignored\\u005fpaths":\n    - "evidence/reviews/**/*.md"\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_gitguardian_yaml_reel_du_depot_toujours_conforme_apres_round40():
    # Non-régression directe sur le fichier réel du dépôt, après le refactor round 40 (regex de
    # nom de clé génériques partagées entre `ignored_paths` et `secret`, décodage post-match) :
    # le verdict ne doit rien changer.
    ok, motifs = check_gitguardian_scope.verifier(REPO / ".gitguardian.yaml")
    assert ok is True, f"exclusion(s) markdown globale(s) réintroduite(s) : {motifs}"


def test_parser_reconnait_la_cle_ignored_paths_echappee_dans_un_mapping_flow(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 41, GPT-5.6-Terra-Pro) : la limite
    # assumée à la fin du round 40 (« la recherche de clé dans un mapping flow garde l'ancienne
    # forme littérale ») est comblée — une clé `ignored_paths` guillemetée avec un échappement
    # YAML valide, DANS un mapping flow parent, doit désormais être reconnue. Vérifié
    # empiriquement contre PyYAML : `secret.ignored_paths` résout bien en `['**/*.md']` (via
    # l'alias) malgré l'échappement dans le nom de clé.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md >-\n  **/*.md\nsecret: {"ignored\\u005fpaths": [*md]}\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_mapping_flow_bare_ne_traverse_pas_une_frontiere_flow(tmp_path):
    # Bug réel trouvé PROACTIVEMENT en vérifiant le correctif round 41 : l'alternative nue
    # générique du round 40 (`_NOM_CLE_QUELCONQUE`, qui exclut seulement `:`/`#`) engloutissait
    # à tort du texte à travers une frontière d'item flow (virgule, crochet) lorsqu'utilisée SANS
    # ancrage `^` (cas de la recherche dans un mapping flow, contrairement aux formes bloc
    # ancrées à une ligne) — masquant la vraie clé `ignored_paths` derrière un candidat bare
    # illégitime engendré par le texte d'une valeur guillemetée précédente. Reproduction exacte
    # du round 33 (fausse clé dans une valeur guillemetée), qui aurait régressé sans le
    # correctif dédié `_NOM_CLE_QUELCONQUE_FLOW`.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md >-\n  **/*.md\nsecret: {note: "ignored_paths: [safe]", ignored_paths: [*md]}\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_cle_flow_echappee_ne_masque_pas_un_glob_borne_reel(tmp_path):
    # Non-régression : la clé guillemetée avec échappement dans un mapping flow reste
    # correctement résolue pour un glob BORNÉ légitime — pas de faux positif introduit par le
    # correctif round 41.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret: {"ignored\\u005fpaths": ["evidence/reviews/**/*.md"]}\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_gitguardian_yaml_reel_du_depot_toujours_conforme_apres_round41():
    # Non-régression directe sur le fichier réel du dépôt, après le round 41 (échappements dans
    # les clés de mapping flow, `_NOM_CLE_QUELCONQUE_FLOW`) : le verdict ne doit rien changer.
    ok, motifs = check_gitguardian_scope.verifier(REPO / ".gitguardian.yaml")
    assert ok is True, f"exclusion(s) markdown globale(s) réintroduite(s) : {motifs}"


def test_parser_reconnait_la_syntaxe_de_cle_explicite(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 42, GPT-5.6-Terra-Pro) : la syntaxe YAML
    # de clé EXPLICITE (indicateur `?`, spec 8.2.1) permet à la clé et à son séparateur `:`
    # d'être sur des lignes DISTINCTES — forme rare mais valide, supportée par PyYAML. Aucune
    # regex existante ne reconnaissait une ligne commençant par `?` suivie d'une ligne `:`.
    # Vérifié empiriquement contre PyYAML : la liste finale résout bien en `['**/*.md']`.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  ? ignored_paths\n  :\n    - >-\n      **/*.md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_cle_explicite_ne_masque_pas_un_glob_borne_reel(tmp_path):
    # Non-régression : la même forme (clé explicite), mais avec la vraie clé ne portant qu'un
    # glob BORNÉ légitime — le résultat doit rester conforme (pas de faux positif introduit par
    # le correctif round 42).
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  ? ignored_paths\n  :\n    - "evidence/reviews/**/*.md"\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_gitguardian_yaml_reel_du_depot_toujours_conforme_apres_round42():
    # Non-régression directe sur le fichier réel du dépôt, après le round 42 (syntaxe de clé
    # explicite `?`/`:`) : le verdict ne doit rien changer.
    ok, motifs = check_gitguardian_scope.verifier(REPO / ".gitguardian.yaml")
    assert ok is True, f"exclusion(s) markdown globale(s) réintroduite(s) : {motifs}"


def test_parser_cle_explicite_saute_un_commentaire_avant_le_separateur(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 43, GPT-5.6-Terra-Pro) : la prise en
    # charge de la clé explicite (round 42) ne sautait que les lignes VIDES entre `? ignored_paths`
    # et le séparateur `:`, contredisant sa propre docstring (« prochaine ligne non vide/non
    # commentée ») — une ligne de COMMENTAIRE entre les deux (YAML valide) empêchait la
    # reconnaissance du séparateur. Vérifié empiriquement contre PyYAML.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  ? ignored_paths\n  # commentaire\n  :\n    - >-\n      **/*.md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_cle_explicite_saute_lignes_vides_et_commentaires_melanges(tmp_path):
    # Variante : plusieurs lignes vides ET de commentaire entrelacées entre `?` et `:`.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  ? ignored_paths\n\n  # commentaire\n\n  :\n    - >-\n      **/*.md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_cle_explicite_avec_commentaire_ne_masque_pas_un_glob_borne_reel(tmp_path):
    # Non-régression : la même forme (commentaire entre `?` et `:`), mais avec la vraie clé ne
    # portant qu'un glob BORNÉ légitime — le résultat doit rester conforme (pas de faux positif
    # introduit par le correctif round 43).
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  ? ignored_paths\n  # commentaire\n  :\n    - "evidence/reviews/**/*.md"\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_gitguardian_yaml_reel_du_depot_toujours_conforme_apres_round43():
    # Non-régression directe sur le fichier réel du dépôt, après le round 43 (clé explicite +
    # commentaire avant le séparateur) : le verdict ne doit rien changer.
    ok, motifs = check_gitguardian_scope.verifier(REPO / ".gitguardian.yaml")
    assert ok is True, f"exclusion(s) markdown globale(s) réintroduite(s) : {motifs}"


def test_parser_ignore_le_contenu_dun_scalaire_bloc_porte_par_une_cle_guillemetee_avec_deux_points(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 44, GPT-5.6-Terra-Pro) : `_LIGNE_CLE_BLOC`
    # (identifie les lignes de CONTENU d'un scalaire bloc, pour les exclure des recherches de clé
    # ailleurs dans le fichier, round 18) ne reconnaissait pas une clé GUILLEMETÉE contenant un
    # `:` littéral (`"note: benign": |-`) — le `:` interne, rencontré avant le vrai séparateur,
    # faisait échouer la reconnaissance de la ligne comme porteuse d'un scalaire bloc. Son
    # contenu (une fausse hiérarchie `secret.ignored_paths`) n'était alors PAS exclu des
    # recherches, masquant la vraie liste. Vérifié empiriquement contre PyYAML : la clé
    # guillemetée `note: benign` a bien pour valeur le texte littéral du bloc (pas une vraie
    # structure YAML imbriquée), `secret.ignored_paths` résout bien en `['**/*.md']`.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        '"note: benign": |-\n  secret:\n    ignored_paths: [safe]\ndefaults: &md >-\n  **/*.md\nsecret:\n  ignored_paths: [*md]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_cle_guillemetee_avec_deux_points_dans_scalaire_bloc_ne_masque_pas_un_glob_borne_reel(tmp_path):
    # Non-régression : la même forme (clé guillemetée avec `:` portant un scalaire bloc), mais
    # avec la vraie clé ne portant qu'un glob BORNÉ légitime — le résultat doit rester conforme
    # (pas de faux positif introduit par le correctif round 44).
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        '"note: benign": |-\n  secret:\n    ignored_paths: [safe]\nsecret:\n  ignored_paths: ["evidence/reviews/**/*.md"]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_gitguardian_yaml_reel_du_depot_toujours_conforme_apres_round44():
    # Non-régression directe sur le fichier réel du dépôt, après le round 44 (clé guillemetée
    # avec `:` littéral portant un scalaire bloc) : le verdict ne doit rien changer.
    ok, motifs = check_gitguardian_scope.verifier(REPO / ".gitguardian.yaml")
    assert ok is True, f"exclusion(s) markdown globale(s) réintroduite(s) : {motifs}"


def test_parser_ignore_un_mapping_secret_homonyme_imbrique_sous_un_autre_parent(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 45, GPT-5.6-Terra-Pro) : `_LIGNE_CLE_SECRET`
    # exige par construction que la clé racine soit à la RACINE (aucune tolérance d'indentation)
    # — c'est précisément ce qui distingue le vrai mapping racine d'un mapping HOMONYME imbriqué
    # sous un autre parent. `_est_descendante_de_secret` matchait cette regex contre la ligne
    # DÉPOUILLÉE de son indentation, annulant cette distinction : une clé homonyme imbriquée à
    # n'importe quelle profondeur devenait indiscernable de la vraie clé racine. Vérifié
    # empiriquement contre PyYAML : la vraie liste racine résout bien en `['**/*.md']` (via
    # l'alias), sans rapport avec la liste imbriquée sous `autre` (`['safe']`).
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md >-\n  **/*.md\nautre:\n  secret:\n    ignored_paths: [safe]\nsecret:\n  ignored_paths: [*md]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_ignore_un_alias_secret_homonyme_imbrique_sous_un_autre_parent(tmp_path):
    # Bug réel trouvé PROACTIVEMENT en vérifiant le correctif round 45 : même défaut de fond
    # dans `_noms_ancres_aliasees_secret` (recherche de la clé racine réduite à un alias, round
    # 30) — une clé homonyme réduite à un alias, imbriquée sous un autre parent, enregistrait à
    # tort son nom d'ancre comme équivalent à la vraie clé racine. Vérifié empiriquement contre
    # PyYAML : la vraie liste racine (scalaire bloc non guillemeté) résout bien en `['**/*.md']`,
    # sans rapport avec l'alias imbriqué sous `autre` (mapping borné et sans danger).
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &cfg\n  ignored_paths:\n    - "evidence/reviews/**/*.md"\nautre:\n  secret: *cfg\nsecret:\n  ignored_paths:\n    - >-\n      **/*.md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_secret_homonyme_imbrique_ne_masque_pas_un_glob_borne_reel(tmp_path):
    # Non-régression : la même forme (mapping `secret` homonyme imbriqué sous un autre parent),
    # mais avec la vraie clé racine ne portant qu'un glob BORNÉ légitime — le résultat doit
    # rester conforme (pas de faux positif introduit par le correctif round 45).
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'autre:\n  secret:\n    ignored_paths: [danger]\nsecret:\n  ignored_paths: ["evidence/reviews/**/*.md"]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_gitguardian_yaml_reel_du_depot_toujours_conforme_apres_round45():
    # Non-régression directe sur le fichier réel du dépôt, après le round 45 (mapping/alias
    # `secret` homonyme imbriqué sous un autre parent) : le verdict ne doit rien changer.
    ok, motifs = check_gitguardian_scope.verifier(REPO / ".gitguardian.yaml")
    assert ok is True, f"exclusion(s) markdown globale(s) réintroduite(s) : {motifs}"


def test_parser_cle_explicite_avec_liste_flow_inline_apres_le_separateur(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 46, GPT-5.6-Terra-Pro) : la limite
    # documentée à la fin du round 42 (« pas de valeur inline après `:` ») est comblée — une
    # valeur peut légitimement suivre le séparateur `:` sur la MÊME ligne (`: [*alias]`), pas
    # seulement sur les lignes suivantes. Vérifié empiriquement contre PyYAML.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md >-\n  **/*.md\nsecret:\n  ? ignored_paths\n  : [*md]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_cle_explicite_avec_alias_direct_inline_apres_le_separateur(tmp_path):
    # Variante trouvée PROACTIVEMENT en vérifiant le correctif round 46 : un alias DIRECT (sans
    # crochets) après le séparateur `:` de la clé explicite, même famille que la forme flow.
    # Vérifié empiriquement contre PyYAML.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md >-\n  **/*.md\nsecret:\n  ? ignored_paths\n  : *md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_cle_explicite_valeur_inline_ne_masque_pas_un_glob_borne_reel(tmp_path):
    # Non-régression : la même forme (valeur flow inline après `:`), mais avec la vraie clé ne
    # portant qu'un glob BORNÉ légitime — le résultat doit rester conforme (pas de faux positif
    # introduit par le correctif round 46).
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  ? ignored_paths\n  : ["evidence/reviews/**/*.md"]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_gitguardian_yaml_reel_du_depot_toujours_conforme_apres_round46():
    # Non-régression directe sur le fichier réel du dépôt, après le round 46 (valeur inline
    # après le séparateur `:` d'une clé explicite) : le verdict ne doit rien changer.
    ok, motifs = check_gitguardian_scope.verifier(REPO / ".gitguardian.yaml")
    assert ok is True, f"exclusion(s) markdown globale(s) réintroduite(s) : {motifs}"


def test_construire_table_ancres_ignore_un_dieze_esperluette_dans_un_scalaire_nu_deja_commence(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 48, GPT-5.6-Terra-Pro) : un `&nom` peut
    # apparaître à l'intérieur d'un scalaire NU déjà commencé (`note: foo&md safe`) sans être une
    # propriété de nœud — vérifié empiriquement contre PyYAML : `&` ne démarre une ancre que s'il
    # est en position de DÉBUT de valeur (juste après `clé:`+blanc, `-`+blanc, un tag+blanc, ou
    # en tout début de ligne), jamais au milieu d'un scalaire déjà en cours. Sans ce filtrage, la
    # table d'ancres écrasait à tort la VRAIE ancre `md` (pointant vers l'exclusion globale) par
    # ce faux candidat, dont la valeur (`safe`) masquait ensuite l'alias réel dans `ignored_paths`.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md >-\n  **/*.md\nnote: foo&md safe\nsecret:\n  ignored_paths: [*md]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_construire_table_ancres_esperluette_dans_scalaire_nu_ne_masque_pas_un_glob_borne_reel(tmp_path):
    # Non-régression : la même forme (`&nom` dans un scalaire nu déjà commencé, écrasement
    # potentiel de la table d'ancres), mais avec la vraie ancre pointant vers un glob BORNÉ
    # légitime — le résultat doit rester conforme (pas de faux positif introduit par le
    # correctif round 48).
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md >-\n  evidence/reviews/**/*.md\nnote: foo&md safe\nsecret:\n  ignored_paths: [*md]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_gitguardian_yaml_reel_du_depot_toujours_conforme_apres_round48():
    # Non-régression directe sur le fichier réel du dépôt, après le round 48 (`&` dans un
    # scalaire nu déjà commencé, non pris pour une définition d'ancre) : le verdict ne doit rien
    # changer.
    ok, motifs = check_gitguardian_scope.verifier(REPO / ".gitguardian.yaml")
    assert ok is True, f"exclusion(s) markdown globale(s) réintroduite(s) : {motifs}"


def test_parser_reconnait_la_cle_racine_en_syntaxe_explicite(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 49, GPT-5.6-Terra-Pro) : la syntaxe de
    # clé EXPLICITE (`? nom\n:`, rounds 42-43/46) avait été supportée pour `ignored_paths` mais
    # jamais pour la clé racine elle-même — `_LIGNE_CLE_SECRET` ne reconnaît que la forme bloc
    # classique sur une seule ligne, pas `?` sur une ligne séparée. Vérifié empiriquement contre
    # PyYAML.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        '? secret\n:\n  ? ignored_paths\n  :\n    - >-\n      **/*.md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_cle_racine_explicite_avec_ignored_paths_standard(tmp_path):
    # Variante : clé racine en syntaxe explicite, mais `ignored_paths` en syntaxe bloc standard
    # (pas les deux clés en explicite simultanément).
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        '? secret\n:\n  ignored_paths:\n    - >-\n      **/*.md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_ignore_une_cle_racine_explicite_homonyme_imbriquee(tmp_path):
    # Non-régression CRITIQUE trouvée en vérifiant le correctif round 49 lui-même (avant tout
    # commit) : la première version du correctif ne vérifiait pas que le `? secret` trouvé soit
    # lui-même à la RACINE (indentation 0, même invariant que le round 45 pour la forme
    # standard) — un `? secret` HOMONYME imbriqué sous un autre parent, en syntaxe explicite,
    # était accepté à tort comme la vraie clé racine. Vérifié empiriquement contre PyYAML.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md >-\n  **/*.md\nautre:\n  ? secret\n  :\n    ignored_paths: [safe]\nsecret:\n  ignored_paths: ["evidence/reviews/**/*.md"]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["evidence/reviews/**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_cle_racine_explicite_ne_masque_pas_un_glob_borne_reel(tmp_path):
    # Non-régression : la même forme (clé racine explicite), mais avec `ignored_paths` ne
    # portant qu'un glob BORNÉ légitime — le résultat doit rester conforme (pas de faux positif
    # introduit par le correctif round 49).
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        '? secret\n:\n  ignored_paths:\n    - "evidence/reviews/**/*.md"\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_gitguardian_yaml_reel_du_depot_toujours_conforme_apres_round49():
    # Non-régression directe sur le fichier réel du dépôt, après le round 49 (clé racine en
    # syntaxe explicite) : le verdict ne doit rien changer.
    ok, motifs = check_gitguardian_scope.verifier(REPO / ".gitguardian.yaml")
    assert ok is True, f"exclusion(s) markdown globale(s) réintroduite(s) : {motifs}"


def test_parser_cle_racine_explicite_avec_mapping_flow_inline(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 50, GPT-5.6-Terra-Pro) : la clé racine en
    # syntaxe explicite (round 49) peut porter une valeur MAPPING FLOW inline après son
    # séparateur `:` (`? secret\n: {ignored_paths: [*md]}`) — symétrique à la forme bloc classique
    # (round 32). Vérifié empiriquement contre PyYAML.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md >-\n  **/*.md\n? secret\n: {ignored_paths: [*md]}\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_ignore_une_cle_racine_explicite_flow_homonyme_imbriquee(tmp_path):
    # Non-régression : même invariant que le round 49 (racine à l'indentation 0) appliqué à la
    # nouvelle forme flow — un `? secret` HOMONYME imbriqué sous un autre parent, avec une
    # valeur flow inline, ne doit PAS être accepté comme la vraie clé racine.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md >-\n  **/*.md\nautre:\n  ? secret\n  : {ignored_paths: [safe]}\nsecret:\n  ignored_paths: ["evidence/reviews/**/*.md"]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["evidence/reviews/**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_cle_racine_explicite_mapping_flow_ne_masque_pas_un_glob_borne_reel(tmp_path):
    # Non-régression : la même forme (clé racine explicite + mapping flow inline), mais avec
    # `ignored_paths` ne portant qu'un glob BORNÉ légitime — le résultat doit rester conforme
    # (pas de faux positif introduit par le correctif round 50).
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        '? secret\n: {ignored_paths: ["evidence/reviews/**/*.md"]}\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_gitguardian_yaml_reel_du_depot_toujours_conforme_apres_round50():
    # Non-régression directe sur le fichier réel du dépôt, après le round 50 (clé racine
    # explicite + mapping flow inline) : le verdict ne doit rien changer.
    ok, motifs = check_gitguardian_scope.verifier(REPO / ".gitguardian.yaml")
    assert ok is True, f"exclusion(s) markdown globale(s) réintroduite(s) : {motifs}"


def test_parser_cle_racine_explicite_avec_ancre_sur_le_separateur(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 51, GPT-5.6-Terra-Pro) :
    # `_LIGNE_VALEUR_EXPLICITE` (`:` seul, valeur bloc sur les lignes suivantes) n'acceptait
    # aucune propriété de nœud (ancre et/ou tag) entre le séparateur `:` et le commentaire
    # optionnel — symétrique à ce que `_PROPRIETES_NOEUD` tolère déjà pour toutes les formes
    # `clé: <properties>?` depuis les rounds 26-29. Vérifié empiriquement contre PyYAML.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        '? secret\n: &cfg\n  ignored_paths:\n    - >-\n      **/*.md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_cle_ignored_paths_explicite_avec_ancre_sur_le_separateur(tmp_path):
    # Variante trouvée PROACTIVEMENT en vérifiant le correctif round 51 : même défaut de fond
    # pour la clé `ignored_paths` explicite (round 42), pas seulement la clé racine. Vérifié
    # empiriquement contre PyYAML.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  ? ignored_paths\n  : &nom\n    - >-\n      **/*.md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_cle_racine_explicite_avec_ancre_ne_masque_pas_un_glob_borne_reel(tmp_path):
    # Non-régression : la même forme (ancre sur le séparateur `:`), mais avec `ignored_paths` ne
    # portant qu'un glob BORNÉ légitime — le résultat doit rester conforme (pas de faux positif
    # introduit par le correctif round 51).
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        '? secret\n: &cfg\n  ignored_paths:\n    - "evidence/reviews/**/*.md"\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_gitguardian_yaml_reel_du_depot_toujours_conforme_apres_round51():
    # Non-régression directe sur le fichier réel du dépôt, après le round 51 (ancre/tag sur le
    # séparateur `:` d'une clé explicite) : le verdict ne doit rien changer.
    ok, motifs = check_gitguardian_scope.verifier(REPO / ".gitguardian.yaml")
    assert ok is True, f"exclusion(s) markdown globale(s) réintroduite(s) : {motifs}"


def test_parser_liste_flow_explicite_avec_ancre_sur_le_separateur(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 52, GPT-5.6-Terra-Pro) : le même défaut
    # que le round 51 affectait aussi `_LIGNE_VALEUR_EXPLICITE_FLOW_OUVERTE` (`: [`, round 46) —
    # `: &nom [...]` n'était pas reconnu, alors que les formes bloc classiques tolèrent déjà une
    # propriété de nœud avant `[`/`{`. Vérifié empiriquement contre PyYAML.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md >-\n  **/*.md\nsecret:\n  ? ignored_paths\n  : &paths [*md]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_mapping_flow_racine_explicite_avec_ancre_sur_le_separateur(tmp_path):
    # Variante trouvée PROACTIVEMENT en vérifiant le correctif round 52 : même défaut pour
    # `_LIGNE_VALEUR_EXPLICITE_SECRET_FLOW_OUVERTE` (`: {`, round 50) — la clé racine explicite
    # avec un mapping flow ANCRÉ inline. Vérifié empiriquement contre PyYAML.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md >-\n  **/*.md\n? secret\n: &cfg {ignored_paths: [*md]}\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_liste_flow_explicite_avec_ancre_ne_masque_pas_un_glob_borne_reel(tmp_path):
    # Non-régression : la même forme (ancre sur le séparateur `:` d'une liste flow explicite),
    # mais avec la vraie clé ne portant qu'un glob BORNÉ légitime — le résultat doit rester
    # conforme (pas de faux positif introduit par le correctif round 52).
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  ? ignored_paths\n  : &paths ["evidence/reviews/**/*.md"]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_gitguardian_yaml_reel_du_depot_toujours_conforme_apres_round52():
    # Non-régression directe sur le fichier réel du dépôt, après le round 52 (ancre sur le
    # séparateur `:` d'une liste/mapping flow explicite) : le verdict ne doit rien changer.
    ok, motifs = check_gitguardian_scope.verifier(REPO / ".gitguardian.yaml")
    assert ok is True, f"exclusion(s) markdown globale(s) réintroduite(s) : {motifs}"


def test_parser_cle_racine_explicite_avec_tag_sur_le_nom(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 53, GPT-5.6-Terra-Pro) : les rounds 51-52
    # corrigeaient le côté VALEUR (`:`) du séparateur explicite — `_LIGNE_CLE_EXPLICITE` (le côté
    # CLÉ, `?`) souffrait du même défaut symétrique, jamais corrigé : aucune propriété de nœud
    # entre `?` et le nom de clé (`? !!str secret`). Vérifié empiriquement contre PyYAML.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        '? !!str secret\n:\n  ignored_paths:\n    - >-\n      **/*.md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_cle_ignored_paths_explicite_avec_tag_sur_le_nom(tmp_path):
    # Variante trouvée PROACTIVEMENT en vérifiant le correctif round 53 : même défaut pour la
    # clé `ignored_paths` explicite, pas seulement la clé racine. Vérifié empiriquement contre
    # PyYAML.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  ? !!str ignored_paths\n  :\n    - >-\n      **/*.md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_cle_racine_explicite_avec_tag_ne_masque_pas_un_glob_borne_reel(tmp_path):
    # Non-régression : la même forme (tag sur le nom de clé explicite), mais avec la vraie clé
    # ne portant qu'un glob BORNÉ légitime — le résultat doit rester conforme (pas de faux
    # positif introduit par le correctif round 53).
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        '? !!str secret\n:\n  ignored_paths:\n    - "evidence/reviews/**/*.md"\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_gitguardian_yaml_reel_du_depot_toujours_conforme_apres_round53():
    # Non-régression directe sur le fichier réel du dépôt, après le round 53 (tag sur le nom
    # d'une clé explicite) : le verdict ne doit rien changer.
    ok, motifs = check_gitguardian_scope.verifier(REPO / ".gitguardian.yaml")
    assert ok is True, f"exclusion(s) markdown globale(s) réintroduite(s) : {motifs}"


def test_construire_table_ancres_reconnait_une_ancre_sur_le_separateur_dune_cle_explicite_arbitraire(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 54, GPT-5.6-Terra-Pro) : une clé EXPLICITE
    # ARBITRAIRE (`? nom\n: &ancre …`, pas seulement `secret`/`ignored_paths` —
    # `_construire_table_ancres` balaie TOUT le fichier, round 12) porte son ancre sur une ligne
    # de séparateur `:` SEUL, sans nom de clé sur cette même ligne. `_PREFIXE_AVANT_ANCRE` ne
    # reconnaissait pas ce préfixe comme une position de début de valeur légitime. Vérifié
    # empiriquement contre PyYAML.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        '? defaults\n: &md >-\n  **/*.md\nsecret:\n  ignored_paths: [*md]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_construire_table_ancres_ancre_sur_separateur_explicite_ne_masque_pas_un_glob_borne_reel(tmp_path):
    # Non-régression : la même forme (ancre sur le séparateur `:` d'une clé explicite
    # arbitraire), mais avec la valeur ancrée ne portant qu'un glob BORNÉ légitime — le résultat
    # doit rester conforme (pas de faux positif introduit par le correctif round 54).
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        '? defaults\n: &md >-\n  evidence/reviews/**/*.md\nsecret:\n  ignored_paths: [*md]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_gitguardian_yaml_reel_du_depot_toujours_conforme_apres_round54():
    # Non-régression directe sur le fichier réel du dépôt, après le round 54 (ancre sur le
    # séparateur `:` d'une clé explicite arbitraire) : le verdict ne doit rien changer.
    ok, motifs = check_gitguardian_scope.verifier(REPO / ".gitguardian.yaml")
    assert ok is True, f"exclusion(s) markdown globale(s) réintroduite(s) : {motifs}"


def test_parser_reconnait_secret_racine_explicite_reduite_a_un_alias(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 55, GPT-5.6-Terra-Pro) : la clé `secret`
    # racine réduite à un alias direct (round 30) peut aussi être exprimée en syntaxe EXPLICITE
    # (`? secret\n: *cfg`) — `_LIGNE_SECRET_ALIAS` ne reconnaît que la forme sur une seule ligne.
    # Vérifié empiriquement contre PyYAML.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &cfg\n  ignored_paths:\n    - >-\n      **/*.md\n? secret\n: *cfg\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_ignore_un_alias_secret_explicite_homonyme_imbrique(tmp_path):
    # Non-régression CRITIQUE (même invariant que le round 45/49 : racine à l'indentation 0) —
    # un `? secret\n: *cfg` HOMONYME imbriqué sous un autre parent ne doit PAS être accepté
    # comme la vraie clé racine. Vérifié empiriquement contre PyYAML.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &cfg\n  ignored_paths:\n    - >-\n      **/*.md\nautre:\n  ? secret\n  : *cfg\nsecret:\n  ignored_paths: ["evidence/reviews/**/*.md"]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["evidence/reviews/**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_secret_racine_explicite_alias_ne_masque_pas_un_glob_borne_reel(tmp_path):
    # Non-régression : la même forme (clé racine explicite réduite à un alias), mais avec
    # l'ancre référencée ne portant qu'un glob BORNÉ légitime — le résultat doit rester
    # conforme (pas de faux positif introduit par le correctif round 55).
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &cfg\n  ignored_paths:\n    - "evidence/reviews/**/*.md"\n? secret\n: *cfg\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_gitguardian_yaml_reel_du_depot_toujours_conforme_apres_round55():
    # Non-régression directe sur le fichier réel du dépôt, après le round 55 (clé racine
    # explicite réduite à un alias) : le verdict ne doit rien changer.
    ok, motifs = check_gitguardian_scope.verifier(REPO / ".gitguardian.yaml")
    assert ok is True, f"exclusion(s) markdown globale(s) réintroduite(s) : {motifs}"


def test_parser_detecte_fusion_yaml_en_liste_flow_dans_secret(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 56, GPT-5.6-Terra-Pro) : la clé de FUSION
    # YAML (round 31) ne reconnaissait qu'une SEULE ancre (`<<: *nom`) — or l'extension
    # `tag:yaml.org,2002:merge` permet aussi une LISTE flow d'ancres (`<<: [*a, *b]`), forme
    # valide vérifiée empiriquement contre PyYAML. Reproduction exacte du reviewer.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &cfg\n  ignored_paths:\n    - >-\n      **/*.md\nsecret:\n  <<: [*cfg]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_detecte_fusion_yaml_en_liste_flow_a_plusieurs_ancres(tmp_path):
    # Non-régression : la liste flow peut référencer PLUSIEURS ancres — chacune doit être
    # résolue, pas seulement la première du jeton `[`.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &cfg1\n  autre_champ: x\nsuite: &cfg2\n  ignored_paths:\n'
        '    - >-\n      **/*.md\nsecret:\n  <<: [*cfg1, *cfg2]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_fusion_liste_flow_hors_de_secret_ne_declenche_pas_de_faux_positif(tmp_path):
    # Non-régression : une fusion en liste flow qui n'est PAS elle-même descendante de `secret`
    # ne doit pas être confondue avec le cas ciblé par ce correctif.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &cfg\n  ignored_paths:\n    - >-\n      **/*.md\nautre:\n  <<: [*cfg]\n'
        'secret:\n  ignored_paths:\n    - "evidence/reviews/**/*.md"\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["evidence/reviews/**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_detecte_fusion_yaml_en_bloc_dans_secret(tmp_path):
    # Gap symétrique comblé proactivement dans la foulée du round 56 : la même « séquence de
    # nœuds mapping » de l'extension merge peut aussi s'écrire en style BLOC plutôt qu'en liste
    # flow (`<<:\n  - *a`) — vérifié empiriquement équivalent à `<<: [*a]` contre PyYAML.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &cfg\n  ignored_paths:\n    - >-\n      **/*.md\nsecret:\n  <<:\n    - *cfg\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_fusion_bloc_tolere_ligne_vide_et_commentaire_entre_items(tmp_path):
    # Non-régression : même discipline que round 6 pour `ignored_paths` lui-même — une ligne
    # vide ou un commentaire seul entre deux items `- *nom` de la séquence bloc de fusion est du
    # YAML valide et ne doit pas arrêter prématurément la collecte des ancres.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &cfg1\n  autre_champ: x\nsuite: &cfg2\n  ignored_paths:\n'
        '    - >-\n      **/*.md\nsecret:\n  <<:\n    - *cfg1\n\n    # commentaire\n    - *cfg2\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_fusion_bloc_hors_de_secret_ne_declenche_pas_de_faux_positif(tmp_path):
    # Non-régression : une fusion en style bloc qui n'est PAS elle-même descendante de `secret`
    # ne doit pas être confondue avec le cas ciblé par ce correctif.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &cfg\n  ignored_paths:\n    - >-\n      **/*.md\nautre:\n  <<:\n    - *cfg\n'
        'secret:\n  ignored_paths:\n    - "evidence/reviews/**/*.md"\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["evidence/reviews/**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_fusion_valeur_vide_sans_item_ensuite_ne_leve_pas(tmp_path):
    # Cas limite : `<<:` sans valeur et sans item de séquence à la suite (fin de fichier ou
    # ligne moins indentée immédiate) — ne doit lever aucune exception et ne rien ajouter.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text('secret:\n  <<:\n', encoding="utf-8")  # proof:allow — clé de schéma YAML, pas un secret réel
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == []
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_gitguardian_yaml_reel_du_depot_toujours_conforme_apres_round56():
    # Non-régression directe sur le fichier réel du dépôt, après le round 56 (fusion YAML en
    # liste flow et en bloc) : le verdict ne doit rien changer.
    ok, motifs = check_gitguardian_scope.verifier(REPO / ".gitguardian.yaml")
    assert ok is True, f"exclusion(s) markdown globale(s) réintroduite(s) : {motifs}"


def test_parser_detecte_secret_alias_vers_ancre_mapping_flow(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 57, GPT-5.6-Terra-Pro) : la clé racine
    # `secret` réduite à un alias direct (round 30) peut référencer une ancre dont la valeur est
    # elle-même un mapping FLOW (round 32) — `_construire_table_ancres` exclut explicitement les
    # ancres-mapping de son périmètre, et le pré-passage round 32 ne cherchait `{` qu'après la
    # clé littérale `secret`, jamais après une ancre nommée différemment. Vérifié empiriquement
    # contre PyYAML : `secret.ignored_paths` résout bien en `['**/*.md']`.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md >-\n  **/*.md\ncfg: &cfg {ignored_paths: [*md]}\nsecret: *cfg\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_detecte_secret_fusion_vers_ancre_mapping_flow(tmp_path):
    # Gap symétrique comblé pour la même cause racine (`noms_alias_racine` unifie les noms
    # d'ancre équivalents-secret, qu'ils viennent d'un alias direct round 30 ou d'une fusion
    # round 31/56) : `<<: *cfg` référençant la même ancre-mapping-flow doit être résolu
    # identiquement. Vérifié empiriquement contre PyYAML.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md >-\n  **/*.md\ncfg: &cfg {ignored_paths: [*md]}\nsecret:\n  <<: *cfg\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_detecte_secret_fusion_liste_vers_ancre_mapping_flow(tmp_path):
    # Même gap symétrique, combiné à la forme LISTE flow de la fusion (round 56). Vérifié
    # empiriquement contre PyYAML.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md >-\n  **/*.md\ncfg: &cfg {ignored_paths: [*md]}\nsecret:\n  <<: [*cfg]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_detecte_ancre_double_guillemets_multiligne_via_continuation_echappee(tmp_path):
    # RC1-015 round 98, revue scellée GPT-5.6-Terra-Pro (MAJEURE bloquante, bug réel) : une
    # chaîne double-guillemets d'ANCRE (`&nom "..."`) peut s'étendre sur PLUSIEURS lignes
    # physiques via une continuation de ligne échappée — même mécanisme que le nom de clé
    # explicite multiligne (round 58, `_decoder_cle_explicite_multiligne`), jamais branché pour
    # la VALEUR d'une ancre avant ce round. Vérifié empiriquement contre PyYAML AVANT correctif.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md "**/*.\\\n  md"\nsecret:\n  ignored_paths: [*md]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_ancre_double_guillemets_multiligne_valeur_sure_ne_declenche_pas_de_faux_positif(tmp_path):
    # Non-régression symétrique du round 98 : une ancre double-guillemets multiligne portant une
    # valeur SÛRE reste correctement résolue sans faux positif — le correctif ne doit pas
    # sur-détecter au-delà de ce que PyYAML résout réellement.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &safe "sa\\\n  fe"\nsecret:\n  ignored_paths: [*safe]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["safe"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_detecte_secret_fusion_flow_dupliquee_derniere_occurrence_gagne(tmp_path):
    # RC1-015 round 96, revue scellée DeepSeek-V4-Pro-0813 (MAJEURE bloquante, bug réel) :
    # `_noms_fusion_dans_mapping_flow` ne traitait que la PREMIÈRE occurrence de clé de fusion
    # `<<` dans un mapping flow (`break` inconditionnel) — une clé `<<` DUPLIQUÉE au sein du
    # même mapping suit pourtant la même sémantique YAML « dernière occurrence gagne » que
    # toute autre clé dupliquée (round 67, déjà vérifiée pour `ignored_paths`). Vérifié
    # empiriquement contre PyYAML : `secret: {<<: *safe, <<: *md}` résout `secret.ignored_paths`  <!-- proof:allow : exemple prose -->
    # vers UNIQUEMENT ce que porte `md` (la fusion `safe` disparaît entièrement, pas de merge).
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'safe: &safe\n  ignored_paths: [x]\nmd: &md\n  ignored_paths: ["**/*.md"]\nsecret: {<<: *safe, <<: *md}\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_fusion_flow_dupliquee_premiere_occurrence_seule_reste_sans_effet(tmp_path):
    # Non-régression symétrique du round 96 : quand seule la PREMIÈRE occurrence de `<<` porte
    # l'exclusion et la SECONDE (qui gagne, sémantique dernière occurrence) porte une valeur
    # sûre, l'exclusion de la première ne doit PLUS apparaître — sinon régression vers l'ancien
    # comportement (traiter la première occurrence au lieu de la dernière).
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'md: &md\n  ignored_paths: ["**/*.md"]\nsafe: &safe\n  ignored_paths: [x]\nsecret: {<<: *md, <<: *safe}\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["x"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_ancre_mapping_flow_hors_noms_alias_racine_ne_declenche_pas_de_faux_positif(tmp_path):
    # Non-régression : une ancre-mapping-flow qui n'est PAS référencée par `secret` (nom absent
    # de `noms_alias_racine`) ne doit pas être confondue avec le cas ciblé par ce correctif.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md >-\n  **/*.md\nautre: &autre {ignored_paths: [*md]}\n'
        'secret:\n  ignored_paths:\n    - "evidence/reviews/**/*.md"\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["evidence/reviews/**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_secret_alias_vers_ancre_mapping_flow_ne_masque_pas_un_glob_borne_reel(tmp_path):
    # Non-régression : même forme, mais avec l'ancre finale ne portant qu'un glob BORNÉ légitime
    # — le résultat doit rester conforme (pas de faux positif introduit par ce correctif).
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &b >-\n  evidence/reviews/**/*.md\ncfg: &cfg {ignored_paths: [*b]}\nsecret: *cfg\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_gitguardian_yaml_reel_du_depot_toujours_conforme_apres_round57():
    # Non-régression directe sur le fichier réel du dépôt, après le round 57 (composition
    # alias/fusion racine vers une ancre-mapping-flow) : le verdict ne doit rien changer.
    ok, motifs = check_gitguardian_scope.verifier(REPO / ".gitguardian.yaml")
    assert ok is True, f"exclusion(s) markdown globale(s) réintroduite(s) : {motifs}"


def test_parser_detecte_cle_explicite_ignored_paths_guillemetee_multiligne(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 58, GPT-5.6-Terra-Pro) : une clé EXPLICITE
    # (`? "..."`) dont le nom est une chaîne double-guillemets peut légitimement s'étendre sur
    # PLUSIEURS lignes physiques via une continuation de ligne échappée (même mécanisme que les
    # VALEURS depuis le round 11) — `_LIGNE_CLE_EXPLICITE` exigeait guillemet ouvrant ET fermant
    # sur la même ligne. Reproduction exacte du reviewer, vérifiée empiriquement contre PyYAML :
    # `secret.ignored_paths` résout bien en `['**/*.md']`.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  ? "ignored_\\\n    paths"\n  :\n    - >-\n      **/*.md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_cle_explicite_multiligne_ne_masque_pas_un_glob_borne_reel(tmp_path):
    # Non-régression : même forme, mais avec le contenu de la liste ne portant qu'un glob BORNÉ
    # légitime — le résultat doit rester conforme.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  ? "ignored_\\\n    paths"\n  :\n    - >-\n      evidence/reviews/**/*.md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_cle_explicite_multiligne_hors_de_secret_ne_declenche_pas_de_faux_positif(tmp_path):
    # Non-régression : une clé explicite multiligne homonyme, mais HORS du mapping `secret`, ne
    # doit pas être confondue avec le cas ciblé par ce correctif.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'autre:\n  ? "ignored_\\\n    paths"\n  :\n    - >-\n      **/*.md\n'
        'secret:\n  ignored_paths:\n    - "evidence/reviews/**/*.md"\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["evidence/reviews/**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_cle_explicite_multiligne_nom_decode_different_ne_leve_pas(tmp_path):
    # Non-régression PROACTIVE (bug trouvé en vérifiant ce correctif) : `_LIGNE_CLE_EXPLICITE`
    # matche à tort un guillemet non refermé via son alternative NUE de repli (le nom décodé
    # capturé n'est alors ni `ignored_paths` ni la clé réelle) — une clé explicite multiligne qui
    # décode en un nom SANS RAPPORT ne doit provoquer ni exception ni faux positif.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  ? "autre_\\\n    champ"\n  :\n    - >-\n      **/*.md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == []
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_cle_explicite_multiligne_deux_continuations_echappees(tmp_path):
    # Non-régression : le mécanisme doit franchir PLUSIEURS continuations de ligne échappées
    # d'affilée (pas seulement une seule), vérifié empiriquement contre PyYAML.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  ? "ignored\\\n    _pa\\\n    ths"\n  :\n    - >-\n      **/*.md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_cle_explicite_quote_jamais_fermee_ne_leve_pas(tmp_path):
    # Cas limite : un guillemet ouvrant sans fermeture nulle part dans le fichier (YAML invalide)
    # ne doit lever aucune exception — comportement défensif, cohérent avec le round 56.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text('secret:\n  ? "ignored_\\\n', encoding="utf-8")  # proof:allow — clé de schéma YAML, pas un secret réel
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == []
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_gitguardian_yaml_reel_du_depot_toujours_conforme_apres_round58():
    # Non-régression directe sur le fichier réel du dépôt, après le round 58 (clé explicite
    # double-guillemets multiligne) : le verdict ne doit rien changer.
    ok, motifs = check_gitguardian_scope.verifier(REPO / ".gitguardian.yaml")
    assert ok is True, f"exclusion(s) markdown globale(s) réintroduite(s) : {motifs}"


def test_parser_detecte_fusion_dans_ancre_mapping_flow_referencee_par_secret(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 59, GPT-5.6-Terra-Pro) : une ancre
    # référencée par `secret` (round 30) peut porter un mapping FLOW (round 32/57) dont le SEUL
    # contenu est une clé de FUSION (`<<`, round 31) vers une AUTRE ancre — ni la recherche de
    # clé directe dans le mapping flow (round 32/57) ni la recherche de fusion textuellement
    # descendante de `secret` (round 31/56) ne couvrent cette composition. Reproduction exacte du
    # reviewer, vérifiée empiriquement contre PyYAML.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md\n  ignored_paths:\n    - >-\n      **/*.md\ncfg: &cfg {<<: *md}\nsecret: *cfg\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_detecte_fusion_liste_dans_ancre_mapping_flow(tmp_path):
    # Non-régression : la forme LISTE de la fusion (round 56, `<<: [*a, *b]`) doit aussi être
    # résolue quand elle apparaît à l'intérieur d'un mapping flow — vérifie que
    # `_noms_fusion_dans_mapping_flow` ne casse pas sur la liste imbriquée (jamais un découpage
    # par virgule appliqué au mapping entier, qui la romprait).
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md\n  ignored_paths:\n    - >-\n      **/*.md\n'
        'autre: &autre\n  x: 1\n'
        'cfg: &cfg {<<: [*md, *autre]}\nsecret: *cfg\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_fusion_dans_ancre_flow_hors_de_secret_ne_declenche_pas_de_faux_positif(tmp_path):
    # Non-régression : une ancre mapping flow fusionnant une AUTRE ancre, mais qui n'est PAS
    # elle-même référencée par `secret`, ne doit pas être confondue avec le cas ciblé.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md\n  ignored_paths:\n    - >-\n      **/*.md\n'
        'cfg: &cfg {<<: *md}\n'
        'secret:\n  ignored_paths:\n    - "evidence/reviews/**/*.md"\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["evidence/reviews/**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_fusion_dans_ancre_flow_ne_masque_pas_une_cle_directe_prioritaire(tmp_path):
    # Non-régression : quand le mapping flow ancré porte À LA FOIS une fusion ET une clé
    # `ignored_paths` DIRECTE, la clé directe doit gagner (sémantique YAML de fusion : les clés
    # explicites du mapping l'emportent sur celles injectées par `<<`) — vérifié empiriquement
    # contre PyYAML. Comportement déjà correct par construction : la recherche de clé directe
    # (round 32/57) est tentée AVANT le repli fusion (round 59), sans changement nécessaire ici.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md\n  ignored_paths:\n    - >-\n      **/*.txt\n'
        'cfg: &cfg {<<: *md, ignored_paths: ["evidence/reviews/**/*.md"]}\nsecret: *cfg\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_fusion_liste_flow_premier_element_gagne_meme_dangereux(tmp_path):
    # RC1-015 round 99, revue scellée GPT-5.6-Terra-Pro (MAJEURE bloquante, bug réel).
    # Reproduction exacte du reviewer : `<<: [*danger, *safe]` — la sémantique YAML merge-key
    # fait gagner le PREMIER élément (`danger`) sur le second, quelle que soit sa position
    # textuelle dans le fichier. Vérifié empiriquement contre PyYAML AVANT correctif.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'safe: &safe\n  ignored_paths: [safe]\ndanger: &danger\n  ignored_paths:\n    - >-\n      **/*.md\nsecret:\n  <<: [*danger, *safe]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_fusion_liste_bloc_premier_element_gagne_meme_dangereux(tmp_path):
    # Même reproduction round 99, forme BLOC de la séquence de fusion (round 56).
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'safe: &safe\n  ignored_paths: [safe]\ndanger: &danger\n  ignored_paths:\n    - >-\n      **/*.md\nsecret:\n  <<:\n    - *danger\n    - *safe\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_fusion_liste_flow_ordre_inverse_le_sur_ne_gagne_pas_a_tort(tmp_path):
    # Non-régression symétrique du round 99 : quand la valeur SÛRE est PREMIÈRE dans la liste
    # (`[*safe, *danger]`), c'est elle qui doit gagner — le correctif ne doit PAS toujours
    # préférer la valeur dangereuse, seulement respecter fidèlement l'ordre réel de la liste.
    # Vérifié empiriquement contre PyYAML : `secret.ignored_paths` résout vers `safe` seul.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'safe: &safe\n  ignored_paths: [safe]\ndanger: &danger\n  ignored_paths:\n    - >-\n      **/*.md\nsecret:\n  <<: [*safe, *danger]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["safe"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_fusion_liste_mapping_flow_racine_premier_element_gagne(tmp_path):
    # RC1-015 round 100, revue scellée GPT-5.6-Terra-Pro (MAJEURE bloquante, bug réel) : le
    # correctif round 99 ne couvrait que les fusions BLOC directement descendantes de `secret`
    # (`_noms_ancres_fusionnees_dans_secret`) — la même famille de bug subsistait pour une
    # fusion-liste au sein d'un mapping FLOW porté par la clé racine (`{<<: [*a, *b]}`, round 60), qui  <!-- proof:allow : exemple prose -->
    # passe par la fonction SŒUR `_noms_fusion_dans_mapping_flow` (round 59), laquelle
    # retournait un `set[str]` sans ordre. Vérifié empiriquement contre PyYAML AVANT correctif.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'safe: &safe\n  ignored_paths: [safe]\ndanger: &danger\n  ignored_paths: ["**/*.md"]\nsecret: {<<: [*danger, *safe]}\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_fusion_liste_mapping_flow_racine_ordre_inverse_le_sur_ne_gagne_pas_a_tort(tmp_path):
    # Non-régression symétrique round 100 : la valeur sûre en première position gagne.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'safe: &safe\n  ignored_paths: [safe]\ndanger: &danger\n  ignored_paths: ["**/*.md"]\nsecret: {<<: [*safe, *danger]}\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["safe"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_fusion_liste_dans_ancre_flow_referencee_par_alias_premier_element_gagne(tmp_path):
    # Round 100 : même correctif, 3e site d'appel — fusion-liste au sein du mapping flow d'une
    # ANCRE référencée par `secret` via un alias direct (round 59 : `cfg: &cfg {<<: [...]}` +
    # un alias `*cfg` de la clé racine). Vérifié empiriquement contre PyYAML.  <!-- proof:allow : exemple prose -->
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'safe: &safe\n  ignored_paths: [safe]\ndanger: &danger\n  ignored_paths: ["**/*.md"]\ncfg: &cfg {<<: [*danger, *safe]}\nsecret: *cfg\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_position_fusion_ne_collisionne_jamais_avec_une_position_entiere_reelle():
    # RC1-015 round 101, revue scellée GPT-5.6-Terra-Pro (MAJEURE bloquante, bug réel) : le
    # décalage ENTIER du round 100 (`position - index_jeton`) pouvait entrer en COLLISION avec
    # la position réelle d'un contenu totalement indépendant ailleurs dans le document (ex. une
    # occurrence antérieure de la clé racine `secret`), faussant le départage `position >
    # meilleur_trouve_ligne` (jamais à égalité) au profit de l'ordre de balayage plutôt que de
    # la sémantique YAML. `_position_fusion` utilise désormais un décalage FRACTIONNAIRE —
    # preuve mathématique directe qu'il reste TOUJOURS strictement dans l'intervalle ouvert
    # `(position_base - 1, position_base]`, donc ne peut jamais atteindre ni dépasser un entier
    # distinct (quelle que soit la longueur de la liste de fusion).
    #
    # RC1-015 round 102, revue scellée GPT-5.6-Terra-Pro (MAJEURE bloquante, bug réel dans le
    # correctif round 101 lui-même) : le premier diviseur (constante FIXE 1_000_000) ne
    # garantissait la propriété que pour `index_jeton < 1_000_000` — à `index_jeton ==
    # 1_000_000` PILE, la fraction valait EXACTEMENT 1, recréant la collision
    # (`_position_fusion(10, 1_000_000) == 9`, PAS strictement `> 9`). Corrigé avec un diviseur
    # DYNAMIQUE (`index_jeton + 1`), mathématiquement < 1 pour TOUT `index_jeton >= 0` sans
    # AUCUNE borne — ce test couvre désormais explicitement l'ancien seuil qui cassait le round
    # 101, et des valeurs arbitrairement plus grandes, pour prouver l'absence de toute limite.
    for position_base in (0, 1, 5, 100, 10_000):
        for index_jeton in (0, 1, 2, 999, 999_999, 1_000_000, 1_000_001, 10**9, 10**12):
            valeur = check_gitguardian_scope._position_fusion(position_base, index_jeton)
            assert (position_base - 1) < valeur <= position_base
    # Non-régression explicite : index 0 reste EXACTEMENT la position pleine (pas de fraction).
    assert check_gitguardian_scope._position_fusion(7, 0) == 7
    assert isinstance(check_gitguardian_scope._position_fusion(7, 0), int)
    # Reproduction EXACTE de la collision round 102 (index_jeton == ancien diviseur fixe) :
    # confirmée résolue, ne retombe plus jamais exactement sur l'entier inférieur.
    assert check_gitguardian_scope._position_fusion(10, 1_000_000) != 9
    assert 9 < check_gitguardian_scope._position_fusion(10, 1_000_000) <= 10


def test_position_fusion_arithmetique_exacte_aucune_perte_de_precision_flottante():
    # RC1-015 round 106, revue scellée GPT-5.6-Terra-Pro (finding mineur, réel) : la garantie
    # « `index_jeton / (index_jeton + 1)` mathématiquement < 1 pour TOUT `index_jeton` » (round
    # 102) était FAUSSE en arithmétique FLOTTANTE IEEE-754 (précision finie, ~15-17 chiffres
    # significatifs) — pour un `index_jeton` suffisamment grand, la division flottante
    # s'arrondissait à `1.0` pile, recréant la collision. Vérifié empiriquement AVANT correctif :
    # `_position_fusion(10, 10**20) == 9.0` (le test round 101/102 ne couvrait que jusqu'à
    # `10**12`, jamais assez grand pour révéler la perte de précision).
    #
    # Round 106 : `fractions.Fraction` (arithmétique rationnelle EXACTE, stdlib pur) au lieu de
    # `float` — ce test prouve l'absence de perte de précision jusqu'à des grandeurs où AUCUNE
    # représentation flottante ne pourrait plus tenir la garantie (10**1000, largement au-delà
    # de toute limite flottante réaliste).
    for index_jeton in (10**16, 10**20, 10**100, 10**1000):
        valeur = check_gitguardian_scope._position_fusion(10, index_jeton)
        assert 9 < valeur <= 10
        assert valeur != 9
    # Reproduction EXACTE de la collision round 106 (perte de précision flottante) : confirmée
    # résolue.
    from fractions import Fraction

    assert isinstance(
        check_gitguardian_scope._position_fusion(10, 10**20) - 9, Fraction
    )


def test_parser_fusion_liste_flow_racine_ne_masque_pas_une_occurrence_secret_anterieure(tmp_path):
    # RC1-015 round 101 : reproduction du RISQUE identifié par le reviewer (collision entre le
    # décalage d'un élément démoté et la position d'une occurrence ANTÉRIEURE et indépendante de
    # la clé racine `secret`, dupliquée — sémantique YAML « dernière occurrence gagne »). Une
    # PREMIÈRE clé racine `secret` porte un contenu SÛR direct ; une SECONDE (qui doit
    # l'emporter entièrement, clé dupliquée) fusionne `[*safeA, *dangerB]` — `dangerB` (démoté,
    # 2e élément) reçoit une position fractionnaire juste sous celle de la fusion, potentiellement
    # très proche de la ligne de la première occurrence. Vérifié empiriquement contre PyYAML
    # AVANT d'écrire cette assertion : la seconde racine gagne entièrement, `safeA` (1er élément)
    # l'emporte sur `dangerB` dans la fusion — résultat final SÛR.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'dangerB: &dangerB\n  ignored_paths: ["**/*.md"]\nsafeA: &safeA\n  ignored_paths: [safeval]\nsecret:\n  ignored_paths: [placeholder]\nsecret: {<<: [*safeA, *dangerB]}\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["safeval"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_fusion_dans_ancres_flow_deux_niveaux_indirection(tmp_path):
    # Non-régression : la boucle à point fixe de `noms_alias_racine` doit franchir PLUSIEURS
    # niveaux d'indirection d'affilée (pas seulement un seul) — `cfg` fusionne `cfg2`, qui
    # fusionne `md`. Vérifié empiriquement contre PyYAML.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md\n  ignored_paths:\n    - >-\n      **/*.md\n'
        'cfg2: &cfg2 {<<: *md}\n'
        'cfg: &cfg {<<: *cfg2}\n'
        'secret: *cfg\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_gitguardian_yaml_reel_du_depot_toujours_conforme_apres_round59():
    # Non-régression directe sur le fichier réel du dépôt, après le round 59 (fusion à
    # l'intérieur d'un mapping flow ancré) : le verdict ne doit rien changer.
    ok, motifs = check_gitguardian_scope.verifier(REPO / ".gitguardian.yaml")
    assert ok is True, f"exclusion(s) markdown globale(s) réintroduite(s) : {motifs}"


def test_parser_detecte_fusion_dans_flow_racine_secret(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 60, GPT-5.6-Terra-Pro) : une clé de
    # FUSION (`<<`) peut apparaître DIRECTEMENT dans le mapping flow de la clé racine elle-même
    # (valeur `{<<: *md}`), sans aucune indirection d'ancre — ni la recherche de clé directe
    # `ignored_paths` (round 32) ni la fusion dans le mapping flow d'une ancre RÉFÉRENCÉE par
    # alias (round 59) ne couvrent ce cas. Reproduction exacte du reviewer, vérifiée
    # empiriquement contre PyYAML.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md\n  ignored_paths:\n    - >-\n      **/*.md\nsecret: {<<: *md}\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_detecte_fusion_liste_dans_flow_racine_secret(tmp_path):
    # Non-régression : la forme LISTE de la fusion (round 56) doit aussi être résolue quand
    # elle apparaît directement dans le mapping flow de `secret`.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md\n  ignored_paths:\n    - >-\n      **/*.md\n'
        'autre: &autre\n  x: 1\n'
        'secret: {<<: [*md, *autre]}\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_fusion_dans_flow_racine_secret_ne_masque_pas_une_cle_directe_prioritaire(tmp_path):
    # Non-régression : quand le mapping flow racine porte à la fois une fusion ET une clé
    # `ignored_paths` DIRECTE, la clé directe doit gagner (sémantique YAML de fusion), vérifié
    # empiriquement contre PyYAML.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md\n  ignored_paths:\n    - >-\n      **/*.txt\n'
        'secret: {<<: *md, ignored_paths: ["evidence/reviews/**/*.md"]}\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_fusion_dans_flow_racine_secret_ne_masque_pas_un_glob_borne_reel(tmp_path):
    # Non-régression : même forme, mais avec l'ancre fusionnée ne portant qu'un glob BORNÉ
    # légitime — le résultat doit rester conforme.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md\n  ignored_paths:\n    - >-\n      evidence/reviews/**/*.md\n'
        'secret: {<<: *md}\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_detecte_fusion_dans_flow_racine_secret_explicite(tmp_path):
    # Gap symétrique trouvé PROACTIVEMENT en vérifiant ce correctif (bug réel) : la clé racine
    # `secret` exprimée en syntaxe EXPLICITE (round 49) avec une valeur mapping flow inline
    # (round 50, `? secret\n: {<<: *md}`) souffrait de la MÊME limite que la forme classique —
    # le pré-passage round 50 ne cherchait, lui aussi, que la clé directe. Vérifié empiriquement
    # contre PyYAML.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md\n  ignored_paths:\n    - >-\n      **/*.md\n? secret\n: {<<: *md}\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_gitguardian_yaml_reel_du_depot_toujours_conforme_apres_round60():
    # Non-régression directe sur le fichier réel du dépôt, après le round 60 (fusion dans le
    # mapping flow de `secret` elle-même, forme classique et explicite) : le verdict ne doit
    # rien changer.
    ok, motifs = check_gitguardian_scope.verifier(REPO / ".gitguardian.yaml")
    assert ok is True, f"exclusion(s) markdown globale(s) réintroduite(s) : {motifs}"


def test_parser_ancre_avec_deux_points_termine_correctement_le_nom_ancre(tmp_path):
    # Round 61 — finding RÉFUTÉ après vérification empirique (GPT-5.6-Terra-Pro REJECT) : le
    # reviewer affirmait que `_CARACTERE_ANCRE` devrait accepter `:` (et `?`) dans un nom
    # d'ancre/alias, au nom de la grammaire YAML 1.2. Reproduction exacte du reviewer, vérifiée
    # empiriquement contre PyYAML — deux preuves REFUTENT le finding :
    # (1) le scanner RÉEL de PyYAML (`yaml.scanner.Scanner.scan_anchor`, lu directement) restreint
    #     DÉLIBÉRÉMENT les noms d'ancre/alias à `[A-Za-z0-9_-]` (commentaire du code source :
    #     « we restrict aliases to numbers and ASCII letters », précisément pour éviter
    #     l'ambiguïté `[ *alias, value ]` / `[ *alias , value ]`) — `:` est un caractère
    #     TERMINATEUR explicite (`ch not in '\\0 \\t\\r\\n...?:,]}%@\\`'` lève une erreur), jamais
    #     un caractère de nom valide.
    # (2) la reproduction du reviewer elle-même, passée dans PyYAML réel, ne résout MÊME PAS en
    #     une exclusion Markdown : `defaults` devient la chaîne `':glob >- **/*.md'`, et
    #     `secret.ignored_paths` devient `[{':glob >- **/*.md': 'glob'}]` — une structure absurde,
    #     jamais l'exclusion globale interdite. `verifier()` reste donc conforme (True, []) sur
    #     ce fichier, ce qui est FACTUELLEMENT CORRECT vis-à-vis de PyYAML, pas un défaut.
    # Décision : AUCUN changement de code (le comportement pour ce cas était déjà correct).
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md:glob >-\n  **/*.md\nsecret:\n  ignored_paths: [*md:glob]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_ancre_nom_correctement_tronque_avant_deux_points_reste_resoluble(tmp_path):
    # Non-régression complémentaire (round 61) : une ancre légitimement nommée SANS `:`
    # (`&md`, correctement tronquée par PyYAML avant tout `:` suivant sur la même ligne dans un
    # contexte SANS rapport) continue de se résoudre normalement via un alias `*md` — le
    # comportement déjà correct de `_CARACTERE_ANCRE` (terminaison à `:`) n'empêche pas la
    # résolution normale des ancres qui n'en contiennent pas.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &md >-\n  **/*.md\nsecret:\n  ignored_paths: [*md]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_detecte_liste_flow_ancree_aliasee_comme_ignored_paths(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 62, GPT-5.6-Terra-Pro) : une ancre
    # portant une SÉQUENCE FLOW sur la même ligne (`paths: &paths [*md]`) était stockée comme
    # une chaîne LITTÉRALE brute (`"[*md]"`) plutôt que résolue comme une liste —
    # `_construire_table_ancres` ne modélisait que scalaire/bloc/guillemeté/séquence-bloc, pas
    # une séquence FLOW sur la même ligne que l'ancre. Reproduction exacte du reviewer, vérifiée
    # empiriquement contre PyYAML : `secret.ignored_paths` résout bien en `['**/*.md']`.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'md: &md >-\n  **/*.md\npaths: &paths [*md]\nsecret:\n  ignored_paths: *paths\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_detecte_liste_flow_ancree_multiligne(tmp_path):
    # Non-régression : la liste flow ancrée peut légitimement s'étendre sur PLUSIEURS lignes
    # physiques (round 17) — vérifie que `_construire_table_ancres` avance correctement son
    # index de ligne après avoir consommé une telle liste (pas de ligne sautée ni re-scannée).
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'md: &md >-\n  **/*.md\npaths: &paths [\n  *md\n]\nsecret:\n  ignored_paths: *paths\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_ligne_suivante_toujours_scannee_apres_liste_flow_ancree_multiligne(tmp_path):
    # Non-régression CRITIQUE : une ancre SCALAIRE définie sur la ligne suivant IMMÉDIATEMENT la
    # fermeture d'une liste flow ancrée multiligne doit rester correctement résolue — vérifie
    # que l'avancement d'index (round 62) ne saute ni ne re-scanne aucune ligne.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'md: &md >-\n  **/*.md\npaths: &paths [\n  *md\n]\n'
        'autre: &autre "evidence/reviews/**/*.md"\nsecret:\n  ignored_paths: [*autre]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["evidence/reviews/**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_liste_flow_ancree_ne_masque_pas_un_glob_borne_reel(tmp_path):
    # Non-régression : même forme, mais avec l'ancre référencée ne portant qu'un glob BORNÉ
    # légitime — le résultat doit rester conforme.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'md: &md >-\n  evidence/reviews/**/*.md\npaths: &paths [*md]\n'
        'secret:\n  ignored_paths: *paths\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_liste_flow_ancree_plusieurs_items(tmp_path):
    # Non-régression : la liste flow ancrée peut porter PLUSIEURS items (mélange alias et
    # scalaires) — chacun doit être résolu individuellement, pas seulement le premier.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'md: &md >-\n  **/*.md\nsc: &sc "safe.txt"\npaths: &paths [*md, *sc]\n'
        'secret:\n  ignored_paths: *paths\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md", "safe.txt"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_gitguardian_yaml_reel_du_depot_toujours_conforme_apres_round62():
    # Non-régression directe sur le fichier réel du dépôt, après le round 62 (liste flow
    # ancrée résolue dans la table d'ancres) : le verdict ne doit rien changer.
    ok, motifs = check_gitguardian_scope.verifier(REPO / ".gitguardian.yaml")
    assert ok is True, f"exclusion(s) markdown globale(s) réintroduite(s) : {motifs}"


def test_parser_detecte_cle_racine_explicite_multiligne_forme_bloc(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 63, GPT-5.6-Terra-Pro) : la clé racine
    # `secret` exprimée en syntaxe EXPLICITE (round 49) peut elle-même avoir un nom en chaîne
    # double-guillemets MULTILIGNE (round 58, continuation échappée) — cette capacité n'avait
    # été branchée que dans la recherche de `ignored_paths`, jamais dans la remontée
    # d'ascendance vers la clé racine (`_est_ligne_secret_explicite`). Reproduction exacte du
    # reviewer, vérifiée empiriquement contre PyYAML.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        '? "sec\\\n  ret"\n:\n  ignored_paths:\n    - >-\n      **/*.md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_detecte_cle_racine_explicite_multiligne_forme_alias(tmp_path):
    # Gap symétrique trouvé PROACTIVEMENT en vérifiant ce correctif (bug réel) : la même limite
    # existait dans `_nom_ancre_secret_explicite_alias` (round 55, forme alias `? secret\n:
    # *cfg`) — vérifiée empiriquement contre PyYAML.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &cfg\n  ignored_paths:\n    - >-\n      **/*.md\n? "sec\\\n  ret"\n: *cfg\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_cle_racine_explicite_multiligne_homonyme_imbrique_ne_declenche_pas_de_faux_positif(tmp_path):
    # Non-régression CRITIQUE (même invariant que les rounds 45/49/55) : une clé racine
    # explicite multiligne HOMONYME, imbriquée sous un autre parent, ne doit PAS être acceptée
    # comme la vraie clé racine.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'defaults: &cfg\n  ignored_paths:\n    - >-\n      **/*.md\n'
        'autre:\n  ? "sec\\\n    ret"\n  : *cfg\n'
        'secret:\n  ignored_paths:\n    - "evidence/reviews/**/*.md"\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["evidence/reviews/**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_cle_racine_explicite_multiligne_ne_masque_pas_un_glob_borne_reel(tmp_path):
    # Non-régression : même forme (bloc et alias), mais avec un glob BORNÉ légitime — le
    # résultat doit rester conforme.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        '? "sec\\\n  ret"\n:\n  ignored_paths:\n    - >-\n      evidence/reviews/**/*.md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_cle_racine_explicite_plusieurs_continuations_echappees(tmp_path):
    # Non-régression : le mécanisme doit franchir PLUSIEURS continuations de ligne échappées
    # d'affilée pour la clé RACINE explicite (pas seulement pour `ignored_paths`, round 58).
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        '? "s\\\n  ec\\\n  ret"\n:\n  ignored_paths:\n    - >-\n      **/*.md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_gitguardian_yaml_reel_du_depot_toujours_conforme_apres_round63():
    # Non-régression directe sur le fichier réel du dépôt, après le round 63 (clé racine
    # explicite multiligne, forme bloc et alias) : le verdict ne doit rien changer.
    ok, motifs = check_gitguardian_scope.verifier(REPO / ".gitguardian.yaml")
    assert ok is True, f"exclusion(s) markdown globale(s) réintroduite(s) : {motifs}"


def test_parser_detecte_ancre_de_sequence_dans_mapping_flow(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 65, GPT-5.6-Terra-Pro) : une ancre peut
    # porter une clé À L'INTÉRIEUR d'un mapping FLOW (`holder: { paths: &paths [*base] }`) —
    # `_PREFIXE_AVANT_ANCRE` n'acceptait que le début de ligne, `-`, `:` seul, ou UNE clé unique
    # depuis le début de ligne, jamais une clé EXTÉRIEURE suivie d'un `{` ouvrant avant la clé
    # locale. Reproduction exacte du reviewer, vérifiée empiriquement contre PyYAML :
    # `secret.ignored_paths` résout bien en `['**/*.md']`.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'base: &base >-\n  **/*.md\nholder: { paths: &paths [*base] }\nsecret:\n  ignored_paths: *paths\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_detecte_ancre_dans_mapping_flow_imbrique_deux_niveaux(tmp_path):
    # Non-régression : le mapping flow contenant l'ancre peut lui-même être imbriqué sur
    # PLUSIEURS niveaux — seule la frontière LOCALE immédiatement avant la clé importe, pas la
    # profondeur d'imbrication.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'base: &base >-\n  **/*.md\na: { b: { paths: &paths [*base] } }\nsecret:\n  ignored_paths: *paths\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_detecte_ancre_dans_mapping_flow_deuxieme_cle_apres_virgule(tmp_path):
    # Non-régression : l'ancre peut aussi porter sur une clé qui n'est PAS la première du
    # mapping flow (précédée d'une virgule, pas d'une accolade ouvrante directe).
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'base: &base >-\n  **/*.md\nholder: { x: 1, paths: &paths [*base] }\nsecret:\n  ignored_paths: *paths\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_ancre_dans_mapping_flow_hors_de_secret_ne_declenche_pas_de_faux_positif(tmp_path):
    # Non-régression : une ancre dans un mapping flow qui n'est PAS référencée par `secret` ne
    # doit pas être confondue avec le cas ciblé par ce correctif.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'base: &base >-\n  **/*.md\nholder: { paths: &paths [*base] }\n'
        'secret:\n  ignored_paths:\n    - "evidence/reviews/**/*.md"\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["evidence/reviews/**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_ancre_dans_mapping_flow_ne_masque_pas_un_glob_borne_reel(tmp_path):
    # Non-régression : même forme, mais avec l'ancre ne portant qu'un glob BORNÉ légitime — le
    # résultat doit rester conforme.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'base: &base >-\n  evidence/reviews/**/*.md\nholder: { paths: &paths [*base] }\n'
        'secret:\n  ignored_paths: *paths\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_ancre_mid_scalaire_toujours_pas_une_ancre_apres_round65(tmp_path):
    # Non-régression CRITIQUE (round 48) : un `&nom` au MILIEU d'un scalaire nu déjà commencé
    # ne doit toujours PAS être traité comme une ancre — l'élargissement round 65 (préfixe
    # extérieur se terminant par `{`/`,`) ne doit pas rouvrir ce cas.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'note: foo&md safe\nsecret:\n  ignored_paths:\n    - "evidence/reviews/**/*.md"\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_gitguardian_yaml_reel_du_depot_toujours_conforme_apres_round65():
    # Non-régression directe sur le fichier réel du dépôt, après le round 65 (ancre de séquence
    # dans un mapping flow) : le verdict ne doit rien changer.
    ok, motifs = check_gitguardian_scope.verifier(REPO / ".gitguardian.yaml")
    assert ok is True, f"exclusion(s) markdown globale(s) réintroduite(s) : {motifs}"


def test_parser_detecte_deuxieme_occurrence_ignored_paths_bloc_dupliquee(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 67, GPT-5.6-Terra-Pro) : PyYAML accepte
    # silencieusement une clé `ignored_paths` DUPLIQUÉE au sein du même mapping `secret` — la
    # DERNIÈRE occurrence l'emporte, jamais une erreur. Le cliquet retournait sur la PREMIÈRE
    # occurrence trouvée, laissant une seconde occurrence — pourtant sémantiquement gagnante —
    # jamais examinée. Reproduction exacte du reviewer, vérifiée empiriquement contre PyYAML.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  ignored_paths:\n    - safe\n  ignored_paths:\n    - >-\n      **/*.md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_detecte_deuxieme_occurrence_ignored_paths_flow_dupliquee(tmp_path):
    # Gap symétrique comblé proactivement (même round, même cause racine) : la forme FLOW
    # (round 32, clé racine réduite à un mapping flow avec `ignored_paths` répétée deux fois)
    # souffrait de la même limite dans `_resoudre_ignored_paths_dans_mapping_flow` (round 41) —
    # sans être toujours rattrapée par le filet textuel quand la seconde valeur vit dans un
    # alias vers un scalaire bloc non guillemeté. Vérifié empiriquement contre PyYAML.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'md: &md >-\n  **/*.md\nsecret: {ignored_paths: [safe], ignored_paths: [*md]}\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_duplication_ordre_inverse_reste_conforme(tmp_path):
    # Non-régression : quand c'est la SECONDE occurrence (celle qui gagne) qui porte un glob
    # BORNÉ légitime — et la PREMIÈRE le motif interdit — le résultat doit rester conforme
    # (la première ne doit plus jamais gagner, quel que soit son contenu).
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  ignored_paths:\n    - >-\n      **/*.md\n  ignored_paths:\n    - "evidence/reviews/**/*.md"\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_trois_occurrences_ignored_paths_la_derniere_gagne(tmp_path):
    # Non-régression : le mécanisme doit franchir PLUSIEURS occurrences dupliquées d'affilée
    # (pas seulement 2), toujours la DERNIÈRE qui gagne.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  ignored_paths:\n    - a\n  ignored_paths:\n    - b\n  ignored_paths:\n    - >-\n      **/*.md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_duplication_formes_melangees_alias_puis_bloc(tmp_path):
    # Non-régression : la duplication peut mélanger des FORMES différentes (alias direct suivi
    # de forme bloc classique) — la dernière forme rencontrée doit toujours gagner, quelle que
    # soit sa forme syntaxique.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'sc: &sc ["safe"]\n'
        'secret:\n  ignored_paths: *sc\n  ignored_paths:\n    - >-\n      **/*.md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_duplication_ne_masque_pas_une_occurrence_hors_de_secret(tmp_path):
    # Non-régression CRITIQUE : une occurrence `ignored_paths` HORS de `secret`, placée APRÈS
    # la vraie occurrence dans le document, ne doit JAMAIS être confondue avec une duplication
    # gagnante — l'invariant d'ascendance (`_est_descendante_de_secret`, round 19) reste
    # entièrement respecté par le mécanisme round 67.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  ignored_paths:\n    - >-\n      **/*.md\nautre:\n  ignored_paths:\n    - safe\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_derniere_liste_jamais_refermee_en_fin_de_fichier(tmp_path):
    # Cas limite : la dernière occurrence dupliquée n'est jamais refermée par une ligne
    # non-item (le fichier se termine en plein milieu de son accumulation) — ses items
    # doivent quand même l'emporter sur toute occurrence antérieure.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  ignored_paths:\n    - safe\n  ignored_paths:\n    - >-\n      **/*.md',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_gitguardian_yaml_reel_du_depot_toujours_conforme_apres_round67():
    # Non-régression directe sur le fichier réel du dépôt, après le round 67 (clé `ignored_paths`
    # dupliquée, formes bloc et flow, dernière occurrence gagnante) : le verdict ne doit rien
    # changer.
    ok, motifs = check_gitguardian_scope.verifier(REPO / ".gitguardian.yaml")
    assert ok is True, f"exclusion(s) markdown globale(s) réintroduite(s) : {motifs}"


def test_parser_detecte_duplication_flow_value_puis_bloc(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 68, GPT-5.6-Terra-Pro) : le correctif
    # round 67 (« dernière occurrence gagne ») ne couvrait que les formes traitées PAR la boucle
    # principale — le pré-passage dédié à `ignored_paths: [...]` (valeur FLOW inline pour une
    # clé en syntaxe bloc, rounds 12/17) `return`ait toujours immédiatement sur son premier
    # candidat, AVANT même que la boucle principale n'ait la moindre chance d'examiner une
    # occurrence ultérieure en forme bloc. Reproduction exacte du reviewer, vérifiée
    # empiriquement contre PyYAML.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  ignored_paths: [safe]\n  ignored_paths:\n    - >-\n      **/*.md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_duplication_bloc_puis_flow_value_ordre_inverse(tmp_path):
    # Non-régression : l'ordre inverse (bloc PREMIER, valeur flow SECONDE et gagnante) doit
    # aussi fonctionner — la comparaison de position doit s'appliquer symétriquement quel que
    # soit le sens de la transition entre les deux mécanismes.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  ignored_paths:\n    - >-\n      **/*.md\n  ignored_paths: ["evidence/reviews/**/*.md"]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_duplication_trois_formes_melangees_alias_flow_bloc(tmp_path):
    # Non-régression : trois occurrences consécutives mélangeant TROIS formes distinctes
    # (alias, valeur flow inline, bloc classique) — la DERNIÈRE (bloc) doit gagner, quel que
    # soit le mécanisme qui la trouve.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'md: &md >-\n  **/*.txt\n'
        'secret:\n  ignored_paths: *md\n  ignored_paths: ["safe.txt"]\n  ignored_paths:\n    - >-\n      **/*.md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_duplication_flow_value_unique_hors_secret_ne_declenche_pas_de_faux_positif(tmp_path):
    # Non-régression CRITIQUE : une occurrence en valeur flow inline HORS de `secret` ne doit
    # jamais être confondue avec une duplication gagnante — l'invariant d'ascendance
    # (`_est_descendante_de_secret`, round 19) reste entièrement respecté.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  ignored_paths:\n    - >-\n      **/*.md\nautre:\n  ignored_paths: [safe]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_gitguardian_yaml_reel_du_depot_toujours_conforme_apres_round68():
    # Non-régression directe sur le fichier réel du dépôt, après le round 68 (duplication
    # croisant la forme valeur-flow-inline et la forme bloc) : le verdict ne doit rien changer.
    ok, motifs = check_gitguardian_scope.verifier(REPO / ".gitguardian.yaml")
    assert ok is True, f"exclusion(s) markdown globale(s) réintroduite(s) : {motifs}"


def test_parser_detecte_cle_racine_secret_dupliquee_flow_puis_bloc(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 69, GPT-5.6-Terra-Pro) : PyYAML accepte
    # silencieusement une clé RACINE `secret` DUPLIQUÉE (pas seulement `ignored_paths` dans son
    # mapping, déjà couvert rounds 67/68) — la DERNIÈRE occurrence l'emporte. Le pré-passage
    # round 32 (clé racine réduite à un mapping flow entier) `return`ait immédiatement sur son
    # premier candidat trouvé. Reproduction exacte du reviewer, vérifiée empiriquement contre
    # PyYAML.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret: {ignored_paths: [safe]}\nsecret:\n  ignored_paths:\n    - >-\n      **/*.md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_duplication_racine_ordre_inverse_reste_conforme(tmp_path):
    # Non-régression : ordre inversé (première occurrence interdite, seconde bornée et
    # gagnante) doit rester conforme.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  ignored_paths:\n    - >-\n      **/*.md\nsecret: {ignored_paths: ["evidence/reviews/**/*.md"]}\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_detecte_cle_racine_secret_dupliquee_explicite_flow_puis_bloc(tmp_path):
    # Gap symétrique comblé proactivement (même round, même cause racine) : le pré-passage
    # round 50 (`? secret\n: {...}`, forme EXPLICITE de la clé racine avec valeur mapping flow
    # inline) souffrait de la même limite — vérifié empiriquement contre PyYAML.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        '? secret\n: {ignored_paths: [safe]}\nsecret:\n  ignored_paths:\n    - >-\n      **/*.md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_duplication_racine_trois_formes_melangees(tmp_path):
    # Non-régression : trois occurrences RACINE consécutives mélangeant TROIS formes (flow,
    # explicite-flow, bloc classique) — la DERNIÈRE (bloc) doit gagner.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret: {ignored_paths: [a]}\n? secret\n: {ignored_paths: [b]}\nsecret:\n  ignored_paths:\n    - >-\n      **/*.md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_gitguardian_yaml_reel_du_depot_toujours_conforme_apres_round69():
    # Non-régression directe sur le fichier réel du dépôt, après le round 69 (clé racine
    # `secret` dupliquée, formes flow et explicite-flow) : le verdict ne doit rien changer.
    ok, motifs = check_gitguardian_scope.verifier(REPO / ".gitguardian.yaml")
    assert ok is True, f"exclusion(s) markdown globale(s) réintroduite(s) : {motifs}"


def test_parser_detecte_cle_racine_secret_dupliquee_alias_puis_bloc(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 70, GPT-5.6-Terra-Pro) : la limite
    # documentée round 69 (pré-passage round 57, clé racine réduite à un alias vers une
    # ancre-mapping-flow) est comblée — quand le nom d'ancre a été découvert via un alias
    # RACINE direct (round 30/55), sa position est désormais comparée à
    # `meilleur_trouve_ligne` comme les autres pré-passages. Reproduction exacte du reviewer,
    # vérifiée empiriquement contre PyYAML.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'cfg: &cfg {ignored_paths: [safe]}\nsecret: *cfg\nsecret:\n  ignored_paths:\n    - >-\n      **/*.md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_duplication_racine_bloc_puis_alias_ordre_inverse_reste_conforme(tmp_path):
    # Non-régression : ordre inversé (bloc PREMIER interdit, alias->flow SECOND borné et
    # gagnant) doit rester conforme.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'cfg: &cfg {ignored_paths: ["evidence/reviews/**/*.md"]}\n'
        'secret:\n  ignored_paths:\n    - >-\n      **/*.md\nsecret: *cfg\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_duplication_racine_flow_puis_alias_flow(tmp_path):
    # Non-régression : deux formes toutes deux résolues par des pré-passages distincts (round
    # 32 direct, round 57 via alias) — la DERNIÈRE doit gagner.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'cfg: &cfg {ignored_paths: [safe]}\nsecret: {ignored_paths: [a]}\nsecret: *cfg\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["safe"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_gitguardian_yaml_reel_du_depot_toujours_conforme_apres_round70():
    # Non-régression directe sur le fichier réel du dépôt, après le round 70 (clé racine
    # `secret` dupliquée, forme alias vers ancre-mapping-flow) : le verdict ne doit rien
    # changer.
    ok, motifs = check_gitguardian_scope.verifier(REPO / ".gitguardian.yaml")
    assert ok is True, f"exclusion(s) markdown globale(s) réintroduite(s) : {motifs}"


def test_parser_detecte_cle_racine_secret_dupliquee_fusion_puis_bloc(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 71, GPT-5.6-Terra-Pro) : la limite
    # documentée round 70 (« un nom découvert UNIQUEMENT via une FUSION conserve le
    # comportement return immédiat ») est comblée — `position_alias_racine` couvre désormais
    # aussi les noms fusionnés (round 31/56/59/60), pas seulement l'alias racine direct
    # (round 30/55). Reproduction exacte du reviewer, vérifiée empiriquement contre PyYAML.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'cfg: &cfg {ignored_paths: [safe]}\nsecret:\n  <<: *cfg\nsecret:\n  ignored_paths:\n    - >-\n      **/*.md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_duplication_racine_fusion_puis_bloc_ordre_inverse_reste_conforme(tmp_path):
    # Non-régression : ordre inversé (fusion PREMIER borné, bloc SECOND interdit) — le bloc
    # gagne toujours, cas déjà couvert avant round 71 (position propre du merge round 31/56).
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'cfg: &cfg {ignored_paths: ["evidence/reviews/**/*.md"]}\nsecret:\n  ignored_paths:\n    - >-\n      **/*.md\nsecret:\n  <<: *cfg\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_detecte_fusion_dans_ancre_flow_racine_seconde_occurrence(tmp_path):
    # Bug réel trouvé et corrigé PROACTIVEMENT dans le même round 71 (vérifié empiriquement
    # avant tout dispatch de revue) : `_noms_ancres_fusionnees_dans_ancres_flow` (round 59)
    # utilisait la ligne de DÉFINITION de l'ancre fusionnante comme position, alors que cette
    # ancre peut être définie AVANT la ligne racine qui la rend pertinente (déclaration
    # avancée, YAML valide) — la position doit être HÉRITÉE de l'ancre découvrante
    # (`position_alias_racine`), pas de sa propre ligne de définition.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'safe: &safe evidence/reviews/**/*.md\ninner: &inner {ignored_paths: [*safe]}\ncfg: &cfg {<<: *inner}\nsecret:\n  ignored_paths:\n    - >-\n      **/*.md\nsecret: *cfg\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["evidence/reviews/**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_duplication_racine_fusion_flow_directe_second(tmp_path):
    # Non-régression round 60 (fusion DIRECTE dans le mapping flow de la clé racine `secret`
    # elle-même, sans indirection d'ancre) combinée à une duplication root — la SECONDE
    # occurrence (fusion flow directe) doit gagner sur la première (bloc interdit).
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'cfg: &cfg {ignored_paths: [safe]}\nsecret:\n  ignored_paths:\n    - >-\n      **/*.md\nsecret: {<<: *cfg}\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["safe"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_gitguardian_yaml_reel_du_depot_toujours_conforme_apres_round71():
    # Non-régression directe sur le fichier réel du dépôt, après le round 71 (clé racine
    # `secret` dupliquée, positions fusion/ancre-flow propagées) : le verdict ne doit rien
    # changer.
    ok, motifs = check_gitguardian_scope.verifier(REPO / ".gitguardian.yaml")
    assert ok is True, f"exclusion(s) markdown globale(s) réintroduite(s) : {motifs}"


def test_parser_detecte_cle_racine_secret_dupliquee_alias_vers_ancre_bloc(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 72, GPT-5.6-Terra-Pro) : chaque
    # appelant de `_est_descendante_de_secret()` utilisait SA PROPRE position locale pour la
    # comparaison à `meilleur_trouve_ligne`, même quand l'ascendant était un nom d'ancre
    # ALIAS-ÉQUIVALENT (pas la clé racine `secret` littérale) — la ligne candidate peut alors
    # être définie n'importe où dans le fichier, potentiellement bien AVANT l'occurrence
    # racine tardive qui la rend pertinente. Reproduction exacte du reviewer, vérifiée
    # empiriquement contre PyYAML : la position locale de `ignored_paths` sous l'ancre `cfg`
    # (tôt dans le fichier) perdait à tort face à l'occurrence bloc intermédiaire, alors qu'un
    # alias racine direct vers `cfg` (tardif) doit gagner.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'cfg: &cfg\n  ignored_paths:\n    - >-\n      **/*.md\nsecret:\n  ignored_paths:\n    - safe\nsecret: *cfg\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_duplication_racine_alias_ancre_bloc_ordre_inverse_detecte_bloc_gagnant(tmp_path):
    # Non-régression : ordre inversé (alias vers ancre bloc PREMIER borné, bloc SECOND
    # interdit) — la position de l'alias racine (tôt) est INFÉRIEURE à celle de l'occurrence
    # bloc interdite (tard) : c'est donc le bloc interdit qui doit l'emporter (vérifié
    # empiriquement contre PyYAML), pas l'alias borné.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'cfg: &cfg\n  ignored_paths:\n    - >-\n      evidence/reviews/**/*.md\nsecret: *cfg\nsecret:\n  ignored_paths:\n    - >-\n      **/*.md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_duplication_racine_bloc_puis_alias_ancre_bloc_reste_conforme(tmp_path):
    # Non-régression : ordre inversé légitime — bloc PREMIER interdit, alias vers ancre bloc
    # SECOND (borné, gagnant) doit rester conforme.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'cfg: &cfg\n  ignored_paths:\n    - >-\n      evidence/reviews/**/*.md\nsecret:\n  ignored_paths:\n    - >-\n      **/*.md\nsecret: *cfg\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["evidence/reviews/**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_detecte_cle_racine_secret_explicite_alias_vers_ancre_bloc(tmp_path):
    # Non-régression/généralisation : même famille de bug, forme EXPLICITE de la clé racine
    # (`? secret\n: *cfg`) comme dernière occurrence — même correctif (position héritée),
    # vérifié empiriquement contre PyYAML.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'cfg: &cfg\n  ignored_paths:\n    - >-\n      **/*.md\nsecret:\n  ignored_paths:\n    - safe\n? secret\n: *cfg\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_detecte_fusion_vers_ancre_bloc_definie_avant_secret(tmp_path):
    # Bug latent comblé PROACTIVEMENT dans la même famille (vérifié empiriquement contre
    # PyYAML avant tout dispatch de revue) : `_noms_ancres_fusionnees_dans_secret()`
    # utilisait aussi systématiquement sa propre position locale (la ligne `<<:`) au lieu
    # d'hériter la position de l'ancre découvrante quand celle-ci est alias-équivalente.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'cfg: &cfg\n  ignored_paths:\n    - >-\n      **/*.md\nsecret:\n  ignored_paths:\n    - safe\nsecret:\n  <<: *cfg\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_gitguardian_yaml_reel_du_depot_toujours_conforme_apres_round72():
    # Non-régression directe sur le fichier réel du dépôt, après le round 72 (position
    # effective héritée pour toute ascendance alias-équivalente, pas seulement la position
    # locale de la ligne candidate) : le verdict ne doit rien changer.
    ok, motifs = check_gitguardian_scope.verifier(REPO / ".gitguardian.yaml")
    assert ok is True, f"exclusion(s) markdown globale(s) réintroduite(s) : {motifs}"


def test_construire_table_ancres_deux_ancres_meme_ligne_flow(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 74, GPT-5.6-Terra-Pro) :
    # `_construire_table_ancres()` ne traitait que le PREMIER candidat `&nom` valide trouvé
    # sur chaque ligne (`break` dès la première itération) — une ligne flow portant PLUSIEURS
    # ancres (`{ safe: &safe x, paths: &paths [*md] }`) empêchait donc l'enregistrement de
    # toute ancre ULTÉRIEURE sur cette même ligne. Reproduction exacte du reviewer, vérifiée
    # empiriquement contre PyYAML.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'md: &md >-\n  **/*.md\nholder: { safe: &safe x, paths: &paths [*md] }\nsecret:\n  ignored_paths: *paths\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_pre_passage_round57_trouve_ancre_precedee_par_autre_ancre_meme_ligne(tmp_path):
    # Même famille de bug, dans `_trouver_definition_ancre_valide()` (round 59) — ses deux
    # appelants (pré-passage round 57, `_noms_ancres_fusionnees_dans_ancres_flow` round 59)
    # cherchent un nom d'ancre PRÉCIS ; si ce nom n'était pas le premier candidat valide de sa
    # ligne, il n'était jamais examiné. Ici, `cfg` (aliasée depuis la clé racine) est PRÉCÉDÉE
    # par une ancre `bruit` sans rapport sur la même ligne flow.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'md: &md >-\n  **/*.md\nholder: { bruit: &bruit 1, cfg: &cfg {ignored_paths: [*md]} }\nsecret: *cfg\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_construire_table_ancres_trois_ancres_meme_ligne_troisieme_est_la_cible(tmp_path):
    # Non-régression/généralisation : trois ancres sur une même ligne flow, la TROISIÈME
    # (dernière) est celle référencée — vérifie que la boucle interne ne s'arrête pas non
    # plus après la deuxième.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'md: &md >-\n  **/*.md\nholder: { a: &a 1, b: &b 2, paths: &paths [*md] }\nsecret:\n  ignored_paths: *paths\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_construire_table_ancres_deux_ancres_meme_ligne_non_liees_reste_conforme(tmp_path):
    # Non-régression : deux ancres sur la même ligne flow, mais NI l'une ni l'autre n'est
    # référencée par `ignored_paths` — doit rester conforme (les deux sont désormais
    # correctement enregistrées dans la table d'ancres, mais aucune n'est pertinente ici).
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'holder: { a: &a 1, b: &b 2 }\nsecret:\n  ignored_paths:\n    - safe\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_construire_table_ancres_liste_flow_multiligne_puis_ancre_sur_ligne_de_fermeture(tmp_path):
    # Bug latent comblé PROACTIVEMENT (vérifié empiriquement contre PyYAML avant tout dispatch
    # de revue, en testant le correctif ci-dessus) : quand la valeur FLOW de la première ancre
    # s'étend sur PLUSIEURS lignes physiques, la ligne de FERMETURE (`]`) pouvait porter une
    # AUTRE ancre juste après (`], paths: &paths [...] }`) — le saut de ligne calculé
    # atterrissait auparavant UNE ligne trop loin (`+= sauts_ligne + 1`), sautant entièrement
    # la ligne de fermeture sans jamais la réexaminer.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'md: &md >-\n  **/*.md\nholder: { first: &first [\n  1,\n  2\n], paths: &paths [*md] }\nsecret:\n  ignored_paths: *paths\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_gitguardian_yaml_reel_du_depot_toujours_conforme_apres_round74():
    # Non-régression directe sur le fichier réel du dépôt, après le round 74 (ancres multiples
    # sur une même ligne flow, table d'ancres + pré-passage round 57 comblés) : le verdict ne
    # doit rien changer.
    ok, motifs = check_gitguardian_scope.verifier(REPO / ".gitguardian.yaml")
    assert ok is True, f"exclusion(s) markdown globale(s) réintroduite(s) : {motifs}"


def test_construire_table_ancres_diese_dans_scalaire_nu_ne_masque_pas_ancre_suivante(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 75, GPT-5.6-Terra-Pro) : la détection de
    # commentaire de `_construire_table_ancres()` traitait tout `#` non guillemeté comme un
    # début de commentaire, sans vérifier le caractère PRÉCÉDENT — contrairement à la règle
    # YAML déjà correctement appliquée par `_spans_commentaires()` (round 38) : `#` ne démarre
    # un commentaire que séparé du contenu précédent. `foo#bar` est un scalaire nu YAML valide
    # (le `#` en fait partie), pas un commentaire. Reproduction exacte du reviewer, vérifiée
    # empiriquement contre PyYAML.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'base: &base >-\n  **/*.md\nholder: {note: foo#bar, paths: &paths [*base]}\nsecret:\n  ignored_paths: *paths\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_pre_passage_round57_diese_dans_scalaire_nu_ne_masque_pas_ancre_suivante(tmp_path):
    # Même famille de bug, dans `_trouver_definition_ancre_valide()` (round 59, factorisée du
    # même filtrage) — même correctif de bord appliqué.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'base: &base >-\n  **/*.md\nholder: {note: foo#bar, cfg: &cfg {ignored_paths: [*base]}}\nsecret: *cfg\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_construire_table_ancres_vrai_commentaire_en_fin_de_ligne_masque_toujours_fausse_ancre(tmp_path):
    # Non-régression : un VRAI commentaire (`#` précédé d'un espace, en fin de ligne) doit
    # continuer à masquer une fausse ancre qu'il contiendrait — la valeur réelle de l'ancre
    # légitime PRÉCÉDANT ce commentaire, sur la même ligne, reste résolue normalement.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'holder: {a: &a [safe]} # &fake [danger]\nsecret:\n  ignored_paths: *a\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_gitguardian_yaml_reel_du_depot_toujours_conforme_apres_round75():
    # Non-régression directe sur le fichier réel du dépôt, après le round 75 (détection de
    # commentaire alignée sur la règle YAML de `_spans_commentaires`) : le verdict ne doit
    # rien changer.
    ok, motifs = check_gitguardian_scope.verifier(REPO / ".gitguardian.yaml")
    assert ok is True, f"exclusion(s) markdown globale(s) réintroduite(s) : {motifs}"


def test_parser_boucle_point_fixe_met_a_jour_position_dun_nom_deja_connu(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 76, GPT-5.6-Terra-Pro) : la boucle à
    # point fixe (round 59/71) comparait l'ENSEMBLE DE NOMS pour décider de s'arrêter
    # (`nouveau == noms_alias_racine: break`) AVANT de mettre à jour `position_alias_racine` —
    # un nom déjà connu (donc n'affectant pas l'ensemble), redécouvert à une position PLUS
    # TARDIVE par une itération ultérieure, ne voyait alors JAMAIS sa position mise à jour.
    # Reproduction exacte du reviewer, vérifiée empiriquement contre PyYAML : `cfg` est d'abord
    # connu via un alias racine direct (position ligne 3), puis redécouvert plus tard via une
    # fusion `<<: *cfg` (position ligne 7, bien plus tardive) — cette position mise à jour
    # devait faire gagner la fusion sur l'occurrence bloc intermédiaire.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'cfg: &cfg\n  ignored_paths:\n    - >-\n      **/*.md\nsecret: *cfg\nsecret:\n  ignored_paths: [safe]\nsecret:\n  <<: *cfg\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_boucle_point_fixe_trois_occurrences_ordre_naturel(tmp_path):
    # Non-régression/généralisation : trois occurrences de la clé racine dans l'ordre naturel
    # (ancre bloc interdite en fond, occurrence bloc interdite intermédiaire, alias direct
    # borné, fusion FINALE redécouvrant `cfg` à une position tardive) — la fusion finale doit
    # gagner.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'cfg: &cfg\n  ignored_paths:\n    - >-\n      **/*.md\nsecret:\n  ignored_paths: [safe]\nsecret: *cfg\nsecret:\n  <<: *cfg\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_gitguardian_yaml_reel_du_depot_toujours_conforme_apres_round76():
    # Non-régression directe sur le fichier réel du dépôt, après le round 76 (position
    # toujours mise à jour dans la boucle à point fixe, même pour un nom déjà connu) : le
    # verdict ne doit rien changer.
    ok, motifs = check_gitguardian_scope.verifier(REPO / ".gitguardian.yaml")
    assert ok is True, f"exclusion(s) markdown globale(s) réintroduite(s) : {motifs}"


# ---------------------------------------------------------------------------
# scalaires bloc YAML (`- >`/`- |`) — round 8
# ---------------------------------------------------------------------------

def test_parser_consomme_un_scalaire_replie_dont_le_contenu_est_sur_la_ligne_suivante(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 8, GPT-5.6-Terra-Pro) : `- >-` est capté
    # par `_LIGNE_ITEM` comme une valeur non guillemetée littérale `'>-'` — le VRAI contenu, sur
    # la ligne suivante plus indentée, n'était jamais examiné. `"**/*.md"` sous forme de scalaire
    # bloc replié (`>-`) est sémantiquement `**/*.md` pour tout parseur YAML conforme.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  ignored_paths:\n    - >-\n      **/*.md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_consomme_un_scalaire_litteral_dont_le_contenu_est_sur_la_ligne_suivante(tmp_path):
    # Même bug, indicateur `|` (littéral, pas replié) au lieu de `>` (replié).
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  ignored_paths:\n    - |\n      *.md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["*.md"]


def test_parser_scalaire_bloc_ne_confond_pas_un_glob_borne_avec_le_litteral_interdit(tmp_path):
    # Non-régression : un scalaire bloc dont le contenu réel est un glob BORNÉ légitime
    # (evidence/reviews/**/*.md) ne doit pas être classé comme exclusion globale.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  ignored_paths:\n    - >-\n      evidence/reviews/**/*.md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


def test_parser_scalaire_bloc_ordre_indicateur_profondeur_puis_chomping(tmp_path):
    # Bug réel trouvé par revue scellée (RC1-015 round 9, GPT-5.6-Terra-Pro) : la grammaire YAML
    # (spec 8.1.1.1) autorise l'indicateur de profondeur ET de chomping dans les DEUX ordres
    # (`>-2` chomping-puis-profondeur, `>2-` profondeur-puis-chomping) — seul le premier ordre
    # était reconnu par `_LIGNE_ITEM_BLOC`. Repro confirmée avant correctif : `>2-` non reconnu
    # comme en-tête de scalaire bloc, `parser_ignored_paths` capturait `'>2-'` comme valeur
    # littérale au lieu de consommer la ligne de contenu suivante.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  ignored_paths:\n    - >2-\n      **/*.md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_parser_scalaire_bloc_suivi_d_un_autre_item_continue_correctement(tmp_path):
    # Après avoir consommé le contenu d'un scalaire bloc, le parseur doit reprendre l'analyse
    # normale des items suivants — pas s'arrêter prématurément.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  ignored_paths:\n    - >-\n      tests/fixtures/**\n    - "LICENSE"\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["tests/fixtures/**", "LICENSE"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is True
    assert motifs == []


# ---------------------------------------------------------------------------
# fichier réel du dépôt — cliquet anti-régression
# ---------------------------------------------------------------------------

def test_gitguardian_yaml_reel_du_depot_sans_exclusion_globale():
    ok, motifs = check_gitguardian_scope.verifier(REPO / ".gitguardian.yaml")
    assert ok is True, f"exclusion(s) markdown globale(s) réintroduite(s) : {motifs}"


def test_gitguardian_yaml_reel_conserve_les_exceptions_non_markdown():
    chemins = check_gitguardian_scope.parser_ignored_paths(REPO / ".gitguardian.yaml")
    for attendu in ("tests/fixtures/**", "src/forgeai/data/catalogue.json", "LICENSE", ".gitignore"):
        assert attendu in chemins, f"exception légitime disparue : {attendu}"


# ---------------------------------------------------------------------------
# corpus réel — aucune valeur factice detectable-AWS ne traîne hors chemins bornés
# ---------------------------------------------------------------------------

def test_aucun_motif_cle_aws_plausible_dans_le_markdown_hors_evidence_reviews():
    # Reproduit la preuve empirique (voir stories/RC1-015.md) : un identifiant de clé d'accès AWS
    # de forme plausible (AKIA + 16 car. alphanumériques majuscules), placé dans un .md HORS de
    # tout chemin borné, DOIT être absent du dépôt réel (vérifié aussi positivement : ce motif
    # déclenche bien ggshield quand présent — voir story). Ce test protège contre une régression
    # qui réintroduirait une telle valeur sans qu'aucun gate ne la voie.
    import re

    motif = re.compile(r"AKIA[0-9A-Z]{16}")
    racine_reviews = REPO / "evidence" / "reviews"
    trouvailles = []
    for chemin in REPO.rglob("*.md"):
        if racine_reviews in chemin.parents or chemin == racine_reviews:
            continue
        if ".git" in chemin.parts:
            continue
        try:
            texte = chemin.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if motif.search(texte):
            trouvailles.append(str(chemin.relative_to(REPO)))
    assert trouvailles == [], f"motif de clé AWS plausible trouvé : {trouvailles}"


# ---------------------------------------------------------------------------
# main() — CLI
# ---------------------------------------------------------------------------

def test_main_retourne_0_si_conforme(tmp_path, monkeypatch):
    import sys

    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text('secret:\n  ignored_paths:\n    - "LICENSE"\n', encoding="utf-8")  # proof:allow — clé de schéma YAML, pas un secret réel
    monkeypatch.setattr(sys, "argv", ["check_gitguardian_scope.py", "--fichier", str(fichier)])
    assert check_gitguardian_scope.main() == 0


def test_main_retourne_1_si_exclusion_globale(tmp_path, monkeypatch):
    import sys

    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text('secret:\n  ignored_paths:\n    - "**/*.md"\n', encoding="utf-8")  # proof:allow — clé de schéma YAML, pas un secret réel
    monkeypatch.setattr(sys, "argv", ["check_gitguardian_scope.py", "--fichier", str(fichier)])
    assert check_gitguardian_scope.main() == 1


def test_construire_table_ancres_resout_ancre_guillemetee_suivie_de_fermeture_flow(tmp_path):
    # RC1-015 round 94, revue scellée GPT-5.6-Terra-Pro (MAJEURE, bug réel) : une ancre de
    # scalaire double-guillemets portée par une clé d'un mapping flow, suivie de la fermeture
    # `}` de ce mapping sur la MÊME ligne, n'était pas résolue — le repli stockait la valeur
    # brute incluant `}`, qui ne satisfait plus est_exclusion_markdown_globale(). FAUX NÉGATIF
    # réel : une exclusion globale active passait inaperçue. Vérifié empiriquement (PyYAML)
    # avant correctif que secret.ignored_paths résout bien vers ['**/*.md'] dans ce cas.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'holder: { paths: &paths "**/*.md" }\nsecret:\n  ignored_paths: [*paths]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_construire_table_ancres_resout_ancre_simple_guillemets_suivie_de_fermeture_flow(tmp_path):
    # Même bug round 94, variante guillemets SIMPLES (chemin de code distinct : `_CHAINE_SIMPLE_
    # GUILLEMETS`, même condition de fermeture corrigée).
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        "holder: { paths: &paths '**/*.md' }\nsecret:\n  ignored_paths: [*paths]\n",  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_construire_table_ancres_resout_ancre_guillemetee_quelle_que_soit_la_suite(tmp_path):
    # RC1-015 round 95 (revue scellée GPT-5.6-Terra-Pro, MAJEURE bloquante — même famille de bug
    # que le round 94, reproduction étendue à une imbrication à deux niveaux flow avec clé sœur,
    # exactement la « limite résiduelle CONNUE » documentée puis retirée au round 95) : le
    # filtrage de la suite après la valeur guillemetée est retiré ENTIÈREMENT — `.match()`
    # ancrant déjà en position 0 de `reste`, la valeur capturée est sans ambiguïté correcte quel
    # que soit ce qui suit. Ce test fige ce nouveau comportement (round 94 testait l'ANCIENNE
    # restriction, aujourd'hui retirée) : même une suite non-flow (`extra`) résout désormais la
    # valeur — cette suite est hors du périmètre de ce cliquet (dont la responsabilité s'arrête
    # à ne jamais laisser passer une exclusion réelle, pas à valider la syntaxe YAML globale).
    ancres = check_gitguardian_scope._construire_table_ancres(
        'holder: { paths: &paths "safe" extra }\n',
        ['holder: { paths: &paths "safe" extra }'],
    )
    assert ancres.get("paths") == "safe"


def test_construire_table_ancres_resout_ancre_guillemetee_imbriquee_deux_niveaux_avec_cle_soeur(tmp_path):
    # RC1-015 round 95, reproduction EXACTE du reviewer (revue scellée GPT-5.6-Terra-Pro,
    # MAJEURE bloquante) : ancre de scalaire guillemeté nichée à DEUX niveaux flow, suivie d'une
    # clé SŒUR de l'enveloppe extérieure sur la même ligne physique — vérifié empiriquement
    # (PyYAML) que secret.ignored_paths résout bien vers ['**/*.md'] via l'alias avant correctif.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'outer: { holder: { paths: &paths "**/*.md" }, other: 1 }\nsecret:\n  ignored_paths: [*paths]\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]


def test_lignes_dans_bloc_secret_racine_ne_retourne_jamais_none_pour_cas_simple():
    # RC1-015 round 94, revue scellée GPT-5.6-Terra-Pro (CRITIQUE, finding RÉFUTÉ avec preuve) :
    # claim que _lignes_dans_bloc_secret_racine() ne retourne jamais (chute sur None implicite).
    # Réfuté empiriquement — la fonction retourne bien une list[bool], jamais None, pour un cas
    # bien formé. Le `return resultat` final est bien présent (voir aussi le diff soumis à la
    # revue round 94, ligne confirmée présente par grep direct AVANT ce round).
    resultat = check_gitguardian_scope._lignes_dans_bloc_secret_racine(
        "secret:\n  ignored_paths:\n    - safe\n", {}  # proof:allow — clé de schéma YAML, pas un secret réel
    )
    assert resultat is not None
    assert isinstance(resultat, list)
    assert all(isinstance(v, bool) for v in resultat)


def test_parser_scalaire_bloc_item_avec_ancre_directe_est_reconnu(tmp_path):
    # RC1-015 round 111, revue scellée GPT-5.6-Terra-Pro (CRITIQUE, bug réel) : miroir manqué de
    # `_LIGNE_CLE_BLOC` (round 12, ancre optionnelle avant tag optionnel avant indicateur) — un
    # item de LISTE portant une ancre directement sur son scalaire bloc (`- &a >-\n  **/*.md`)
    # n'était reconnu ni par `_LIGNE_ITEM_BLOC` (tag seul autorisé, pas d'ancre) ni par
    # `_LIGNE_ITEM` (le jeton nu `&a` laisse `>-` non consommé avant la fin de ligne attendue).
    # Repro confirmée AVANT correctif : PyYAML résout `secret.ignored_paths` en `['**/*.md']`
    # (forme YAML valide), mais `verifier()` concluait à tort à la conformité (`ok=True`), la
    # ligne de contenu `**/*.md` n'étant jamais consommée comme scalaire bloc.
    fichier = tmp_path / ".gitguardian.yaml"
    fichier.write_text(
        'secret:\n  ignored_paths:\n    - &a >-\n      **/*.md\n',  # proof:allow — clé de schéma YAML, pas un secret réel
        encoding="utf-8",
    )
    assert check_gitguardian_scope.parser_ignored_paths(fichier) == ["**/*.md"]
    ok, motifs = check_gitguardian_scope.verifier(fichier)
    assert ok is False
    assert motifs == ["**/*.md"]
