"""Tests du module ``forgeai.ide.guard_fs`` (B-24c/d).

Chaque test fonctionnel exécute RÉELLEMENT le script de garde généré, via
``subprocess.run([sys.executable, script], input=json.dumps(charge),
text=True, capture_output=True)``, et asserte le code de sortie ET l'effet
(message de refus sur stderr, entrée de registre, chaîne validée par le
verify officiel). Aucun mock.

Précautions d'herméticité :

- ``registre_path`` et ``allow_path`` sont TOUJOURS redirigés sous tmp_path à
  la génération — les tests n'écrivent jamais dans le ``~/.forgeai`` réel ;
- pour le script produit par ``install_guard_fs`` (chemins embarqués par
  défaut), la journalisation est redirigée via la variable d'environnement
  ``FORGEAI_REGISTRE`` lue par la garde ;
- pytest place tmp_path sous ``tempfile.gettempdir()`` : or la garde autorise
  par défaut tout chemin sous le tempdir. Les tests qui exigent un REFUS sur
  une cible située sous tmp_path isolent donc le ``TMPDIR`` du subprocess
  dans un répertoire dédié (fixture ``env_tmpdir``).
"""

import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from forgeai.ide import IDEError
from forgeai.ide.bootstrap import HookSpec
from forgeai.ide.guard_fs import generate_guard_fs, install_guard_fs

REPO_RACINE = Path(__file__).resolve().parents[1]
REGISTRE_PY = REPO_RACINE / "scripts" / "registre.py"


def run(script, charge, env=None):
    """Exécute le script de garde sur une charge de hook -> (exit, stderr).

    ``charge`` est un dict (sérialisé en JSON) ou une chaîne brute — les
    chaînes servent aux cas fail-closed (stdin vide, JSON invalide). ``env``
    est fusionné PAR-DESSUS os.environ : le subprocess hérite du reste.
    """
    entree = charge if isinstance(charge, str) else json.dumps(charge)
    environ = dict(os.environ)
    if env:
        environ.update(env)
    proc = subprocess.run(
        [sys.executable, str(script)],
        input=entree,
        text=True,
        capture_output=True,
        env=environ,
    )
    return proc.returncode, proc.stderr


def charge(outil, tool_input=None, cwd=None):
    """Construit une charge de hook PreToolUse minimale mais valide."""
    return {
        "tool_name": outil,
        "tool_input": {} if tool_input is None else tool_input,
        "cwd": str(cwd),
    }


def ecrire_garde(tmp_path, racine, *, registre=None, allow=None, nom="forgeai_guard_fs.py"):
    """Génère la garde pour ``racine`` et en écrit le source sous tmp_path.

    registre/allow basculent par défaut sous tmp_path : aucun test ne touche
    le ``~/.forgeai`` réel de la machine.
    """
    src = generate_guard_fs(
        racine,
        registre_path=registre if registre is not None else tmp_path / "registre.jsonl",
        allow_path=allow if allow is not None else tmp_path / "guard-fs.allow",
    )
    script = tmp_path / nom
    script.write_text(src, encoding="utf-8")
    return script


@pytest.fixture
def racine(tmp_path):
    root = tmp_path / "racine"
    root.mkdir()
    return root


@pytest.fixture
def env_tmpdir(tmp_path):
    """TMPDIR isolé pour le subprocess de garde.

    tmp_path vit sous tempfile.gettempdir() ; sans cette isolation,
    l'exception tempdir de la garde AUTORISERAIT des cibles de test placées
    sous tmp_path alors qu'elles doivent être REFUSÉES (tests 6 et 10).
    """
    dossier = tmp_path / "guard-tmpdir"
    dossier.mkdir()
    return {"TMPDIR": str(dossier)}


# 1. Racine inexistante -> IDEError.
def test_generate_racine_inexistante_leve_ideerror(tmp_path):
    with pytest.raises(IDEError):
        generate_guard_fs(tmp_path / "n-existe-pas")


# 2. Le source rendu compile et ne contient plus aucun marqueur.
def test_source_genere_compile_et_sans_marqueurs(tmp_path):
    root = tmp_path / "racine"
    root.mkdir()
    src = generate_guard_fs(root)
    compile(src, "<guard_fs>", "exec")  # lève SyntaxError si invalide
    for marqueur in ("__FORGEAI_ROOT__", "__FORGEAI_REGISTRE__", "__FORGEAI_ALLOW__"):
        assert marqueur not in src, f"marqueur non substitué : {marqueur}"


# 3. install_guard_fs écrit le script et rend le HookSpec attendu.
def test_install_ecrit_script_et_rend_hookspec(tmp_path):
    dest = tmp_path / "projet"
    dest.mkdir()
    script_path, hook = install_guard_fs(dest)
    attendu = (dest / ".claude" / "hooks" / "forgeai_guard_fs.py").resolve()
    assert script_path == attendu
    assert script_path.is_file()
    assert script_path.stat().st_size > 0
    assert stat.S_IMODE(script_path.stat().st_mode) == 0o755
    assert isinstance(hook, HookSpec)
    assert hook.event == "PreToolUse"
    assert hook.matcher == "*"
    assert f'"{sys.executable}"' in hook.command
    assert f'"{script_path}"' in hook.command


# 4. Lecture DANS la racine -> exit 0.
def test_lecture_dans_racine_autorisee(tmp_path, racine):
    cible = racine / "notes.txt"
    cible.write_text("bonjour", encoding="utf-8")
    script = ecrire_garde(tmp_path, racine)
    code, err = run(script, charge("Read", {"file_path": str(cible)}, cwd=racine))
    assert code == 0, err


# 5. Lecture HORS racine -> exit 2.
def test_lecture_hors_racine_refusee(tmp_path, racine):
    script = ecrire_garde(tmp_path, racine)
    code, err = run(script, charge("Read", {"file_path": "/etc/passwd"}, cwd=racine))
    assert code == 2
    assert "REFUS" in err


