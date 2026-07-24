"""S3 (#144) — sidecar de re-unseal openbao dans le Deployment k3s + logique du script.

Deux niveaux de preuve : (1) le manifeste rendu est un YAML valide avec 2 conteneurs dont le sidecar
`openbao-unsealer` (script + montage RO de la clé) et le volume Secret des clés ; (2) le script
`_UNSEAL_SCRIPT` DESCELLE réellement le coffre (faux `bao` : scellé -> descellé).
"""
from __future__ import annotations

import os
import stat
import subprocess
import sys

import yaml
from forgeai.core.models import ServiceSpec
from forgeai.renderers.k3s import _UNSEAL_SCRIPT, _deployment

_OPENBAO = ServiceSpec(
    name="openbao",
    image="openbao/openbao:2.6.0",
    host_port=8200,
    container_port=8200,
    healthcheck_url="http://127.0.0.1:8200/v1/sys/health",
    volumes=[
        "forgeai-openbao-data:/openbao/file",
        "./openbao.hcl:/openbao/config/openbao.hcl:ro",
    ],
    command=["server", "-config=/openbao/config/openbao.hcl"],
    env={},
)
_REDIS = ServiceSpec(
    name="redis", image="redis:7-alpine", host_port=6379, container_port=6379,
    healthcheck_url="", volumes=["forgeai-redis-data:/data"], env={},
)


def _openbao_deployment() -> dict:
    manifest = _deployment(_OPENBAO, config_files={"openbao.hcl": 'storage "file" {}\n'})
    docs = [d for d in yaml.safe_load_all(manifest) if d]
    return next(d for d in docs if d.get("kind") == "Deployment")


def test_manifest_yaml_valide_2_conteneurs() -> None:
    dep = _openbao_deployment()
    conts = dep["spec"]["template"]["spec"]["containers"]
    names = [c["name"] for c in conts]
    assert names == ["openbao", "openbao-unsealer"], names


def test_sidecar_script_et_montage() -> None:
    dep = _openbao_deployment()
    conts = dep["spec"]["template"]["spec"]["containers"]
    side = next(c for c in conts if c["name"] == "openbao-unsealer")
    assert side["image"] == _OPENBAO.image  # même image openbao (bao présent)
    script = side["command"][2]
    assert "bao status" in script
    assert "operator unseal" in script
    assert "/keys/unseal_key" in script
    mount = side["volumeMounts"][0]
    assert mount["name"] == "openbao-keys" and mount["mountPath"] == "/keys"
    assert mount["readOnly"] is True


def test_volume_secret_cles_optional_item_unseal_only() -> None:
    dep = _openbao_deployment()
    vols = dep["spec"]["template"]["spec"]["volumes"]
    kv = next(v for v in vols if v["name"] == "openbao-keys")
    assert kv["secret"]["secretName"] == "forgeai-openbao-keys"
    assert kv["secret"]["optional"] is True
    # seul unseal_key est exposé (jamais le root token)
    assert kv["secret"]["items"] == [{"key": "unseal_key", "path": "unseal_key"}]


def test_conteneur_principal_ne_monte_pas_les_cles() -> None:
    dep = _openbao_deployment()
    main = next(
        c for c in dep["spec"]["template"]["spec"]["containers"] if c["name"] == "openbao"
    )
    assert all(m["name"] != "openbao-keys" for m in main.get("volumeMounts", []))


def test_non_regression_service_sans_sidecar() -> None:
    manifest = _deployment(_REDIS)
    dep = next(d for d in yaml.safe_load_all(manifest) if d and d.get("kind") == "Deployment")
    conts = dep["spec"]["template"]["spec"]["containers"]
    assert [c["name"] for c in conts] == ["redis"]
    assert "openbao-unsealer" not in manifest


def test_script_descelle_reellement(tmp_path) -> None:
    """PREUVE LOGIQUE : le script _UNSEAL_SCRIPT appelle `bao operator unseal` avec la clé montée
    quand le coffre est scellé (faux `bao` simulant scellé -> descellé)."""
    bindir = tmp_path / "bin"
    keys = tmp_path / "keys"
    bindir.mkdir()
    keys.mkdir()
    (keys / "unseal_key").write_text("MA-CLE-UNSEAL-FACTICE", encoding="utf-8")

    fake_bao = bindir / "bao"
    fake_bao.write_text(
        "#!/bin/sh\n"
        'STATE="$0.state"\n'
        '[ -f "$STATE" ] || echo sealed > "$STATE"\n'
        'case "$1" in\n'
        "  status)\n"
        '    if [ "$(cat "$STATE")" = unsealed ]; then\n'
        '      echo "Initialized     true"; echo "Sealed          false"\n'
        "    else\n"
        '      echo "Initialized     true"; echo "Sealed          true"\n'
        "    fi ;;\n"
        "  operator)\n"
        '    if [ "$2" = unseal ]; then\n'
        '      echo "unseal_called key=$4" >> "$0.trace"; echo unsealed > "$STATE"\n'
        "    fi ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    fake_bao.chmod(fake_bao.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    # Le script cible /keys/unseal_key en dur : on réoriente vers notre fichier de test.
    run_script = _UNSEAL_SCRIPT.replace("/keys/unseal_key", str(keys / "unseal_key"))

    env = dict(os.environ)
    env["PATH"] = f"{bindir}{os.pathsep}{env['PATH']}"
    env["UNSEAL_MAX_ITERS"] = "4"
    env["BAO_ADDR"] = "http://127.0.0.1:8200"
    proc = subprocess.run(
        ["sh", "-c", run_script], env=env, capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    trace = fake_bao.with_suffix(".trace")
    assert trace.exists(), "bao operator unseal n'a jamais été appelé"
    assert "unseal_called key=MA-CLE-UNSEAL-FACTICE" in trace.read_text(encoding="utf-8")


def test_script_ne_contient_pas_jq_ni_secret_en_clair() -> None:
    # sans jq (image minimale) ; la clé n'est JAMAIS echo'ée (seuls des messages d'état).
    assert "jq" not in _UNSEAL_SCRIPT
    for line in _UNSEAL_SCRIPT.splitlines():
        if line.lstrip().startswith("echo"):
            assert "unseal_key" not in line and "$(cat" not in line and "$key" not in line, line


if __name__ == "__main__":  # pragma: no cover
    sys.exit(subprocess.call([sys.executable, "-m", "pytest", "-q", __file__]))
