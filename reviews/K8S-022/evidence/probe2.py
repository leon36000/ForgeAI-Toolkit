#!/usr/bin/env python3
"""K8S-022 — matrice d'isolation : QUEL contrôle Restricted casse QUEL service ?
Variantes : A=restricted complet | B=sans readOnlyRootFilesystem | C=root+dropALL | D=baseline actuel."""
import json, subprocess, sys, time
NS = "k8s022-probe"
SERVICES = [
    ("qdrant",   "qdrant/qdrant:v1.12.5", "pc2-forge-b", 1000, "/qdrant/storage", {}),
    ("tei",      "ghcr.io/huggingface/text-embeddings-inference:cpu-1.5", "pc2-forge-b", 1000, "/data",
     {"MODEL_ID": "BAAI/bge-small-en-v1.5", "HF_HUB_OFFLINE": "1"}),
    ("ollama",   "ollama/ollama:latest", "pc2-forge-b", 1000, "/root/.ollama", {}),
    ("ollamahome","ollama/ollama:latest", "pc2-forge-b", 1000, "/models",
     {"HOME": "/models", "OLLAMA_MODELS": "/models/m"}),
    ("postgres", "postgres:18.3-alpine", "pc1-x870e-taichi", 999, "/var/lib/postgresql/data",
     {"POSTGRES_PASSWORD": "probe-only-not-a-secret", "PGDATA": "/var/lib/postgresql/data/pgdata"}),
]
VARIANTS = {"A": (True, True, True), "B": (True, False, True),
            "C": (False, False, True), "D": (False, False, False)}  # (nonroot, rorf, dropall)

def pod(cid, image, node, uid, mount, env, nonroot, rorf, dropall):
    envs = "".join(f"\n        - name: {k}\n          value: \"{v}\"" for k, v in env.items())
    envb = f"\n      env:{envs}" if envs else ""
    psc = "\n    seccompProfile:\n      type: RuntimeDefault"
    if nonroot:
        psc = f"\n    runAsNonRoot: true\n    runAsUser: {uid}\n    runAsGroup: {uid}\n    fsGroup: {uid}" + psc
    csc = "\n        allowPrivilegeEscalation: false"
    if rorf:
        csc += "\n        readOnlyRootFilesystem: true"
    if dropall:
        csc += "\n        capabilities:\n          drop: [\"ALL\"]"
    return f"""apiVersion: v1
kind: Pod
metadata:
  name: {cid}
  namespace: {NS}
spec:
  restartPolicy: Never
  nodeSelector: {{kubernetes.io/hostname: {node}}}
  securityContext:{psc}
  containers:
    - name: c
      image: {image}
      imagePullPolicy: IfNotPresent{envb}
      securityContext:{csc}
      volumeMounts:
        - name: data
          mountPath: {mount}
        - name: tmp
          mountPath: /tmp
  volumes:
    - name: data
      emptyDir: {{}}
    - name: tmp
      emptyDir: {{}}
"""

def sh(a, **k): return subprocess.run(a, capture_output=True, text=True, timeout=180, **k)
sh(["kubectl", "create", "ns", NS])
for svc, image, node, uid, mount, env in SERVICES:
    for vid, (nonroot, rorf, dropall) in VARIANTS.items():
        cid = f"{svc}-{vid.lower()}"
        sh(["kubectl", "delete", "pod", cid, "-n", NS, "--ignore-not-found", "--wait=false"])
        time.sleep(2)
        r = sh(["kubectl", "apply", "-f", "-"],
               input=pod(cid, image, node, uid, mount, env, nonroot, rorf, dropall))
        if r.returncode:
            print(json.dumps({"svc": svc, "variant": vid, "verdict": "APPLY_REFUSE",
                              "detail": r.stderr.strip()[:200]})); sys.stdout.flush(); continue
        verdict, detail = "TIMEOUT", ""
        for t in range(22):
            time.sleep(4)
            g = sh(["kubectl", "get", "pod", cid, "-n", NS, "-o", "json"])
            if g.returncode: continue
            st = json.loads(g.stdout).get("status", {})
            cs = (st.get("containerStatuses") or [{}])[0]; phase = st.get("phase")
            w = cs.get("state", {}).get("waiting") or {}
            term = cs.get("state", {}).get("terminated") or {}
            if w.get("reason") in ("CreateContainerConfigError", "CreateContainerError",
                                   "ErrImagePull", "ImagePullBackOff", "CrashLoopBackOff"):
                verdict, detail = w["reason"], (w.get("message") or "")[:200]; break
            if term:
                verdict = "EXIT_%s" % term.get("exitCode"); detail = (term.get("reason") or "")[:80]; break
            if phase == "Failed": verdict = "FAILED"; break
            if cs.get("ready") and phase == "Running": verdict = "READY"; break
            if phase == "Running" and t >= 7: verdict = "RUNNING_NOT_READY"; break
        logs = sh(["kubectl", "logs", cid, "-n", NS, "--tail=4"])
        out = (logs.stdout or logs.stderr).strip().replace("\n", " | ")[:240]
        print(json.dumps({"svc": svc, "variant": vid, "nonroot": nonroot, "rorf": rorf,
                          "dropall": dropall, "verdict": verdict, "detail": detail, "logs": out},
                         ensure_ascii=False)); sys.stdout.flush()