# 6. Écriture qui SORT via .. -> exit 2.
def test_ecriture_sortant_par_point_point_refusee(tmp_path, racine, env_tmpdir):
    script = ecrire_garde(tmp_path, racine)
    cible = f"{racine}/../evil.txt"
    code, err = run(
        script,
        charge("Write", {"file_path": cible, "content": "x"}, cwd=racine),
        env=env_tmpdir,
    )
    assert code == 2
    assert "REFUS" in err


# 7. Bash avec un chemin littéral hors racine -> exit 2.
def test_bash_chemin_litteral_hors_racine_refuse(tmp_path, racine):
    script = ecrire_garde(tmp_path, racine)
    code, err = run(script, charge("Bash", {"command": "cat /etc/shadow"}, cwd=racine))
    assert code == 2
    assert "REFUS" in err


# 8. Bash sans aucun chemin littéral -> exit 0.
def test_bash_sans_chemin_litteral_autorise(tmp_path, racine):
    script = ecrire_garde(tmp_path, racine)
    code, err = run(script, charge("Bash", {"command": "echo ok"}, cwd=racine))
    assert code == 0, err


# 9. Symlink SORTANT : <racine>/lien -> /etc, lecture de <racine>/lien/passwd -> exit 2.
def test_symlink_sortant_refuse(tmp_path, racine):
    os.symlink("/etc", racine / "lien")
    script = ecrire_garde(tmp_path, racine)
    cible = racine / "lien" / "passwd"
    code, err = run(script, charge("Read", {"file_path": str(cible)}, cwd=racine))
    assert code == 2
    assert "REFUS" in err


# 10. Répertoire frère à préfixe commun : racine <base>/repo, cible <base>/repo-evil/x -> exit 2.
def test_repertoire_frere_a_prefixe_commun_refuse(tmp_path, env_tmpdir):
    base = tmp_path / "base"
    root = base / "repo"
    root.mkdir(parents=True)
    cible = base / "repo-evil" / "x.txt"
    script = ecrire_garde(tmp_path, root)
    code, err = run(
        script,
        charge("Read", {"file_path": str(cible)}, cwd=root),
        env=env_tmpdir,
    )
    assert code == 2
    assert "REFUS" in err


# 11. Auto-protection : settings.json, le script lui-même, le répertoire des hooks.
def test_auto_protection_outils_ecriture_refuses(tmp_path):
    dest = tmp_path / "projet"
    dest.mkdir()
    script_path, _hook = install_guard_fs(dest)
    # Le script installé embarque le registre par défaut (~/.forgeai/...) :
    # redirection de la journalisation vers tmp_path via la variable lue par la garde.
    env = {"FORGEAI_REGISTRE": str(tmp_path / "registre.jsonl")}
    cas = [
        ("Write", {"file_path": str(dest / ".claude" / "settings.json"), "content": "{}"}),
        ("Edit", {"file_path": str(script_path), "old_string": "a", "new_string": "b"}),
        ("Write", {"file_path": str(dest / ".claude" / "hooks" / "autre.py"), "content": "x"}),
    ]
    for outil, tool_input in cas:
        code, err = run(script_path, charge(outil, tool_input, cwd=dest), env=env)
        assert code == 2, f"{outil} sur {tool_input['file_path']} doit être refusé"
        assert "auto-protection" in err


# 12. stdin vide -> exit 2 (fail-closed) ; stdin JSON invalide -> exit 2.
def test_stdin_vide_et_json_invalide_refuses(tmp_path, racine):
    script = ecrire_garde(tmp_path, racine)
    code, err = run(script, "")
    assert code == 2
    assert "REFUS" in err
    code, err = run(script, "{ceci n'est pas du json")
    assert code == 2
    assert "REFUS" in err


# 13. tool_input sans aucun chemin -> exit 0.
def test_tool_input_sans_chemin_autorise(tmp_path, racine):
    script = ecrire_garde(tmp_path, racine)
    code, err = run(script, charge("Read", {}, cwd=racine))
    assert code == 0, err


# 14. Outil inconnu sans chemin candidat -> exit 0.
def test_outil_inconnu_sans_chemin_autorise(tmp_path, racine):
    script = ecrire_garde(tmp_path, racine)
    code, err = run(
        script,
        charge("WebFetch", {"url": "https://example.com"}, cwd=racine),
    )
    assert code == 0, err


# 15. JOURNALISATION : deux refus successifs, entrées "guard_fs_denied",
# prev_hash chaîné, et chaîne acceptée par le verify officiel du produit.
def test_journalisation_registre_et_verify_officiel(tmp_path, racine):
    registre = tmp_path / "Registres" / "mission.jsonl"
    script = ecrire_garde(tmp_path, racine, registre=registre)
    cibles = ["/etc/passwd", "/etc/shadow"]
    for cible in cibles:
        code, _err = run(script, charge("Read", {"file_path": cible}, cwd=racine))
        assert code == 2
    lignes = registre.read_text(encoding="utf-8").splitlines()
    assert len(lignes) == 2, f"2 refus journalisés attendus : {lignes}"
    e1, e2 = (json.loads(ligne) for ligne in lignes)
    racine_resolue = os.path.realpath(str(racine))
    for entree, cible in ((e1, cibles[0]), (e2, cibles[1])):
        assert entree["type"] == "guard_fs_denied"
        assert entree["actor"] == "guard-fs"
        assert entree["payload"]["tool"] == "Read"
        assert entree["payload"]["chemin_resolu"] == os.path.realpath(cible)
        assert entree["payload"]["racine"] == racine_resolue
    assert e1["seq"] == 1
    assert e2["seq"] == 2
    assert e1["prev_hash"] == "0" * 64
    assert e2["prev_hash"] == e1["hash"], "prev_hash de l'entrée 2 doit chaîner le hash de l'entrée 1"
    # Vérification par le verify OFFICIEL du produit.
    assert REGISTRE_PY.is_file(), f"verify officiel introuvable : {REGISTRE_PY}"
    proc = subprocess.run(
        [sys.executable, str(REGISTRE_PY), "verify", str(registre)],
        text=True,
        capture_output=True,
        cwd=str(REPO_RACINE),
    )
    assert proc.returncode == 0, proc.stderr
    assert "chaîne intègre" in (proc.stdout + proc.stderr)


