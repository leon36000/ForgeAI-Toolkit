"""SSH-030 — `SshRunner.run()` ne doit pas laisser SSH aplatir un argv contenant des espaces.

Trouvé en pilotant `forgeai node discover` contre du VRAI matériel distant (deux machines
physiques différentes — l'une NVIDIA, l'autre AMD, ni l'une ni l'autre avec docker) : les deux
rapportaient `docker ✓` et le mauvais vendor GPU, un résultat IDENTIQUE qui se trouvait
correspondre à l'environnement de la machine orchestratrice, pas des nœuds sondés.

Preuve au niveau du protocole (`ssh -v`, contre un vrai hôte) :
    debug1: Sending command: sh -c command -v "$1" sh docker
OpenSSH rejoint les éléments d'argv avec un simple espace, SANS les re-quoter, avant de les
transmettre au shell distant — tronquant `-c` au premier mot pour tout script multi-mots.
"""

from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from forgeai.network.remote_probe import SshRunner

# Argv RÉEL utilisé par discover.py — celui qui casse sur le code d'avant le correctif.
ARGV_CASSE = ["sh", "-c", 'command -v "$1"', "sh", "docker"]

# Argv simples RÉELLEMENT utilisés ailleurs dans le dépôt (aucun espace par élément) :
# la preuve de non-régression porte sur CES appels précis, pas des exemples inventés.
ARGV_SIMPLES_REELS = [
    ["kubectl", "get", "nodes", "-o", "json"],   # network/nodes.py:19
    ["cat", "/proc/meminfo"],                     # network/remote_probe.py:165
    ["lscpu", "-J"],                               # hardware/detect.py:37
    ["nvidia-smi", "-L"],                          # network/discover.py:107
    ["ss", "-tlnH"],                               # network/discover.py:100
]


def _capturer_commande_ssh(monkeypatch, argv: list[str]) -> list[str]:
    """Appelle `SshRunner.run(argv)` avec `subprocess.run` intercepté, contourne
    `_enroll()` (réseau) en pré-remplissant `_known_hosts`, et renvoie la commande SSH
    RÉELLEMENT construite — pas une reconstruction manuelle qui pourrait diverger du code."""
    capture: dict[str, list[str]] = {}

    def faux_run(cmd, **kwargs):
        capture["cmd"] = cmd

        class Resultat:
            returncode = 0
            stdout = ""

        return Resultat()

    monkeypatch.setattr(subprocess, "run", faux_run)

    runner = SshRunner("user", "host", "/cle", "SHA256:" + "a" * 43)
    runner._known_hosts = "/dev/null"  # évite enroll_hostkey (réseau)
    runner.run(argv)
    return capture["cmd"]


def test_g1_argv_multi_mots_ne_laisse_qu_un_seul_element_apres_double_tiret(monkeypatch):
    """CA1/CA3 — sans ça, SSH a plusieurs éléments à aplatir par espace : rien ne l'empêche."""
    cmd = _capturer_commande_ssh(monkeypatch, ARGV_CASSE)
    partie_distante = cmd[cmd.index("--") + 1:]
    assert len(partie_distante) == 1, (
        f"un seul élément doit suivre '--', sinon SSH les rejoint par espace sans les "
        f"re-quoter : {partie_distante!r}"
    )


def test_g2_l_element_unique_survit_a_un_vrai_shell_local(monkeypatch):
    """CA1 — LE détecteur du défaut mesuré.

    On rejoue exactement ce qu'un shell distant POSIX ferait en recevant cette chaîne : on
    l'exécute via un VRAI `/bin/sh -c` local. Sur le code d'avant le correctif, ce test
    échouerait à la ligne précédente (plusieurs éléments après --) ; ici on vérifie en plus
    que l'élément unique, une fois réellement interprété par un shell, distingue correctement
    un binaire présent d'un binaire absent — pas seulement qu'il « a l'air » bien formé.
    """
    cmd_present = _capturer_commande_ssh(
        monkeypatch, ["sh", "-c", 'command -v "$1"', "sh", "ls"]
    )
    cmd_absent = _capturer_commande_ssh(
        monkeypatch, ["sh", "-c", 'command -v "$1"', "sh", "zzz-binaire-forgeai-inexistant-030"]
    )

    script_present = cmd_present[cmd_present.index("--") + 1]
    script_absent = cmd_absent[cmd_absent.index("--") + 1]

    # subprocess.run reste monkeypatché (stub) après la capture : on l'annule pour que la
    # vérification ci-dessous invoque un VRAI /bin/sh, exactement le rôle du shell distant.
    monkeypatch.undo()
    r_present = subprocess.run(["sh", "-c", script_present], capture_output=True, text=True)
    r_absent = subprocess.run(["sh", "-c", script_absent], capture_output=True, text=True)

    assert r_present.returncode == 0 and r_present.stdout.strip(), (
        f"un binaire RÉELLEMENT présent (ls) doit être détecté : rc={r_present.returncode} "
        f"stdout={r_present.stdout!r}"
    )
    assert r_absent.returncode != 0, (
        f"un binaire ABSENT doit rester non détecté, pas rc=0 par accident : "
        f"rc={r_absent.returncode} stdout={r_absent.stdout!r}"
    )


