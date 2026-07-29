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