# 16. Journalisation impossible : le refus tient (exit 2) quand même.
def test_journalisation_impossible_ne_leve_pas_le_refus(tmp_path, racine):
    bloquant = tmp_path / "bloquant"
    bloquant.write_text("un fichier là où un dossier est attendu", encoding="utf-8")
    registre_bloque = bloquant / "sous" / "registre.jsonl"
    script = ecrire_garde(tmp_path, racine, registre=registre_bloque)
    code, err = run(script, charge("Read", {"file_path": "/etc/passwd"}, cwd=racine))
    assert code == 2
    assert "journalisation impossible" in err


# 17. Exceptions : chemin hors racine mais listé dans allow_path -> exit 0 ;
# tempfile.gettempdir() autorisé par défaut -> exit 0.
def test_allow_list_et_tempdir_autorises(tmp_path, racine):
    # a) /etc listé explicitement dans le fichier d'exceptions.
    allow = tmp_path / "exceptions.allow"
    allow.write_text("/etc\n", encoding="utf-8")
    script_allow = ecrire_garde(tmp_path, racine, allow=allow, nom="garde_allow.py")
    code, err = run(script_allow, charge("Read", {"file_path": "/etc/passwd"}, cwd=racine))
    assert code == 0, err
    # b) Aucun fichier d'exceptions : le tempdir reste autorisé par défaut.
    script_defaut = ecrire_garde(
        tmp_path, racine, allow=tmp_path / "allow-absente.txt", nom="garde_defaut.py"
    )
    hors_racine = Path(tempfile.mkdtemp()) / "secret.txt"
    hors_racine.write_text("x", encoding="utf-8")
    code, err = run(
        script_defaut,
        charge("Read", {"file_path": str(hors_racine)}, cwd=racine),
    )
    assert code == 0, err



# 18. Auto-protection du SCRIPT, ISOLÉE de la protection du dossier hooks et de la
#     règle de containment. Le script est généré À L'INTÉRIEUR de la racine mais
#     HORS de <root>/.claude/hooks/ : un Edit du script n'est alors couvert QUE par
#     `cible == SCRIPT_PATH` (il est dans la racine, donc containment l'autoriserait ;
#     il n'est pas sous hooks/). Sans cette règle, la garde se laisse réécrire —
#     c'est le cas que la mutation-test doit tuer.
def test_auto_protection_du_script_dans_racine_hors_hooks(tmp_path, racine, env_tmpdir):
    src = generate_guard_fs(
        racine,
        registre_path=tmp_path / "registre.jsonl",
        allow_path=tmp_path / "guard-fs.allow",
    )
    # script placé DANS la racine, pas sous .claude/hooks/
    script = racine / "garde_dans_racine.py"
    script.write_text(src, encoding="utf-8")
    code, err = run(script, charge("Edit", {"file_path": str(script)}, cwd=racine), env=env_tmpdir)
    assert code == 2, f"le script doit se protéger même hors du dossier hooks (stderr={err!r})"


# ─────────────── Tour 2 : non-régression de sécurité (revue scellée) ───────────────
# La revue a REJETÉ (2/3) la première version : des chemins littéraux TRIVIAUX
# passaient à travers le confinement Bash (tokens quotés, chemins relatifs sans
# préfixe, chemins Windows), et le dossier .claude parent n'était pas protégé.
# Chaque test ci-dessous LANCE le script généré et prouve la fermeture d'un
# contournement précis. env_tmpdir est passé partout : sans lui, l'exception
# tempdir autoriserait des cibles sous tmp_path.

def test_bash_chemin_absolu_double_quote_refuse(racine, env_tmpdir, tmp_path):
    script = ecrire_garde(tmp_path, racine)
    code, err = run(script, charge("Bash", {"command": 'cat "/etc/passwd"'}, cwd=racine), env=env_tmpdir)
    assert code == 2, f"chemin quoté doit être refusé (stderr={err!r})"


def test_bash_chemin_absolu_simple_quote_refuse(racine, env_tmpdir, tmp_path):
    script = ecrire_garde(tmp_path, racine)
    code, err = run(script, charge("Bash", {"command": "cat '/etc/passwd'"}, cwd=racine), env=env_tmpdir)
    assert code == 2, f"chemin quoté simple doit être refusé (stderr={err!r})"


def test_bash_relatif_sans_prefixe_dossier_hooks_refuse(racine, env_tmpdir, tmp_path):
    script = ecrire_garde(tmp_path, racine)
    code, err = run(script, charge("Bash", {"command": "rm -rf .claude/hooks"}, cwd=racine), env=env_tmpdir)
    assert code == 2, f"rm -rf .claude/hooks (relatif) doit être refusé (stderr={err!r})"


def test_bash_dossier_claude_lui_meme_refuse(racine, env_tmpdir, tmp_path):
    script = ecrire_garde(tmp_path, racine)
    code, err = run(script, charge("Bash", {"command": "rm -rf .claude"}, cwd=racine), env=env_tmpdir)
    assert code == 2, f"rm -rf .claude (le dossier entier) doit être refusé (stderr={err!r})"


def test_bash_traversal_relatif_refuse(racine, env_tmpdir, tmp_path):
    script = ecrire_garde(tmp_path, racine)
    code, err = run(script, charge("Bash", {"command": "cat foo/../../../etc/passwd"}, cwd=racine), env=env_tmpdir)
    assert code == 2, f"traversal relatif doit être refusé (stderr={err!r})"


