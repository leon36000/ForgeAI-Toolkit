# Story S7 — vue cluster agrégée (« quel vendor GPU sur quels nœuds »)

## Gap comblé (recon gap #5 détection)
probe_remote_node écrit un NodeProbe par nœud au registre (type 'node_hardware'), mais aucun
composant ne consolidait l'ensemble en une vue cluster pour piloter un déploiement multi-nœud
vendor-aware. S7 fournit cette agrégation.

## Changements
- Nouveau module `forgeai/cluster.py` (PUR) : node_vendors, cluster_view (nodes[] + index inversé
  vendor->[nœuds]), read_probes (lit 'node_hardware' du registre JSONL, dernière par node_host,
  lignes corrompues ignorées).
- CLI `forgeai node cluster --registre <path>` : affiche le résumé par nœud + « quel vendor où ».

## Critères (testés)
1. node_vendors : vendors distincts ordonnés ; {} -> [].
2. cluster_view : vendor->nœuds correct (amd sur 2 nœuds, nvidia sur 1, cpu-only absent).
3. read_probes : ignore les non-'node_hardware', garde la plus récente par nœud, fichier absent -> [].
4. CLI node cluster (EN PROCESS, coverage) : affiche 'pc-amd' + 'amd -> pc-amd', exit 0.