def test_g3_argv_simples_reels_produisent_la_meme_chaine_sur_le_fil(monkeypatch):
    """CA2 — non-régression stricte : ce qui compte n'est pas le NOMBRE d'éléments après
    `--` (qui change légitimement, 1 seul après correctif), mais la CHAÎNE que SSH transmet
    au final au shell distant — celle-ci doit rester identique caractère pour caractère à
    l'aplatissement naïf par espace qu'OpenSSH appliquait déjà (`ssh -v` fait foi, voir
    l'en-tête du module). Un test qui figerait la structure au lieu du contenu transmis
    prendrait le format pour la propriété, et non l'absence de régression réelle.
    """
    for argv in ARGV_SIMPLES_REELS:
        cmd = _capturer_commande_ssh(monkeypatch, argv)
        partie_distante = cmd[cmd.index("--") + 1:]
        chaine_transmise = " ".join(partie_distante)  # ce que SSH aplatit réellement
        avant_correctif = " ".join(argv)
        assert chaine_transmise == avant_correctif, (
            f"régression pour {argv!r} : {chaine_transmise!r} != {avant_correctif!r}"
        )


def test_g4_round_trip_shlex_exact():
    """CA3 — la reconstruction côté shell distant doit redonner l'argv D'ORIGINE, sans
    double-échappement ni perte des guillemets internes intentionnels (`\"$1\"`)."""
    assert shlex.split(shlex.join(ARGV_CASSE)) == ARGV_CASSE


def test_g6_docker_ps_format_second_defaut_repare(monkeypatch):
    """CA1 — second défaut réel, trouvé par la revue d'architecture, pas par la mesure
    initiale : `discover.py:85-87` interroge `docker ps --format {{.Image}}|{{.Names}}|...`.
    Le `|` n'a AUCUN espace autour de lui, donc échappait à la mesure originale (limitée aux
    espaces) — mais une fois aplati par SSH, ce `|` redevient un VRAI pipe shell. Sur le code
    d'avant ce correctif, la découverte de conteneurs distants via SSH ne renvoyait donc RIEN,
    silencieusement, depuis toujours. Le même correctif de primitive le répare : ce test le
    PROUVE plutôt que de laisser cette réparation être un effet de bord non vérifié.
    """
    argv = ["docker", "ps", "--format", "{{.Image}}|{{.Names}}|{{.Ports}}"]
    cmd = _capturer_commande_ssh(monkeypatch, argv)
    # Toujours rejoindre TOUS les éléments après `--`, jamais prendre le premier seul :
    # sous une régression vers l'extension naïve, `docker` seul (sans arguments) réussirait
    # par coïncidence et masquerait la mutation — piège déjà rencontré sur ce même fichier.
    partie_distante = cmd[cmd.index("--") + 1:]
    script = " ".join(partie_distante)

    monkeypatch.undo()
    r = subprocess.run(["sh", "-c", script], capture_output=True, text=True)

    assert r.returncode == 0, (
        f"le format docker doit survivre à l'aplatissement SSH (le '|' ne doit plus être "
        f"interprété comme un pipe) : rc={r.returncode} stderr={r.stderr!r}"
    )
    assert "not found" not in r.stderr, (
        "signature exacte du défaut : sh interprétait {{.Names}} comme une commande"
    )


def test_g5_chemin_reel_discover_distingue_present_et_absent(monkeypatch, tmp_path):
    """CA1/CA4 — bout en bout via `discover.inventaire()`, le point d'entrée réel de
    `forgeai node discover`, pas un test unitaire isolé de la primitive seule."""
    from forgeai.network.discover import inventaire

    capture: dict[str, list[list[str]]] = {"appels": []}

    def faux_run(cmd, **kwargs):
        capture["appels"].append(cmd)

        class R:
            returncode = 0
            stdout = ""

        return R()

    monkeypatch.setattr(subprocess, "run", faux_run)

    runner = SshRunner("user", "host", "/cle", "SHA256:" + "a" * 43)
    runner._known_hosts = "/dev/null"

    signatures = [{"id": "docker", "binaire": "docker"}, {"id": "redis", "binaire": "redis-cli"}]
    inventaire(runner, signatures)

    for appel in capture["appels"]:
        if "--" not in appel:
            continue
        partie_distante = appel[appel.index("--") + 1:]
        assert len(partie_distante) == 1, (
            f"discover.py doit produire un argv qui survit à SSH : {partie_distante!r}"
        )