# O2 (chemins Windows) se prouve à deux niveaux. Sur POSIX, `C:\\...` n'est PAS
# absolu : realpath le traite comme un nom relatif dans le cwd, donc DANS la
# racine — refuser serait faux. Le correctif consiste à ne plus IGNORER le token
# (il est capté comme candidat) ; ce fait est vérifiable partout. Le REFUS effectif
# n'a lieu que là où `C:\\` est réellement absolu, c.-à-d. sur Windows.
def test_source_capte_les_chemins_windows_comme_candidats(racine):
    # Preuve portable : le code de détection d'un lecteur Windows est present dans
    # le script généré — le token n'est donc plus ignoré (traitement de O2).
    src = generate_guard_fs(racine)
    assert "[A-Za-z]:" in src, "la détection de chemin Windows doit être présente dans la garde"


@pytest.mark.skipif(
    os.name != "nt",
    reason=("Le REFUS d'un chemin absolu Windows n'est observable que sur Windows, ou "
            "`C:\\...` est absolu (sur POSIX c'est un nom relatif, legitimement dans la "
            "racine). Preuve portable dans le test source ci-dessus ; ce test TOURNE sur "
            "les runners Windows (preuve B-24 au Registres/mission.jsonl)."),
)
def test_bash_chemin_windows_refuse_sur_windows(racine, env_tmpdir, tmp_path):
    script = ecrire_garde(tmp_path, racine)
    code, err = run(script, charge("Bash", {"command": "type C:\\Windows\\System32\\x"}, cwd=racine), env=env_tmpdir)
    assert code == 2, f"chemin Windows absolu doit être refusé (stderr={err!r})"


def test_auto_protection_mv_du_script_installe_refuse(racine, env_tmpdir):
    # install_guard_fs place le script sous racine/.claude/hooks/ : un mv qui le
    # cible par son chemin relatif (avec séparateur) est capté et refusé.
    script, _hook = install_guard_fs(racine)
    code, err = run(
        script,
        charge("Bash", {"command": "mv .claude/hooks/forgeai_guard_fs.py /tmp/x"}, cwd=racine),
        env=env_tmpdir,
    )
    assert code == 2, f"mv du script installé doit être refusé (stderr={err!r})"


def test_cwd_relatif_refus_structurel(racine, env_tmpdir, tmp_path):
    script = ecrire_garde(tmp_path, racine)
    code, err = run(script, charge("Read", {"file_path": "a"}, cwd="relatif/non/absolu"), env=env_tmpdir)
    assert code == 2, f"cwd relatif doit provoquer un refus fail-closed (stderr={err!r})"


def test_cwd_absent_refus_structurel(racine, env_tmpdir, tmp_path):
    script = ecrire_garde(tmp_path, racine)
    charge_sans_cwd = {"tool_name": "Read", "tool_input": {"file_path": "a"}}
    code, err = run(script, charge_sans_cwd, env=env_tmpdir)
    assert code == 2, f"cwd absent doit provoquer un refus fail-closed (stderr={err!r})"


def test_non_regression_commandes_sans_chemin_autorisees(racine, env_tmpdir, tmp_path):
    script = ecrire_garde(tmp_path, racine)
    for cmd in ("echo bonjour", "ls -la"):
        code, err = run(script, charge("Bash", {"command": cmd}, cwd=racine), env=env_tmpdir)
        assert code == 0, f"commande sans chemin doit être autorisée: {cmd!r} (stderr={err!r})"


def test_non_regression_chemin_relatif_dans_racine_autorise(racine, env_tmpdir, tmp_path):
    (racine / "sous").mkdir()
    (racine / "sous" / "fichier.txt").write_text("x", encoding="utf-8")
    script = ecrire_garde(tmp_path, racine)
    code, err = run(script, charge("Bash", {"command": "cat sous/fichier.txt"}, cwd=racine), env=env_tmpdir)
    assert code == 0, f"chemin relatif restant dans la racine doit être autorisé (stderr={err!r})"


def test_double_compile_source_et_fichier_installe(racine):
    # CA-7 : le SOURCE rendu compile ET le fichier écrit sur disque compile aussi
    # (deux passes distinctes).
    src = generate_guard_fs(racine)
    compile(src, "<source-genere>", "exec")
    script, _hook = install_guard_fs(racine)
    compile(Path(script).read_text(encoding="utf-8"), "<fichier-installe>", "exec")
# AJOUTS dans tests/test_guard_fs.py (appendices aux tests existants)