Codeur : orchestrateur.
## Diff intégral (origin/main..HEAD)
```diff
diff --git a/src/forgeai/cli.py b/src/forgeai/cli.py
index dda5f48..ab46e4e 100644
--- a/src/forgeai/cli.py
+++ b/src/forgeai/cli.py
@@ -565,6 +565,22 @@ def _node_probe(args: argparse.Namespace) -> int:
     return 0
 
 
+def _node_cluster(args: argparse.Namespace) -> int:
+    # S7 : vue cluster agrégée « quel vendor GPU sur quels nœuds » depuis les sondes du registre.
+    from forgeai.cluster import cluster_view, read_probes
+    view = cluster_view(read_probes(args.registre))
+    if not view["nodes"]:
+        print("[forgeai] vue cluster : aucune sonde node_hardware au registre")
+        return 0
+    print("[forgeai] vue cluster — vendors GPU par nœud :")
+    for n in view["nodes"]:
+        print(f"  {n['node']} : profil {n['profile']} | vendors {', '.join(n['vendors']) or 'aucun'}")
+    print("[forgeai] quel vendor où :")
+    for vendor, hosts in sorted(view["vendors"].items()):
+        print(f"  {vendor} -> {', '.join(hosts)}")
+    return 0
+
+
 def _node_tailscale(args: argparse.Namespace) -> int:
     from forgeai.network.tailscale import render_node_network, TailscaleError
     from forgeai.network.bootstrap import BootstrapError
@@ -1193,6 +1209,10 @@ def main(argv: list[str] | None = None) -> int:
                                  help="clé privée SSH (requis si distant)")
     p_node_discover.add_argument("--registre", default=str(DEFAULT_REGISTRE))
     p_node_discover.set_defaults(func=_node_discover)
+    p_node_cluster = node_sub.add_parser(
+        "cluster", help="vue cluster agrégée : quel vendor GPU sur quels nœuds (S7)")
+    p_node_cluster.add_argument("--registre", default=str(DEFAULT_REGISTRE))
+    p_node_cluster.set_defaults(func=_node_cluster)
 
     p_wiz = sub.add_parser("wizard", help="wizard bout-en-bout")
     p_wiz.add_argument("--ci", action="store_true", required=True)
diff --git a/src/forgeai/cluster.py b/src/forgeai/cluster.py
new file mode 100644
index 0000000..5469302
--- /dev/null
+++ b/src/forgeai/cluster.py
@@ -0,0 +1,61 @@
+"""Story S7 — vue cluster agrégée : consolide les sondes NodeProbe (registre type `node_hardware`)
+en « quel vendor GPU sur quels nœuds », pour un déploiement multi-nœud vendor-aware.
+Fonctions pures + lecteur registre.
+"""
+from __future__ import annotations
+
+import json
+from pathlib import Path
+
+
+def node_vendors(hardware: dict) -> list[str]:
+    """Vendors GPU DISTINCTS d'un nœud, dans l'ordre de première apparition (hardware['gpus'])."""
+    seen: list[str] = []
+    for gpu in hardware.get("gpus", []):
+        vendor = gpu.get("vendor")
+        if vendor and vendor not in seen:
+            seen.append(vendor)
+    return seen
+
+
+def cluster_view(probes: list[dict]) -> dict:
+    """Agrège une liste de sondes {node_host, profile, backends, hardware} en vue cluster :
+    - `nodes` : un résumé par nœud (node, profile, vendors, backends) ;
+    - `vendors` : index inversé vendor -> [nœuds] (le « quel vendor où »)."""
+    nodes: list[dict] = []
+    vendors: dict[str, list[str]] = {}
+    for probe in probes:
+        host = probe.get("node_host", "?")
+        vs = node_vendors(probe.get("hardware", {}))
+        nodes.append({
+            "node": host,
+            "profile": probe.get("profile", ""),
+            "vendors": vs,
+            "backends": list(probe.get("backends", [])),
+        })
+        for vendor in vs:
+            bucket = vendors.setdefault(vendor, [])
+            if host not in bucket:
+                bucket.append(host)
+    return {"nodes": nodes, "vendors": vendors}
+
+
+def read_probes(registre_path: str | Path) -> list[dict]:
+    """Lit les sondes `node_hardware` d'un registre JSONL ; garde la PLUS RÉCENTE par node_host
+    (le registre est chronologique : la dernière écrase). Lignes illisibles ignorées."""
+    latest: dict[str, dict] = {}
+    path = Path(registre_path)
+    if not path.exists():
+        return []
+    for line in path.read_text(encoding="utf-8").splitlines():
+        line = line.strip()
+        if not line:
+            continue
+        try:
+            entry = json.loads(line)
+        except json.JSONDecodeError:
+            continue
+        if entry.get("type") == "node_hardware":
+            payload = entry.get("payload", {})
+            latest[payload.get("node_host")] = payload
+    return list(latest.values())
diff --git a/tests/test_cluster_view.py b/tests/test_cluster_view.py
new file mode 100644
index 0000000..1026244
--- /dev/null
+++ b/tests/test_cluster_view.py
@@ -0,0 +1,75 @@
+"""Story S7 — vue cluster agrégée : « quel vendor GPU sur quels nœuds » depuis les sondes NodeProbe.
+Comble le gap : aucun composant ne consolidait les NodeProbe multi-nœuds en une vue cluster.
+"""
+import json
+import sys
+from pathlib import Path
+
+sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
+
+from forgeai.cluster import cluster_view, node_vendors, read_probes
+
+
+def _probe(host, profile, gpus, backends):
+    return {"node_host": host, "profile": profile, "backends": backends,
+            "hardware": {"gpus": gpus}}
+
+
+def test_node_vendors_distincts_ordonnes():
+    hw = {"gpus": [{"vendor": "amd"}, {"vendor": "amd"}, {"vendor": "nvidia"}]}
+    assert node_vendors(hw) == ["amd", "nvidia"]  # dédupliqué, ordre de 1re apparition
+    assert node_vendors({}) == []
+
+
+def test_cluster_view_quel_vendor_ou():
+    probes = [
+        _probe("pc-amd", "minimal-gpu-rocm", [{"vendor": "amd"}, {"vendor": "amd"}], ["rocm"]),
+        _probe("pc-mix", "minimal-gpu-cuda", [{"vendor": "nvidia"}, {"vendor": "amd"}], ["cuda"]),
+        _probe("pc-cpu", "minimal-cpu", [], ["cpu"]),
+    ]
+    view = cluster_view(probes)
+    assert view["vendors"]["amd"] == ["pc-amd", "pc-mix"]
+    assert view["vendors"]["nvidia"] == ["pc-mix"]
+    assert "cpu" not in view["vendors"]  # pas de GPU cpu-only
+    pc_mix = next(n for n in view["nodes"] if n["node"] == "pc-mix")
+    assert pc_mix["vendors"] == ["nvidia", "amd"] and pc_mix["profile"] == "minimal-gpu-cuda"
+
+
+def test_read_probes_garde_la_plus_recente(tmp_path):
+    reg = tmp_path / "mission.jsonl"
+    lignes = [
+        {"type": "story_done", "payload": {"story": "X"}},  # ignoré
+        {"type": "node_hardware", "payload": _probe("pc1", "minimal-cpu", [], ["cpu"])},
+        {"type": "node_hardware",  # pc1 re-sondé plus tard : écrase
+         "payload": _probe("pc1", "minimal-gpu-rocm", [{"vendor": "amd"}], ["rocm"])},
+    ]
+    contenu = "\n".join(json.dumps(x) for x in lignes) + "\nligne-corrompue\n"
+    reg.write_text(contenu, encoding="utf-8")
+    probes = read_probes(reg)
+    assert len(probes) == 1  # une seule entrée par node_host (la plus récente)
+    assert probes[0]["profile"] == "minimal-gpu-rocm"
+    assert read_probes(tmp_path / "absent.jsonl") == []
+
+
+def test_read_puis_agrege(tmp_path):
+    reg = tmp_path / "r.jsonl"
+    reg.write_text(json.dumps(
+        {"type": "node_hardware",
+         "payload": _probe("n1", "minimal-gpu-rocm", [{"vendor": "amd"}], ["rocm"])}) + "\n",
+        encoding="utf-8")
+    view = cluster_view(read_probes(reg))
+    assert view["vendors"] == {"amd": ["n1"]}
+
+
+def test_cli_node_cluster_en_process(tmp_path, capsys):
+    """Couvre le handler cli.py EN PROCESS (coverage) : `node cluster` affiche vendor->nœuds."""
+    import forgeai.cli as cli
+    reg = tmp_path / "r.jsonl"
+    reg.write_text(json.dumps({
+        "type": "node_hardware",
+        "payload": _probe("pc-amd", "minimal-gpu-rocm", [{"vendor": "amd"}], ["rocm"])}) + "\n",
+        encoding="utf-8")
+    rc = cli.main(["node", "cluster", "--registre", str(reg)])
+    out = capsys.readouterr().out
+    assert rc == 0
+    assert "pc-amd" in out and "amd -> pc-amd" in out
```
## Preuve déterministe
```
.....                                                                    [100%]
..........s............................................................. [ 99%]
...                                                                      [100%]
All checks passed!
(cli.py : 17 fixables sur origin/main ET HEAD — aucun nouveau problème)
```
