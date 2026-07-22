"""Story S7 — vue cluster agrégée : « quel vendor GPU sur quels nœuds » depuis les sondes NodeProbe.
Comble le gap : aucun composant ne consolidait les NodeProbe multi-nœuds en une vue cluster.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from forgeai.cluster import cluster_view, node_vendors, read_probes


def _probe(host, profile, gpus, backends):
    return {"node_host": host, "profile": profile, "backends": backends,
            "hardware": {"gpus": gpus}}


def test_node_vendors_distincts_ordonnes():
    hw = {"gpus": [{"vendor": "amd"}, {"vendor": "amd"}, {"vendor": "nvidia"}]}
    assert node_vendors(hw) == ["amd", "nvidia"]  # dédupliqué, ordre de 1re apparition
    assert node_vendors({}) == []


def test_cluster_view_quel_vendor_ou():
    probes = [
        _probe("pc-amd", "minimal-gpu-rocm", [{"vendor": "amd"}, {"vendor": "amd"}], ["rocm"]),
        _probe("pc-mix", "minimal-gpu-cuda", [{"vendor": "nvidia"}, {"vendor": "amd"}], ["cuda"]),
        _probe("pc-cpu", "minimal-cpu", [], ["cpu"]),
    ]
    view = cluster_view(probes)
    assert view["vendors"]["amd"] == ["pc-amd", "pc-mix"]
    assert view["vendors"]["nvidia"] == ["pc-mix"]
    assert "cpu" not in view["vendors"]  # pas de GPU cpu-only
    pc_mix = next(n for n in view["nodes"] if n["node"] == "pc-mix")
    assert pc_mix["vendors"] == ["nvidia", "amd"] and pc_mix["profile"] == "minimal-gpu-cuda"


def test_read_probes_garde_la_plus_recente(tmp_path):
    reg = tmp_path / "mission.jsonl"
    lignes = [
        {"type": "story_done", "payload": {"story": "X"}},  # ignoré
        {"type": "node_hardware", "payload": _probe("pc1", "minimal-cpu", [], ["cpu"])},
        {"type": "node_hardware",  # pc1 re-sondé plus tard : écrase
         "payload": _probe("pc1", "minimal-gpu-rocm", [{"vendor": "amd"}], ["rocm"])},
    ]
    contenu = "\n".join(json.dumps(x) for x in lignes) + "\nligne-corrompue\n"
    reg.write_text(contenu, encoding="utf-8")
    probes = read_probes(reg)
    assert len(probes) == 1  # une seule entrée par node_host (la plus récente)
    assert probes[0]["profile"] == "minimal-gpu-rocm"
    assert read_probes(tmp_path / "absent.jsonl") == []


def test_read_puis_agrege(tmp_path):
    reg = tmp_path / "r.jsonl"
    reg.write_text(json.dumps(
        {"type": "node_hardware",
         "payload": _probe("n1", "minimal-gpu-rocm", [{"vendor": "amd"}], ["rocm"])}) + "\n",
        encoding="utf-8")
    view = cluster_view(read_probes(reg))
    assert view["vendors"] == {"amd": ["n1"]}


def test_cli_node_cluster_en_process(tmp_path, capsys):
    """Couvre le handler cli.py EN PROCESS (coverage) : `node cluster` affiche vendor->nœuds."""
    import forgeai.cli as cli
    reg = tmp_path / "r.jsonl"
    reg.write_text(json.dumps({
        "type": "node_hardware",
        "payload": _probe("pc-amd", "minimal-gpu-rocm", [{"vendor": "amd"}], ["rocm"])}) + "\n",
        encoding="utf-8")
    rc = cli.main(["node", "cluster", "--registre", str(reg)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "pc-amd" in out and "amd -> pc-amd" in out