class TestOperateursColles:
    """B-24d — ferme le contournement par opérateurs shell collés au chemin.

    Mesure : ``shlex.split(commande, posix=True)`` ne sépare pas
    ``<``, ``>``, ``;``, ``|``, ``&`` lorsqu'ils sont collés au token
    voisin (``cat</etc/passwd`` reste un seul token). Le correctif
    remplace le tokenizer par ``shlex.shlex(..., punctuation_chars=True,
    whitespace_split=True)`` qui, lui, les isole. Ces tests exécutent
    RÉELLEMENT la garde générée via subprocess et asserent l'exit code.
    """

    def test_cat_redirection_entree_collee_refuse(self, tmp_path, racine, env_tmpdir):
        """``cat</etc/passwd`` : ``<`` collé à ``cat``, mais la cible
        ``/etc/passwd`` DOIT être vue comme un chemin littéral et
        REFUSÉE (sortie de la racine)."""
        script = ecrire_garde(tmp_path, racine)
        ch = charge("Bash", {"command": "cat</etc/passwd"}, cwd=racine)
        exit_code, stderr = run(script, ch, env=env_tmpdir)
        assert exit_code == 2, (
            "cat</etc/passwd doit être refusé (exit 2) ; "
            "shlex.split ne sépare pas '<' collé, mais shlex.shlex "
            "avec punctuation_chars=True doit le faire. stderr="
            f"{stderr!r}"
        )

    def test_echo_redirection_sortie_collee_refuse_settings(
        self, tmp_path, racine, env_tmpdir
    ):
        """``echo bad>.claude/settings.json`` : ``>`` collé, contourne
        l'auto-protection si mal tokenisé. Doit être REFUSÉ (exit 2)."""
        script = ecrire_garde(tmp_path, racine)
        ch = charge(
            "Bash", {"command": "echo bad>.claude/settings.json"}, cwd=racine
        )
        exit_code, stderr = run(script, ch, env=env_tmpdir)
        assert exit_code == 2, (
            "echo bad>.claude/settings.json doit être refusé (exit 2) "
            "pour protéger settings.json. stderr="
            f"{stderr!r}"
        )

    def test_point_virgule_colle_refuse(self, tmp_path, racine, env_tmpdir):
        """``cat;/etc/passwd`` : ``;`` collé à ``cat``. Doit refuser
        l'accès à ``/etc/passwd``."""
        script = ecrire_garde(tmp_path, racine)
        ch = charge("Bash", {"command": "cat;/etc/passwd"}, cwd=racine)
        exit_code, stderr = run(script, ch, env=env_tmpdir)
        assert exit_code == 2, (
            "cat;/etc/passwd doit être refusé (exit 2). stderr="
            f"{stderr!r}"
        )

    def test_pipe_colle_refuse(self, tmp_path, racine, env_tmpdir):
        """``cat|/bin/sh`` : ``|`` collé. ``/bin/sh`` doit être vu comme
        un chemin littéral et REFUSÉ."""
        script = ecrire_garde(tmp_path, racine)
        ch = charge("Bash", {"command": "cat|/bin/sh"}, cwd=racine)
        exit_code, stderr = run(script, ch, env=env_tmpdir)
        assert exit_code == 2, (
            "cat|/bin/sh doit être refusé (exit 2). stderr="
            f"{stderr!r}"
        )

    def test_redirection_append_collee_refuse(self, tmp_path, racine, env_tmpdir):
        """``echo x>>/etc/hosts`` : ``>>`` collé à ``x``. La cible
        ``/etc/hosts`` doit être REFUSÉE (exit 2)."""
        script = ecrire_garde(tmp_path, racine)
        ch = charge("Bash", {"command": "echo x>>/etc/hosts"}, cwd=racine)
        exit_code, stderr = run(script, ch, env=env_tmpdir)
        assert exit_code == 2, (
            "echo x>>/etc/hosts doit être refusé (exit 2). stderr="
            f"{stderr!r}"
        )

    def test_non_regression_guillemet_superieur_dans_nom(
        self, tmp_path, racine, env_tmpdir
    ):
        """NON-RÉGRESSION : un ``>`` LITTÉRAL entre guillemets fait
        partie du nom de fichier, pas un opérateur.

        Crée ``racine/fichier>bizarre.txt`` puis ``cat "fichier>bizarre.txt"``
        avec cwd=racine doit être AUTORISÉ (exit 0)."""
        cible = racine / "fichier>bizarre.txt"
        cible.write_text("contenu\n", encoding="utf-8")
        script = ecrire_garde(tmp_path, racine)
        ch = charge(
            "Bash", {"command": 'cat "fichier>bizarre.txt"'}, cwd=racine
        )
        exit_code, stderr = run(script, ch, env=env_tmpdir)
        assert exit_code == 0, (
            'cat "fichier>bizarre.txt" doit être autorisé (exit 0) ; '
            "le '>' entre guillemets fait partie du nom de fichier. "
            f"stderr={stderr!r}"
        )

    def test_non_regression_commandes_inoffensives(
        self, tmp_path, racine, env_tmpdir
    ):
        """NON-RÉGRESSION : commandes sans chemin littéral, et commande
        avec chemin LITTÉRAL SOUS LA RACINE, restent AUTORISÉES.

        Couvre ``echo bonjour``, ``ls -la``, ``cat sous/fichier.txt``
        avec fichier créé dans la racine et cwd=racine."""
        sous = racine / "sous"
        sous.mkdir()
        (sous / "fichier.txt").write_text("ok\n", encoding="utf-8")

        script = ecrire_garde(tmp_path, racine)
        for cmd in ("echo bonjour", "ls -la", "cat sous/fichier.txt"):
            ch = charge("Bash", {"command": cmd}, cwd=racine)
            exit_code, stderr = run(script, ch, env=env_tmpdir)
            assert exit_code == 0, (
                f"{cmd!r} doit être autorisé (exit 0) — non-régression. "
                f"stderr={stderr!r}"
            )


# ── Tour 4 : validation du cwd (revue scellée, objection critique Gemini) ──
def test_cwd_hors_racine_nom_nu_refuse(tmp_path, racine, env_tmpdir):
    """cwd=/etc + Bash 'cat passwd' -> exit 2.

    « passwd » est un nom nu sans séparateur : l'extraction de candidats
    l'ignore par construction — seul le contrôle du cwd peut refuser.
    """
    script = ecrire_garde(tmp_path, racine)
    code, _ = run(
        script,
        charge("Bash", {"command": "cat passwd"}, cwd="/etc"),
        env=env_tmpdir,
    )
    assert code == 2


def test_cwd_sous_claude_autoprotection_refuse(tmp_path, racine, env_tmpdir):
    """cwd=<racine>/.claude + Bash 'echo bad > settings.json' -> exit 2.

    .claude est sous ROOT, donc le confinement seul laisserait passer :
    c'est l'auto-protection du cwd (outil d'écriture) qui doit refuser.
    """
    (racine / ".claude").mkdir()
    script = ecrire_garde(tmp_path, racine)
    code, _ = run(
        script,
        charge(
            "Bash",
            {"command": "echo bad > settings.json"},
            cwd=str(racine / ".claude"),
        ),
        env=env_tmpdir,
    )
    assert code == 2


