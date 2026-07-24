#!/usr/bin/env python3
"""FAI-0005 S6 — PREUVE e2e RÉELLE : openbao PRODUCTION déployé en Docker via le VRAI code ForgeAI.

Déploie openbao (production : storage fichier, coffre scellé, disable_mlock) + son `openbao-unsealer`
via `render_compose` (le renderer S4 réel) puis exécute le flux de déploiement `openbao_flow` (S5) et
PROUVE, sans aucun mock :
  1. AMORÇAGE : coffre scellé -> `initialize_openbao` -> descellé + token applicatif SCOPÉ (≠ root) ;
  2. ISOLATION du root : le répertoire monté à l'unsealer ne contient QUE `unseal_key`, jamais le root ;
  3. KV round-trip : master key écrite au coffre (token applicatif) puis relue à l'identique ;
  4. POSTURE mlock : disable_mlock (openbao.hcl) + AUCUNE capability IPC_LOCK (inopérante en non-root :
     mlock ne verrouillerait rien, CapEff=0) + bao en non-root + démarrage sans erreur de verrouillage
     mémoire — moindre privilège ; contrôle compensatoire = swap-off au nœud (prérequis opérateur) ;
  5. SURVIE AU RESTART : `docker restart openbao` -> le coffre repart SCELLÉ -> le SIDECAR `openbao-unsealer`
     (S3/S4) le re-descelle AUTOMATIQUEMENT (aucune intervention) -> la master key est TOUJOURS lisible
     (storage fichier persistant).

Aucun faux succès : toute étape qui ne se prouve pas fait échouer le script (exit != 0). Idempotent
(teardown en préambule et en fin). Confiné : réseau/volumes docker dédiés au projet, nettoyés.

Usage : PYTHONPATH=src python3 scripts/proof/prove_openbao_prod.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from tempfile import mkdtemp

from forgeai.core.models import DeploymentPlan, RenderTarget, ServiceSpec
from forgeai.deploy.openbao_flow import FileKeyStore, FileSecretStore, initialize_openbao, prepare_key_store
from forgeai.renderers.compose import render_compose
from forgeai.secrets import vault

PROJECT = "forgeai-openbao-s6-proof"
HOST_PORT = 18220
BAO = f"http://127.0.0.1:{HOST_PORT}"
IMAGE = "openbao/openbao:2.6.0"
KV_PATH = "forgeai/litellm"
MASTER_KEY = "sk-preuve-s6-" + "0" * 8  # gitleaks:allow — valeur factice de preuve, jamais un vrai secret


def _sh(args: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=180, **kw)


def _compose(workdir: Path, *args: str) -> subprocess.CompletedProcess:
    return _sh(["docker", "compose", "-p", PROJECT, "-f", str(workdir / "docker-compose.yml"), *args])


def _teardown(workdir: Path | None) -> None:
    if workdir and (workdir / "docker-compose.yml").exists():
        _compose(workdir, "down", "-v", "--remove-orphans")


def _reachable(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as r:
            return r.status > 0
    except urllib.error.HTTPError:
        return True  # une réponse HTTP (même 5xx scellé) = process up
    except (urllib.error.URLError, OSError, ValueError):
        return False


def _seal_status() -> dict:
    with urllib.request.urlopen(f"{BAO}/v1/sys/seal-status", timeout=3) as r:
        return json.loads(r.read().decode("utf-8"))


def _ok(msg: str) -> None:
    print(f"  PROUVÉ : {msg}")


def _fail(msg: str) -> None:
    print(f"  ÉCHEC : {msg}")
    raise SystemExit(1)


def main() -> int:
    workdir = Path(mkdtemp(prefix="forgeai-s6-"))
    print(f"== FAI-0005 S6 — preuve e2e openbao PRODUCTION (workdir {workdir}) ==")
    _teardown(workdir)  # au cas où un run précédent traîne
    try:
        # --- Rendu du VRAI manifeste compose (renderer S4) -----------------------------------------
        openbao = ServiceSpec(
            name="openbao", image=IMAGE, host_port=HOST_PORT, container_port=8200,
            healthcheck_url="http://127.0.0.1:8200/v1/sys/health",
            volumes=("forgeai-openbao-data:/openbao/file",
                     "./openbao.hcl:/openbao/config/openbao.hcl:ro"),
            command=("server", "-config=/openbao/config/openbao.hcl"),
        )
        plan = DeploymentPlan(plan_id="s6", profile="minimal-cpu", target=RenderTarget.COMPOSE,
                              services=(openbao,), model="m", embed_model="e")
        (workdir / "docker-compose.yml").write_text(render_compose(plan), encoding="utf-8")
        (workdir / "openbao.hcl").write_text(
            (Path(__file__).resolve().parents[2] / "src" / "forgeai" / "data" / "openbao.hcl")
            .read_text(encoding="utf-8"), encoding="utf-8")
        (workdir / ".env").write_text("", encoding="utf-8")
        keys_dir = prepare_key_store(workdir / "openbao-keys")
        # le rendu doit bien porter le service compagnon (S4)
        manifest = (workdir / "docker-compose.yml").read_text(encoding="utf-8")
        if "openbao-unsealer" not in manifest:
            _fail("le manifeste rendu ne contient pas openbao-unsealer")
        _ok("manifeste compose rendu par le renderer réel (openbao + openbao-unsealer)")

        # --- Démarrage openbao + unsealer (coffre scellé au boot) ----------------------------------
        up = _compose(workdir, "up", "-d")
        if up.returncode != 0:
            _fail(f"docker compose up : {up.stderr[-800:]}")
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline and not _reachable(f"{BAO}/v1/sys/health"):
            time.sleep(2)
        if not _reachable(f"{BAO}/v1/sys/health"):
            _fail("openbao injoignable")
        st = _seal_status()
        if st.get("initialized") is not False:
            _fail(f"openbao devrait démarrer NON initialisé : {st}")
        _ok(f"openbao démarre en PRODUCTION, scellé et non initialisé (initialized={st.get('initialized')})")

        # --- 1+2. Amorçage : init/unseal + token scopé, root isolé ---------------------------------
        key_store = FileKeyStore(keys_dir, workdir / "secrets" / "openbao_root")
        secret_store = FileSecretStore(workdir / "secrets" / "openbao_app_token.json")
        app_token = initialize_openbao(BAO, key_store, secret_store)
        root_token = key_store.read()["root_token"]
        if not app_token or app_token == root_token:
            _fail("le token applicatif doit être scopé (≠ root)")
        # lookup-self : le token porte la policy forgeai-app, PAS root
        req = urllib.request.Request(f"{BAO}/v1/auth/token/lookup-self")
        req.add_header("X-Vault-Token", app_token)
        with urllib.request.urlopen(req, timeout=5) as r:
            policies = json.loads(r.read().decode("utf-8")).get("data", {}).get("policies", [])
        if "forgeai-app" not in policies or "root" in policies:
            _fail(f"le token applicatif doit porter forgeai-app et non root : {policies}")
        _ok(f"token applicatif SCOPÉ émis (policies={policies}, ≠ root)")
        keys_dir_entries = sorted(p.name for p in keys_dir.iterdir())
        if keys_dir_entries != ["unseal_key"]:
            _fail(f"le répertoire monté à l'unsealer doit contenir SEULEMENT unseal_key : {keys_dir_entries}")
        _ok("isolation du root : le volume de l'unsealer ne contient que unseal_key (jamais le root)")

        if _seal_status().get("sealed") is not False:
            _fail("openbao devrait être descellé après l'amorçage")
        _ok("coffre DESCELLÉ après amorçage")

        # --- 3. KV round-trip avec le token applicatif ---------------------------------------------
        vault.store(BAO, app_token, KV_PATH, {"master_key": MASTER_KEY})
        relu = vault.read(BAO, app_token, KV_PATH).get("master_key")
        if relu != MASTER_KEY:
            _fail("la master key relue diffère de l'écrite")
        _ok("KV round-trip : master key écrite puis relue à l'identique (token applicatif)")

        # --- 3b. RENEW-SELF : le token périodique se renouvelle lui-même (fix bug-3 exercé RUNTIME) ---
        # Prouve que la policy forgeai-app accorde bien renew-self au token no_default_policy : sans les
        # capacités self ajoutées, ce serait 403 -> le token 720h expirerait silencieusement. Utilise
        # le VRAI `vault.renew_self` (S5), le mécanisme de perpétuité du token sans root.
        ttl = vault.renew_self(BAO, app_token)
        if ttl <= 0:
            _fail(f"renew-self n'a pas renouvelé le token (TTL={ttl}) — token périodique non perpétuable")
        _ok(f"renew-self : le token périodique se renouvelle lui-même (TTL={ttl}s) — perpétuel sans root")

        # --- 4. POSTURE mlock : disable_mlock (conteneur) + démarrage propre, moindre privilège -----
        # Le rendu compose NE demande PAS de capability IPC_LOCK (inopérante en non-root -> mlock ne
        # verrouille rien : CapEff=0, VmLck=0 même avec cap_add -> prétendre « mlock actif » serait un
        # FAUX). Posture correcte, standard conteneur (défaut du chart Helm Vault) : disable_mlock +
        # swap-off au nœud (contrôle compensatoire opérateur documenté).
        if "cap_add" in manifest or "IPC_LOCK" in manifest:
            _fail("le manifeste rendu accorde une capability IPC_LOCK inutile (mlock inopérant en non-root)")
        hcl_text = (Path(__file__).resolve().parents[2] / "src" / "forgeai" / "data" / "openbao.hcl") \
            .read_text(encoding="utf-8")
        if "disable_mlock = true" not in hcl_text:
            _fail("openbao.hcl doit porter disable_mlock = true (posture conteneur)")
        # openbao ne doit JAMAIS échouer sur un verrouillage mémoire (avec disable_mlock il n'essaie pas)
        logs = _compose(workdir, "logs", "openbao").stdout.lower()
        if "failed to lock memory" in logs or "cannot allocate memory" in logs:
            _fail("openbao a échoué à verrouiller la mémoire (mlock demandé alors qu'inopérant)")
        # le process bao tourne bien en NON-root (moindre privilège), sans capability effective
        uid_out = _compose(workdir, "exec", "-T", "openbao", "sh", "-c",
                           "for p in /proc/[0-9]*; do grep -q '^bao' $p/cmdline 2>/dev/null && "
                           "grep -H '^Uid' $p/status; done").stdout
        if "\t0\t" in uid_out or "Uid:\t0" in uid_out:
            _fail(f"openbao ne devrait PAS tourner en root : {uid_out.strip()!r}")
        _ok("posture mlock : disable_mlock + aucune capability privilégiée + bao en non-root, "
            "démarrage sans erreur de verrouillage mémoire (swap-off = prérequis opérateur documenté)")

        # --- 5. SURVIE AU RESTART : re-unseal AUTOMATIQUE par le sidecar ---------------------------
        restart = _compose(workdir, "restart", "openbao")
        if restart.returncode != 0:
            _fail(f"docker compose restart openbao : {restart.stderr[-500:]}")
        # openbao repart SCELLÉ ; on vérifie d'abord le scellage transitoire puis le re-unseal AUTO
        deadline = time.monotonic() + 30
        saw_sealed = False
        while time.monotonic() < deadline:
            try:
                if _seal_status().get("sealed") is True:
                    saw_sealed = True
                    break
            except (urllib.error.URLError, OSError, ValueError):
                pass
            time.sleep(0.5)
        # re-unseal automatique par le sidecar (aucune action de notre part) — deadline généreuse
        deadline = time.monotonic() + 180
        reunsealed = False
        while time.monotonic() < deadline:
            try:
                if _seal_status().get("sealed") is False:
                    reunsealed = True
                    break
            except (urllib.error.URLError, OSError, ValueError):
                pass
            time.sleep(2)
        if not saw_sealed:
            _fail("openbao aurait dû repartir SCELLÉ après restart (storage fichier) — re-seal non observé, "
                  "la preuve de re-unseal serait vacante")
        if not reunsealed:
            _fail("le sidecar openbao-unsealer n'a pas re-descellé le coffre après restart")
        _ok("survie au restart : coffre re-SCELLÉ au reboot PUIS re-descellé AUTOMATIQUEMENT par le sidecar")

        # data persistée + toujours lisible avec le même token applicatif
        relu2 = vault.read(BAO, app_token, KV_PATH).get("master_key")
        if relu2 != MASTER_KEY:
            _fail("la master key n'a pas survécu au restart (storage non persistant ?)")
        _ok("la master key est TOUJOURS lisible après restart (storage fichier persistant + token valide)")

        print("\n== TOUTES LES PREUVES PASSENT — openbao PRODUCTION e2e prouvé ==")
        return 0
    finally:
        _teardown(workdir)


if __name__ == "__main__":
    sys.exit(main())
