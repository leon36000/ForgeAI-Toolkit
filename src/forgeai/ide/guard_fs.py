"""Génération et installation de la garde filesystem autonome (B-24).

Pourquoi un script GÉNÉRÉ plutôt qu'un module du produit : la garde est
branchée en hook PreToolUse chez l'utilisateur et doit survivre à la
désinstallation de forgeai — elle n'importe donc jamais le produit, uniquement
la stdlib. Trois principes la gouvernent :

- fail-closed : toute exception interne, un stdin illisible ou un JSON
  invalide se convertissent en REFUS (exit 2) ; un refus tient même si la
  journalisation échoue ;
- racine figée : la racine de confinement est résolue (``os.path.realpath``)
  AU MOMENT DE LA GÉNÉRATION et embarquée en constante dans le script —
  jamais dérivée du cwd à l'exécution, sinon le confinement suivrait le
  confiné ;
- auto-protection : même dans la racine, un outil d'écriture ne peut réécrire
  ni la garde elle-même, ni le répertoire des hooks, ni ``settings.json`` —
  une garde réécrivable par le confiné est du théâtre.

Le format du registre JSONL répliqué dans le script généré est une duplication
ASSUMÉE de celui de ``forgeai.core.registre`` : c'est un contrat de
compatibilité avec la vérification de chaîne du produit, à faire évoluer de
pair avec lui.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from . import IDEError
from .bootstrap import HookSpec

__all__ = ["generate_guard_fs", "install_guard_fs"]

# Source complet du script autonome déposé chez l'utilisateur. Trois
# emplacements — __FORGEAI_ROOT__, __FORGEAI_REGISTRE__, __FORGEAI_ALLOW__ —
# sont substitués par generate_guard_fs via repr() : jamais d'interpolation
# nue dans du code généré. Chaîne brute : les séquences « \n » / « \r » du
# script généré doivent rester des échappements littéraux dans le template.
_SCRIPT_TEMPLATE = r'''#!/usr/bin/env python3
"""Garde filesystem autonome générée par ForgeAI (B-24) — hook PreToolUse.

Autonome par construction : stdlib uniquement, n'importe jamais forgeai, et
survit donc à la désinstallation du produit. La racine de confinement est
figée (realpath) au moment de la génération — jamais dérivée du cwd à
l'exécution. Politique fail-closed : stdin illisible, JSON invalide ou toute
exception interne se convertissent en REFUS (exit 2) ; un refus tient même si
la journalisation échoue.