def test_cwd_hors_racine_sans_candidat_refuse(tmp_path, racine, env_tmpdir):
    """cwd=/etc + Bash 'echo bonjour' -> exit 2 : le cwd seul suffit à
    refuser, même sans aucun chemin candidat dans la commande."""
    script = ecrire_garde(tmp_path, racine)
    code, _ = run(
        script,
        charge("Bash", {"command": "echo bonjour"}, cwd="/etc"),
        env=env_tmpdir,
    )
    assert code == 2


def test_cwd_racine_commandes_inoffensives_autorisees(tmp_path, racine, env_tmpdir):
    """Non-régression : cwd=racine — les commandes sans chemin restent
    autorisées."""
    script = ecrire_garde(tmp_path, racine)
    for commande in ("echo bonjour", "ls -la"):
        code, _ = run(
            script,
            charge("Bash", {"command": commande}, cwd=str(racine)),
            env=env_tmpdir,
        )
        assert code == 0, commande


def test_cwd_sous_repertoire_racine_autorise(tmp_path, racine, env_tmpdir):
    """Non-régression : cwd = un sous-répertoire de la racine — un nom nu
    qui s'y résout reste autorisé."""
    sous = racine / "sous"
    sous.mkdir()
    (sous / "f.txt").write_text("contenu\n", encoding="utf-8")
    script = ecrire_garde(tmp_path, racine)
    code, _ = run(
        script,
        charge("Bash", {"command": "cat f.txt"}, cwd=str(sous)),
        env=env_tmpdir,
    )
    assert code == 0


