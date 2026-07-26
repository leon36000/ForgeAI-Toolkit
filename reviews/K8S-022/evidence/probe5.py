#!/usr/bin/env python3
"""K8S-022 — Restricted COMPLET + volumes inscriptibles explicites, par service.
kind=REAL : vrai entrypoint du service. kind=WRITE : sonde d'écriture ciblée (service à
dépendances externes) — mesure exactement ce que Restricted change : l'uid non-root peut-il
écrire son volume de données et ses chemins de travail ?"""
import json, subprocess, sys, time
NS = "k8s022-probe"
CASES = [
    ("postgres-e", "postgres:18.3-alpine", "pc1-x870e-taichi", 999,
     ["/var/lib/postgresql/data", "/var/run/postgresql", "/tmp"],
     {"POSTGRES_PASSWORD": "probe-only-not-a-secret",
      "PGDATA": "/var/lib/postgresql/data/pgdata"}, "REAL", None),
    ("immudb-e", "codenotary/immudb:1.11.1", "pc2-forge-b", 3322,
     ["/var/lib/immudb", "/tmp"], {}, "REAL", None),
    ("openbao-e", "openbao/openbao:2.6.0", "pc2-forge-b", 100,
     ["/openbao/file", "/tmp"], {}, "WRITE", "/openbao/file"),
    ("tei-e", "ghcr.io/huggingface/text-embeddings-inference:cpu-1.5", "pc2-forge-b", 1000,
     ["/data", "/tmp"], {}, "WRITE", "/data"),
    ("langfuse-e", "langfuse/langfuse:3", "pc2-forge-b", 1000, ["/tmp"], {}, "WRITE", "/tmp"),
]

def pod(cid, image, node, uid, mounts, env, kind, wpath):
    envs = "".join(f"\n        - name: {k}\n          value: \"{v}\"" for k, v in env.items())
    envb = f"\n      env:{envs}" if envs else ""
    vm = "".join(f"\n        - name: w{i}\n          mountPath: {m}" for i, m in enumerate(mounts))
    vols = "".join(f"\n    - name: w{i}\n      emptyDir: {{}}" for i, _ in enumerate(mounts))
    cmd = ""
    if kind == "WRITE":
        cmd = ('\n      command: ["sh", "-c", "id && touch %s/sonde && echo ECRITURE_OK '
               '&& sleep 8"]' % wpath)
    return f"""apiVersion: v1
kind: Pod
metadata:
  name: {cid}
  namespace: {NS}
spec:
  restartPolicy: Never
  nodeSelector: {{kubernetes.io/hostname: {node}}}
  securityContext:
    runAsNonRoot: true
    runAsUser: {uid}
    runAsGroup: {uid}
    fsGroup: {uid}
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: c
      image: {image}{cmd}{envb}
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities:
          drop: ["ALL"]
      volumeMounts:{vm}
  volumes:{vols}
"""

def sh(a, **k): return subprocess.run(a, capture_output=True, text=True, timeout=300, **k)
for cid, image, node, uid, mounts, env, kind, wpath in CASES:
    sh(["kubectl", "delete", "pod", cid, "-n", NS, "--ignore-not-found", "--wait=false"]); time.sleep(1)
    r = sh(["kubectl", "apply", "-f", "-"], input=pod(cid, image, node, uid, mounts, env, kind, wpath))
    if r.returncode:
        print(json.dumps({"case": cid, "verdict": "APPLY_REFUSE", "detail": r.stderr[:200]}))
        sys.stdout.flush(); continue
    verdict, detail = "TIMEOUT", ""
    for t in range(40):
        time.sleep(5)
        g = sh(["kubectl", "get", "pod", cid, "-n", NS, "-o", "json"])
        if g.returncode: continue
        st = json.loads(g.stdout).get("status", {}); cs = (st.get("containerStatuses") or [{}])[0]
        w = cs.get("state", {}).get("waiting") or {}; term = cs.get("state", {}).get("terminated") or {}
        if w.get("reason") in ("CreateContainerConfigError", "CreateContainerError",
                               "ErrImagePull", "ImagePullBackOff"):
            verdict, detail = w["reason"], (w.get("message") or "")[:230]; break
        if term: verdict, detail = "EXIT_%s" % term.get("exitCode"), term.get("reason", ""); break
        if cs.get("ready") and st.get("phase") == "Running": verdict = "READY"; break
        if st.get("phase") == "Running" and t >= 9: verdict = "RUNNING_NOT_READY"; break
    lg = sh(["kubectl", "logs", cid, "-n", NS, "--tail=5"])
    print(json.dumps({"case": cid, "uid": uid, "kind": kind, "mounts": mounts, "verdict": verdict,
                      "detail": detail,
                      "logs": (lg.stdout or lg.stderr).strip().replace("\n", " | ")[:230]},
                     ensure_ascii=False)); sys.stdout.flush()