CONTRAT ASSUMI : le format d'entrée du registre JSONL répliqué ici (seq, ts,
type, actor, payload, prev_hash, hash sha256 du matériau canonique, ligne JSON
compacte à clés triées) est celui de forgeai.core.registre. Cette duplication
est volontaire : elle préserve la vérification de chaîne du produit. Toute
évolution du format doit être coordonnée des deux côtés.
"""

import hashlib
import json
import os
import sys
import re
import tempfile
from datetime import datetime, timezone

try:
    import fcntl
except ImportError:
    # Windows : pas de flock — écriture sans verrou, contrat assumé.
    fcntl = None

ROOT = __FORGEAI_ROOT__
REGISTRE_DEFAUT = __FORGEAI_REGISTRE__
ALLOW_PATH = __FORGEAI_ALLOW__

GENESIS = "0" * 64
WRITE_TOOLS = ("Write", "Edit", "NotebookEdit", "Bash")
PATH_KEYS = ("file_path", "path", "notebook_path")

SCRIPT_PATH = os.path.realpath(__file__)
# Le répertoire « .claude » ENTIER est protégé en écriture (O4) : hooks,
# settings.json et toute cible sous .claude. HOOKS_DIR et SETTINGS_JSON
# restent définis — couverts a fortiori par CLAUDE_DIR — pour la
# lisibilité et les messages du registre.
CLAUDE_DIR = os.path.realpath(os.path.join(ROOT, ".claude"))
HOOKS_DIR = os.path.realpath(os.path.join(ROOT, ".claude", "hooks"))
SETTINGS_JSON = os.path.realpath(os.path.join(ROOT, ".claude", "settings.json"))


def _sous(chemin, prefixe):
    # Contenance par composants via commonpath — jamais par préfixe de chaîne
    # ("/atelier/b" n'est pas sous "/atelier/bc"). ValueError (chemins
    # incomparables, ex. deux lecteurs Windows) signifie hors racine.
    try:
        commun = os.path.commonpath((os.path.normcase(chemin), os.path.normcase(prefixe)))
    except ValueError:
        return False
    return commun == os.path.normcase(prefixe)


def _resoudre(chemin, cwd):
    # Backslash d'échappement : retrait avant résolution, sur POSIX uniquement.
    # Sur POSIX, ``\/etc/passwd`` est lu par Bash comme ``/etc/passwd`` :
    # sans retrait du backslash, le fragment brut n'est pas absolu et se
    # résout contre le cwd en ``<racine>/\/etc/passwd`` — DANS la racine,
    # donc autorisé à tort (contournement trivial). Sur Windows, le
    # backslash est le séparateur natif, pas un échappement : on le
    # conserve tel quel. Ce traitement couvre AUSSI les chemins venant de
    # file_path (pas seulement ceux extraits de Bash).
    if os.sep != chr(92):
        chemin = chemin.replace(chr(92), "")
    p = os.path.expanduser(chemin)
    if not os.path.isabs(p):
        p = os.path.join(cwd, p)
    return os.path.realpath(p)


def _ressemble_chemin(token):
    # Un token « ressemble à un chemin littéral » si et seulement si :
    # - il contient un séparateur : « / », le séparateur natif os.sep, ou
    #   la barre oblique inverse Windows — chr(92) plutôt qu'un littéral,
    #   pour ne dépendre d'aucun échappement dans la chaîne template ; OU
    # - il commence par « ~ » ; OU
    # - il commence par « . » : navigation (« . », « .. ») ou entrée
    #   cachée (« .claude », « .env ») — dans les deux cas un chemin
    #   littéral ; c'est ce qui capture la cible nue « .claude » de
    #   « rm -rf .claude » (O4), qu'une règle limitée à « .. »/« . »
    #   exacts laisserait passer. Un token non-chemin (commande, option)
    #   ne commence pratiquement jamais par « . » ; OU
    # - il débute par un lecteur Windows `X:` — avec séparateur (`C:\x`, `C:/x`)
    #   OU sans (`C:x`, chemin relatif au répertoire courant du lecteur, tout
    #   aussi valide sous Windows). Regex `^[A-Za-z]:`.
    # Un token SANS séparateur et sans préfixe « ~ »/« . » (ex. « cat »,
    # « rm », « -rf ») N'EST PAS un chemin : l'ajouter provoquerait des
    # faux positifs massifs sur les commandes et leurs options.
    # NOTE B-24d : les opérateurs shell font partie de la classe de
    # découpage de `_candidats`, ils n'apparaissent donc jamais dans un
    # fragment. Et même isolés ils ne ressembleraient pas à un chemin :
    # par construction ils ne contiennent pas de séparateur et ne
    # commencent ni par « ~ », ni par « . », ni par une lettre+« : ».
    if not token:
        return False
    if "/" in token or os.sep in token or chr(92) in token:
        return True
    if token.startswith("~"):
        return True
    if token.startswith("."):
        return True
    if re.match(r"^[A-Za-z]:", token):
        return True
    return False


def _candidats(tool_name, tool_input):
    trouves = []
    for cle in PATH_KEYS:
        valeur = tool_input.get(cle)
        if isinstance(valeur, str) and valeur:
            trouves.append(valeur)
    # Politique « chemins littéraux résolubles uniquement » : seuls les
    # fragments qui ressemblent à un chemin littéral sont contrôlés.
    #
    # B-24c/d — UN SEUL découpage de la commande brute sur la classe des
    # délimiteurs shell (``\s<>;|&()"'`$``), puis application du filtre
    # ``_ressemble_chemin``. Aucune tokenisation de type shell : shlex et
    # son repli re.split ont été rejetés par la revue scellée (chaque
    # tour trouvait un opérateur ou un séparateur oublié, signal de
    # conception). On n'extrait que des fragments LITTÉRAUX.
    #
    # B-24d tour 8 — collage d'un chemin à un préfixe d'option.
    # Le collage d'un chemin à un préfixe d'option suit les conventions
    # POSIX/GNU : séparateur ``=`` pour les options longues
    # (``--file=...``, ``--target-directory=...``) et agglutination
    # après ``-`` pour les options courtes (``-f...``, ``-o...``, etc.).
    # Deux règles bornées par ces conventions les couvrent :
    #
    # R1. Le signe ``=`` est ajouté à la classe des délimiteurs : il
    #     isole le préfixe d'option longue de son argument et couvre
    #     aussi les affectations de variables d'environnement en
    #     préfixe de commande (``VAR=/chemin cmd``).
    # R2. Un fragment qui COMMENCE par ``-`` est une option (convention
    #     universelle). On en extrait AUSSI le suffixe à partir du
    #     premier caractère ouvrant un chemin (``/``, ``~``, ``.``).
    #     Le fragment entier reste également candidat (les deux sont
    #     contrôlés) ; les doublons sont évités par l'ensemble ``vus``.
    #
    # Conséquences : un fragment contenant un séparateur et composé de
    # caractères hors délimiteurs ne peut PAS se cacher — s'il est dans
    # la commande, le motif le trouve, qu'il soit entre guillemets,
    # après une redirection, dans une substitution de commande, dans un
    # heredoc ou collé à un préfixe d'option. Le découpage NE LÈVE PAS
    # d'exception (re.split ne lève jamais sur des guillemets
    # déséquilibrés) : le chemin dégradé ``try/except`` disparaît, et
    # avec lui la porte de service qu'il constituait.
    #
    # Limite de périmètre inchangée : on n'interprète PAS le shell — pas
    # d'expansion de variable (``$HOME``, ``${X}``), pas de substitution
    # de commande (``$(...)``, ``...``), pas de globbing (``*``, ``?``,
    # ``[...]``), pas de compréhension des quotes imbriquées au-delà du
    # découpage. L'extraction porte sur des FRAGMENTS LITTÉRAUX.
    if tool_name == "Bash":
        commande = tool_input.get("command")
        if isinstance(commande, str):
            # bash supprime la continuation de ligne (backslash + saut
            # de ligne) avant tout découpage (mesure). Sans cette
            # normalisation, un chemin fragmenté par des continuations
            # échappe au contrôle. Normalisation appliquée partout, y
            # compris dans des guillemets simples où bash ne le ferait
            # pas — sur-détection assumée, fail-closed. Avec le retrait
            # du backslash dans _resoudre, cela couvre la liste
            # COMPLÈTE et MESURÉE des transformations pré-découpage
            # de bash.
            commande = commande.replace(chr(92) + "\n", "")
            DELIMITEURS = r"""[\s<>;|&()"'`$=]+"""
            fragments = [f for f in re.split(DELIMITEURS, commande) if f]
            # Règle R2 : un fragment commençant par ``-`` est une
            # option. On extrait le suffixe à partir du premier
            # caractère ouvrant un chemin (``/``, ``~``, ``.``). Le
            # fragment entier reste également candidat (les deux
            # contrôlent). Dédoublonnage par ``vus`` pour ne pas
            # accumuler la même cible sous deux formes.
            OUVRE_CHEMIN = re.compile(r"[/~.]")
            vus = set()
            for fragment in fragments:
                if _ressemble_chemin(fragment) and fragment not in vus:
                    trouves.append(fragment)
                    vus.add(fragment)
                if fragment.startswith("-"):
                    m = OUVRE_CHEMIN.search(fragment)
                    if m:
                        suffixe = fragment[m.start():]
                        if _ressemble_chemin(suffixe) and suffixe not in vus:
                            trouves.append(suffixe)
                            vus.add(suffixe)
    return trouves


def _exceptions():
    # tempfile.gettempdir() résolu, plus chaque ligne non vide du fichier
    # d'exceptions s'il existe. Un fichier illisible ne lève pas : on reste
    # étroit (fail-closed) plutôt que de s'autoriser ce qu'on ne vérifie pas.
    prefixes = [os.path.realpath(tempfile.gettempdir())]
    if os.path.exists(ALLOW_PATH):
        try:
            with open(ALLOW_PATH, "r", encoding="utf-8") as fh:
                lignes = fh.read().splitlines()
        except OSError:
            lignes = []
        for ligne in lignes:
            ligne = ligne.strip()
            if ligne:
                prefixes.append(os.path.realpath(os.path.expanduser(ligne)))
    return prefixes


def _auto_protege(tool_name, resolu):
    # Même DANS la racine, un outil d'écriture ne peut toucher ni ce
    # script, ni le répertoire « .claude » ENTIER — lui-même ou toute
    # cible sous lui (hooks, settings.json, etc.) : la garde qui se
    # laisse réécrire par le confiné est du théâtre. SCRIPT_PATH est
    # testé isolément car le script peut vivre HORS de .claude. Ce
    # contrôle précède les exceptions pour n'être jamais contourné par
    # le fichier d'exceptions.
    if tool_name not in WRITE_TOOLS:
        return False
    cible = os.path.normcase(resolu)
    if cible == os.path.normcase(SCRIPT_PATH):
        return True
    if cible == os.path.normcase(CLAUDE_DIR):
        return True
    if _sous(resolu, CLAUDE_DIR):
        return True
    return False

def _journaliser(tool, demande, resolu, cwd):
    # Réplique exacte du format de forgeai.core.registre (contrat de
    # compatibilité avec la vérification de chaîne du produit) : seq et
    # prev_hash dérivés du registre lu, ts UTC à la seconde, hash sha256 du
    # matériau canonique (entrée sans « hash », clés triées, JSON compact
    # UTF-8), ligne écrite en JSON compact trié suivie de « \n », flock
    # LOCK_EX quand fcntl existe, fsync avant de rendre.
    registre = os.environ.get("FORGEAI_REGISTRE", REGISTRE_DEFAUT)
    entries = []
    if os.path.exists(registre):
        with open(registre, "r", encoding="utf-8") as fh:
            for ligne in fh:
                ligne = ligne.strip()
                if ligne:
                    entries.append(json.loads(ligne))
    prev_hash = entries[-1]["hash"] if entries else GENESIS
    entry = {
        "seq": len(entries) + 1,
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "type": "guard_fs_denied",
        "actor": "guard-fs",
        "payload": {
            "tool": tool,
            "chemin_demande": demande,
            "chemin_resolu": resolu,
            "racine": ROOT,
            "cwd": cwd,
        },
        "prev_hash": prev_hash,
    }
    materiau = json.dumps(
        {k: v for k, v in entry.items() if k != "hash"},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    entry["hash"] = hashlib.sha256(materiau).hexdigest()
    ligne = json.dumps(entry, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    parent = os.path.dirname(registre)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(registre, "a", encoding="utf-8") as fh:
        if fcntl is not None:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            fh.seek(0, os.SEEK_END)
            fh.write(ligne + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        finally:
            if fcntl is not None:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def _refuser(tool, demande, resolu, cwd, motif):
    # Message d'UNE ligne : outil, chemin résolu refusé, racine. La
    # journalisation est tentée AVANT de sortir ; si elle échoue, la raison
    # est ajoutée au message — le refus tient TOUJOURS.
    message = "forgeai-guard-fs: REFUS outil={0} chemin={1} racine={2} motif={3}".format(
        tool, resolu, ROOT, motif
    )
    message = message.replace("\r", " ").replace("\n", " ")
    try:
        _journaliser(tool, demande, resolu, cwd)
    except Exception as exc:
        raison = str(exc).replace("\r", " ").replace("\n", " ")
        message += " (journalisation impossible: {0})".format(raison)
    sys.stderr.write(message + "\n")
    raise SystemExit(2)


def _refus_structurel(motif):
    # Refus avant extraction : pas de chemin résolu à journaliser.
    motif = motif.replace("\r", " ").replace("\n", " ")
    sys.stderr.write("forgeai-guard-fs: REFUS racine={0} motif={1}\n".format(ROOT, motif))
    raise SystemExit(2)


def _decider():
    try:
        brut = sys.stdin.read()
    except Exception as exc:
        _refus_structurel("stdin illisible: {0}".format(exc))
    try:
        payload = json.loads(brut)
    except ValueError as exc:
        _refus_structurel("JSON stdin invalide: {0}".format(exc))
    if not isinstance(payload, dict):
        _refus_structurel("charge JSON non-objet")
    tool_name = payload.get("tool_name")
    if not isinstance(tool_name, str) or not tool_name:
        _refus_structurel("tool_name absent ou invalide")
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        _refus_structurel("cwd absent ou invalide")
    # Fail-closed : un cwd relatif rendrait la résolution des chemins
    # relatifs ambiguë — refus structurel avant toute décision.
    if not os.path.isabs(cwd):
        _refus_structurel("cwd non absolu: {0}".format(cwd))
    tool_input = payload.get("tool_input")
    if tool_input is None:
        tool_input = {}
    if not isinstance(tool_input, dict):
        _refus_structurel("tool_input non-objet")
    # Le cwd est validé en propre, avant l'extraction des candidats : un
    # cwd non contraint transforme tout nom de fichier nu (sans séparateur,
    # donc jamais extrait comme candidat) en accès arbitraire — ce que le
    # contrôle des candidats ne peut pas rattraper par construction.
    cwd_resolu = os.path.realpath(cwd)
    exceptions = _exceptions()
    # Auto-protection AVANT confinement (comme pour les candidats) : un cwd
    # sous .claude est refusé même si .claude est sous ROOT — depuis ce
    # cwd, tout nom nu écrirait dans le répertoire de la garde. _sous
    # inclut l'égalité (commonpath d'un chemin avec lui-même).
    if tool_name in WRITE_TOOLS and _sous(cwd_resolu, CLAUDE_DIR):
        _refuser(tool_name, cwd, cwd_resolu, cwd, "cwd sous auto-protection")
    # Confinement : ROOT lui-même et tout descendant sont acceptés, ainsi
    # que tout cwd sous une exception explicite (tempdir, fichier allow).
    if not _sous(cwd_resolu, ROOT) and not any(
        _sous(cwd_resolu, prefixe) for prefixe in exceptions
    ):
        _refuser(tool_name, cwd, cwd_resolu, cwd, "cwd hors racine")
    candidats = _candidats(tool_name, tool_input)
    if not candidats:
        return  # Aucun chemin candidat : AUTORISER (exit 0).
    for demande in candidats:
        resolu = _resoudre(demande, cwd_resolu)
        if _auto_protege(tool_name, resolu):
            _refuser(tool_name, demande, resolu, cwd, "auto-protection")
        if any(_sous(resolu, prefixe) for prefixe in exceptions):
            continue  # Candidat dans une exception explicite : autorisé.
        if not _sous(resolu, ROOT):
            _refuser(tool_name, demande, resolu, cwd, "hors racine")
    # Tous les candidats sont conformes : AUTORISER (exit 0).


def main():
    # Fail-closed global : TOUTE exception interne devient un REFUS exit 2
    # avec la raison sur stderr. SystemExit (autorisation implicite exit 0 ou
    # refus explicite exit 2) est laissé intact.
    try:
        _decider()
    except SystemExit:
        raise
    except Exception as exc:
        raison = str(exc).replace("\r", " ").replace("\n", " ")
        sys.stderr.write(
            "forgeai-guard-fs: REFUS racine={0} motif=erreur interne: {1}\n".format(ROOT, raison)
        )
        raise SystemExit(2)


if __name__ == "__main__":
    main()
'''


def _chemin_embarque(chemin: str | os.PathLike[str]) -> str:
    """expanduser puis absolu, au moment de la génération.

    Un chemin relatif embarqué dans le script généré serait résolu contre un
    cwd imprévisible à l'exécution du hook — même piège que la racine mobile,
    même remède : figer à la génération.
    """
    return os.path.abspath(os.path.expanduser(os.fspath(chemin)))


def generate_guard_fs(
    workspace_root: str | os.PathLike[str],
    *,
    registre_path: str | os.PathLike[str] | None = None,
    allow_path: str | os.PathLike[str] | None = None,
) -> str:
    """Retourne le source complet de la garde, substitutions faites.

    ``workspace_root`` est figé par ``os.path.realpath`` AU MOMENT DE LA
    GÉNÉRATION (décision B-24 : la racine ne doit jamais être dérivée du cwd
    à l'exécution). Une racine inexistante lève ``IDEError`` : générer une
    garde pour une racine fantôme est un piège silencieux.

    ``registre_path`` (défaut ``~/.forgeai/Registres/mission.jsonl``) et
    ``allow_path`` (défaut ``~/.forgeai/guard-fs.allow``) sont expanduser à la
    génération. Les trois chemins sont injectés via ``repr`` — jamais
    d'interpolation nue dans du code généré.
    """
    root = os.path.realpath(os.fspath(workspace_root))
    if not os.path.exists(root):
        raise IDEError(f"generate_guard_fs: racine de workspace inexistante : {root}")
    registre = (
        _chemin_embarque(registre_path)
        if registre_path is not None
        else _chemin_embarque("~/.forgeai/Registres/mission.jsonl")
    )
    allow = (
        _chemin_embarque(allow_path)
        if allow_path is not None
        else _chemin_embarque("~/.forgeai/guard-fs.allow")
    )
    script = _SCRIPT_TEMPLATE
    for jeton, valeur in (
        ("__FORGEAI_ROOT__", root),
        ("__FORGEAI_REGISTRE__", registre),
        ("__FORGEAI_ALLOW__", allow),
    ):
        if jeton not in script:
            raise IDEError(f"generate_guard_fs: emplacement {jeton} absent du template")
        script = script.replace(jeton, repr(valeur))
    return script


def install_guard_fs(
    dest_dir: str | os.PathLike[str],
    *,
    python_executable: str | None = None,
) -> tuple[Path, HookSpec]:
    """Écrit la garde dans ``<dest_dir>/.claude/hooks/`` et retourne son hook.

    Le script est écrit en UTF-8, mode 0o755, à
    ``<dest_dir>/.claude/hooks/forgeai_guard_fs.py`` (répertoires parents
    créés). La commande du hook épingle l'interpréteur ABSOLU capturé au
    bootstrap (``sys.executable`` par défaut — jamais « python » nu, le PATH
    n'est pas garanti chez l'utilisateur) et le chemin absolu du script.

    Retourne ``(chemin_absolu_du_script, HookSpec PreToolUse matcher "*")``.
    """
    dest = Path(dest_dir)
    script_path = (dest / ".claude" / "hooks" / "forgeai_guard_fs.py").resolve()
    contenu = generate_guard_fs(dest)
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(contenu, encoding="utf-8")
    script_path.chmod(0o755)
    python = python_executable if python_executable is not None else sys.executable
    hook = HookSpec(
        event="PreToolUse",
        command=f'"{python}" "{script_path}"',
        matcher="*",
    )
    return script_path, hook