def test_refus_cwd_journalise_et_chaine_verifiee(tmp_path, racine, env_tmpdir):
    """Un refus de type cwd est journalisé en guard_fs_denied, et la chaîne
    du registre est acceptée par le verify officiel du produit."""
    reg = tmp_path / "registre.jsonl"
    script = ecrire_garde(tmp_path, racine, registre=reg)
    code, _ = run(
        script,
        charge("Bash", {"command": "cat passwd"}, cwd="/etc"),
        env=env_tmpdir,
    )
    assert code == 2
    lignes = [
        ligne
        for ligne in reg.read_text(encoding="utf-8").splitlines()
        if ligne.strip()
    ]
    assert lignes, "le refus par cwd doit être journalisé"
    for ligne in lignes:
        json.loads(ligne)  # chaque entrée est un JSON valide
    assert any("guard_fs_denied" in ligne for ligne in lignes)
    proc = subprocess.run(
        [sys.executable, str(REGISTRE_PY), "verify", str(reg)],
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stderr


# ── Tour 5 : le repli de tokenisation ne doit pas etre une porte ──
def test_repli_heredoc_guillemet_orphelin_cible_hors_racine_refuse(
    tmp_path, racine, env_tmpdir
):
    """Repli forcé par here-doc à guillemet orphelin, cible hors racine -> exit 2.

    La commande contient un here-doc avec un guillemet orphelin qui force
    shlex à lever ValueError ; le repli doit malgré tout reconnaître
    `/etc/passwd` comme chemin hors racine et REFUSER.
    """
    script = ecrire_garde(tmp_path, racine)
    commande = 'cat</etc/passwd\ncat <<EOF\n"\nEOF'
    code, stderr = run(
        script, charge("Bash", {"command": commande}, cwd=racine), env=env_tmpdir
    )
    assert code == 2, f"attendu exit 2, obtenu {code} (stderr={stderr!r})"


def test_repli_cible_auto_protection_refuse(tmp_path, racine, env_tmpdir):
    """Repli forcé, cible = auto-protection (.claude/settings.json) -> exit 2.

    Le guillemet orphelin final force le ValueError de shlex ; le repli
    doit malgré tout reconnaître `.claude/settings.json` comme chemin
    protégé et REFUSER la réécriture de la config de la garde.
    """
    script = ecrire_garde(tmp_path, racine)
    commande = 'echo bad >.claude/settings.json "'
    code, stderr = run(
        script, charge("Bash", {"command": commande}, cwd=racine), env=env_tmpdir
    )
    assert code == 2, f"attendu exit 2, obtenu {code} (stderr={stderr!r})"


def test_repli_operateur_colle_cible_hors_racine_refuse(
    tmp_path, racine, env_tmpdir
):
    """Repli forcé, opérateur COLLÉ et cible hors racine -> exit 2.

    `cat</etc/passwd` a l'opérateur de redirection COLLÉ à la commande ;
    le repli doit le séparer pour reconnaître `/etc/passwd` comme chemin
    hors racine et REFUSER.
    """
    script = ecrire_garde(tmp_path, racine)
    commande = 'cat</etc/passwd "'
    code, stderr = run(
        script, charge("Bash", {"command": commande}, cwd=racine), env=env_tmpdir
    )
    assert code == 2, f"attendu exit 2, obtenu {code} (stderr={stderr!r})"


def test_repli_cible_dans_racine_autorise(tmp_path, racine, env_tmpdir):
    """Repli forcé, cible RESTANT dans la racine -> exit 0.

    Prouve que le repli n'est pas un refus aveugle : il analyse vraiment
    les tokens et autorise une cible interne à la racine malgré le
    guillemet orphelin qui déclenche le ValueError de shlex.
    """
    sous = racine / "sous"
    sous.mkdir()
    cible = sous / "f.txt"
    cible.write_text("contenu", encoding="utf-8")
    script = ecrire_garde(tmp_path, racine)
    commande = 'cat sous/f.txt "'
    code, stderr = run(
        script, charge("Bash", {"command": commande}, cwd=racine), env=env_tmpdir
    )
    assert code == 0, f"attendu exit 0, obtenu {code} (stderr={stderr!r})"


def test_non_regression_guillemets_equilibres_autorise(
    tmp_path, racine, env_tmpdir
):
    """NON-RÉGRESSION du chemin NOMINAL : guillemets ÉQUILIBRÉS préservés.

    Avec des guillemets équilibrés, shlex tokenise correctement
    `fichier>bizarre.txt` comme un seul token littéral ; la garde ne le
    reconnaît pas comme chemin (pas de `/`, pas de préfixe `~`/`.`,
    pas de lecteur Windows) et l'AUTORISE. Ce test verrouille le chemin
    nominal face à toute régression du repli.
    """
    cible = racine / "fichier>bizarre.txt"
    cible.write_text("contenu", encoding="utf-8")
    script = ecrire_garde(tmp_path, racine)
    commande = 'cat "fichier>bizarre.txt"'
    code, stderr = run(
        script, charge("Bash", {"command": commande}, cwd=racine), env=env_tmpdir
    )
    assert code == 0, f"attendu exit 0, obtenu {code} (stderr={stderr!r})"


# ── Tour 6 : extraction sans tokenisation shell (ADR option C) ──
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from forgeai.ide.guard_fs import generate_guard_fs


# ---------------------------------------------------------------------------
# AXE A — vecteurs d'evasion CAPTES (exit 2), cwd=racine
# ---------------------------------------------------------------------------

def test_A1_cat_guillemet_double_ferm_guillemet_simple(tmp_path, racine, env_tmpdir):
    script = ecrire_garde(tmp_path, racine)
    c = charge("Bash", {"command": 'cat "/etc/passwd" "'}, cwd=racine)
    exit_code, _ = run(script, c, env=env_tmpdir)
    assert exit_code == 2


def test_A2_cat_guillemet_simple_ferm_guillemet_double(tmp_path, racine, env_tmpdir):
    script = ecrire_garde(tmp_path, racine)
    c = charge("Bash", {"command": "cat '/etc/passwd' '"}, cwd=racine)
    exit_code, _ = run(script, c, env=env_tmpdir)
    assert exit_code == 2


def test_A3_redirection_entree_chemin_colle(tmp_path, racine, env_tmpdir):
    script = ecrire_garde(tmp_path, racine)
    c = charge("Bash", {"command": 'cat</etc/passwd "'}, cwd=racine)
    exit_code, _ = run(script, c, env=env_tmpdir)
    assert exit_code == 2


def test_A4_redirection_sortie_vers_settings_json(tmp_path, racine, env_tmpdir):
    script = ecrire_garde(tmp_path, racine)
    commande = 'echo bad >".claude/settings.json" "'
    c = charge("Bash", {"command": commande}, cwd=racine)
    exit_code, _ = run(script, c, env=env_tmpdir)
    assert exit_code == 2


def test_A5_substitution_commande_chemin(tmp_path, racine, env_tmpdir):
    script = ecrire_garde(tmp_path, racine)
    c = charge("Bash", {"command": 'cat $(echo /etc/passwd) "'}, cwd=racine)
    exit_code, _ = run(script, c, env=env_tmpdir)
    assert exit_code == 2


def test_A6_heredoc_apostrophe_francaise(tmp_path, racine, env_tmpdir):
    script = ecrire_garde(tmp_path, racine)
    commande = "cat <<EOF\nc'est /etc/passwd\nEOF"
    c = charge("Bash", {"command": commande}, cwd=racine)
    exit_code, _ = run(script, c, env=env_tmpdir)
    assert exit_code == 2


def test_A7_cible_nue_collee_operateur(tmp_path, racine, env_tmpdir):
    script = ecrire_garde(tmp_path, racine)
    c = charge("Bash", {"command": "rm -rf>.claude"}, cwd=racine)
    exit_code, _ = run(script, c, env=env_tmpdir)
    assert exit_code == 2


# ---------------------------------------------------------------------------
# AXE B — non-regression syntaxique, AUCUN faux positif (exit 0)
# ---------------------------------------------------------------------------

def test_B1_apostrophe_dans_mot(tmp_path, racine, env_tmpdir):
    script = ecrire_garde(tmp_path, racine)
    c = charge("Bash", {"command": "echo l'utilisateur"}, cwd=racine)
    exit_code, _ = run(script, c, env=env_tmpdir)
    assert exit_code == 0


def test_B2_apostrophe_guillemet_simple(tmp_path, racine, env_tmpdir):
    script = ecrire_garde(tmp_path, racine)
    c = charge("Bash", {"command": "grep don't fichier.txt"}, cwd=racine)
    exit_code, _ = run(script, c, env=env_tmpdir)
    assert exit_code == 0


def test_B3_globe_etoile(tmp_path, racine, env_tmpdir):
    script = ecrire_garde(tmp_path, racine)
    c = charge("Bash", {"command": "ls *.py"}, cwd=racine)
    exit_code, _ = run(script, c, env=env_tmpdir)
    assert exit_code == 0


def test_B4_variable_HOME_resolue_sous_racine(tmp_path, racine, env_tmpdir):
    script = ecrire_garde(tmp_path, racine)
    c = charge("Bash", {"command": "cat $HOME/truc"}, cwd=racine)
    exit_code, _ = run(script, c, env=env_tmpdir)
    assert exit_code == 0


def test_B5_echo_bonjour(tmp_path, racine, env_tmpdir):
    script = ecrire_garde(tmp_path, racine)
    c = charge("Bash", {"command": "echo bonjour"}, cwd=racine)
    exit_code, _ = run(script, c, env=env_tmpdir)
    assert exit_code == 0


# ---------------------------------------------------------------------------
# AXE C — symetrie backslash
# ---------------------------------------------------------------------------

def test_C1_posix_backslash_chemin_absolu(tmp_path, racine, env_tmpdir):
    script = ecrire_garde(tmp_path, racine)
    c = charge("Bash", {"command": 'cat \\/etc/passwd "'}, cwd=racine)
    exit_code, _ = run(script, c, env=env_tmpdir)
    assert exit_code == 2


def test_C2a_windows_condition_apres_chemin_present_dans_source(tmp_path, racine):
    """Sur Windows, le backslash fait partie des separateurs chemins : on ne
    le retire PAS. Ce test est portable : il verifie la PRESENCE du predicat
    ``os.sep != chr(92)`` dans le source rendu — preuve que la garde
    distingue bien les deux plateformes."""
    src = generate_guard_fs(racine)
    assert "os.sep != chr(92)" in src


@pytest.mark.skipif(os.name != "nt", reason="Comportement Windows; voir Registres/")
def test_C2b_windows_backslash_conserve(tmp_path, racine, env_tmpdir):
    script = ecrire_garde(tmp_path, racine)
    c = charge("Bash", {"command": 'cat \\/etc/passwd "'}, cwd=racine)
    exit_code, _ = run(script, c, env=env_tmpdir)
    # Sur Windows le backslash est un separateur de chemin LEGAL -> pas de
    # resolution vers un chemin absolu hors racine -> autorisation.
    assert exit_code == 0


# ---------------------------------------------------------------------------
# AXE D — appartenance a la racine apres extraction
# ---------------------------------------------------------------------------

def test_D1_chemin_sous_racine_autorise(tmp_path, racine, env_tmpdir):
    sous = racine / "sous"
    sous.mkdir()
    cible = sous / "f.txt"
    cible.write_text("ok", encoding="utf-8")
    script = ecrire_garde(tmp_path, racine)
    c = charge("Bash", {"command": "cat sous/f.txt"}, cwd=racine)
    exit_code, _ = run(script, c, env=env_tmpdir)
    assert exit_code == 0


def test_D2_chemin_hors_racine_message_cite_resolu(tmp_path, racine, env_tmpdir):
    script = ecrire_garde(tmp_path, racine)
    c = charge("Bash", {"command": "cat /etc/passwd"}, cwd=racine)
    exit_code, stderr = run(script, c, env=env_tmpdir)
    assert exit_code == 2
    # La citation du chemin RESOLU (et non du fragment brut) prouve que
    # l'extraction a ete suivie d'une resolution reelle.
    assert "/etc/passwd" in stderr


# ── Tour 7 : normalisation de la continuation de ligne bash ──
def test_continuation_ligne_chemin_relatif_sortie(racine, env_tmpdir, tmp_path):
    """`cat .<backslash-newline>./.<backslash-newline>./etc/passwd` reconstitue `cat ../../etc/passwd`
    qui sort de la racine : doit être REFUSÉ (exit 2)."""
    script = ecrire_garde(tmp_path, racine)
    commande = "cat .\\\n./.\\\n./etc/passwd"
    code, _ = run(script, charge("Bash", {"command": commande}, cwd=racine), env=env_tmpdir)
    assert code == 2


def test_continuation_ligne_auto_protection(racine, env_tmpdir, tmp_path):
    """`cat .cla<backslash-newline>ude/settings.json` reconstitue `cat .claude/settings.json`
    qui est un fichier d'auto-protection : doit être REFUSÉ (exit 2)."""
    script = ecrire_garde(tmp_path, racine)
    commande = "cat .cla\\\nude/settings.json"
    code, _ = run(script, charge("Bash", {"command": commande}, cwd=racine), env=env_tmpdir)
    assert code == 2


def test_continuation_ligne_chemin_absolu(racine, env_tmpdir, tmp_path):
    """`cat /etc/pas<backslash-newline>swd` reconstitue `cat /etc/passwd` : doit être REFUSÉ (exit 2)."""
    script = ecrire_garde(tmp_path, racine)
    commande = "cat /etc/pas\\\nswd"
    code, _ = run(script, charge("Bash", {"command": commande}, cwd=racine), env=env_tmpdir)
    assert code == 2


def test_continuation_ligne_parentheses_sortie(racine, env_tmpdir, tmp_path):
    """`cat sous/../<backslash-newline>../etc/passwd` reconstitue `cat sous/../../etc/passwd`
    qui sort de la racine : doit être REFUSÉ (exit 2)."""
    script = ecrire_garde(tmp_path, racine)
    (racine / "sous").mkdir()
    commande = "cat sous/../\\\n../etc/passwd"
    code, _ = run(script, charge("Bash", {"command": commande}, cwd=racine), env=env_tmpdir)
    assert code == 2


def test_continuation_ligne_chemin_interne(racine, env_tmpdir, tmp_path):
    """NON-REGRESSION : `cat sous/f<backslash-newline>.txt` reconstitue `cat sous/f.txt`
    qui est un chemin INTERNE existant : doit rester AUTORISÉ (exit 0)."""
    script = ecrire_garde(tmp_path, racine)
    sous = racine / "sous"
    sous.mkdir()
    (sous / "f.txt").write_text("contenu", encoding="utf-8")
    commande = "cat sous/f\\\n.txt"
    code, _ = run(script, charge("Bash", {"command": commande}, cwd=racine), env=env_tmpdir)
    assert code == 0


def test_continuation_ligne_non_regression(racine, env_tmpdir, tmp_path):
    """NON-REGRESSION : une commande sans continuation reste inchangée.
    `echo bonjour` -> exit 0 ; `cat /etc/passwd` -> exit 2."""
    script = ecrire_garde(tmp_path, racine)
    code, _ = run(script, charge("Bash", {"command": "echo bonjour"}, cwd=racine), env=env_tmpdir)
    assert code == 0
    code, _ = run(script, charge("Bash", {"command": "cat /etc/passwd"}, cwd=racine), env=env_tmpdir)
    assert code == 2
