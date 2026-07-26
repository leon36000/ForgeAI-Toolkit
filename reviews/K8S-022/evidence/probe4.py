#!/usr/bin/env python3
"""K8S-022 — Q1/Q2 : le kubelet accepte-t-il runAsNonRoot:true SANS runAsUser ?
(décide si la table d'uid numériques est OBLIGATOIRE). Q3 : uid/gid natif de chaque image."""
import json, subprocess, sys, time
NS = "k8s022-probe"
# (id, image, mode) mode: "nonroot-sans-uid" | "id-natif"
CASES = [
    ("q1-openbao-nru", "openbao/openbao:2.6.0", "nonroot-sans-uid"),      # USER openbao (nommé)
    ("q2-qdrant-nru",  "qdrant/qdrant:v1.12.5", "nonroot-sans-uid"),      # USER 0:0
    ("q3-immudb",      "codenotary/immudb:1.11.1", "id-natif"),
    ("q3-langfuse",    "langfuse/langfuse:3", "id-natif"),
    ("q3-tei",         "ghcr.io/huggingface/text-embeddings-inference:cpu-1.5", "id-natif"),
    ("q3-litellm",     "ghcr.io/berriai/litellm:main-stable", "id-natif"),
    ("q3-postgres",    "postgres:18.3-alpine", "id-natif"),
]

def pod(cid, image, mode):
    if mode == "nonroot-sans-uid":
        psc = "\n    runAsNonRoot: true\n    seccompProfile:\n      type: RuntimeDefault"
        cmd = '\n      command: ["id"]'
    else:
        psc = "\n    seccompProfile:\n      type: RuntimeDefault"
        cmd = '\n      command: ["id"]'
    return f"""apiVersion: v1
kind: Pod
metadata:
  name: {cid}
  namespace: {NS}
spec:
  restartPolicy: Never
  nodeSelector: {{kubernetes.io/hostname: pc2-forge-b}}
  securityContext:{psc}
  containers:
    - name: c
      image: {image}{cmd}
      securityContext:
        allowPrivilegeEscalation: false
        capabilities:
          drop: ["ALL"]
"""

def sh(a, **k): return subprocess.run(a, capture_output=True, text=True, timeout=300, **k)
for cid, image, mode in CASES:
    sh(["kubectl", "delete", "pod", cid, "-n", NS, "--ignore-not-found", "--wait=false"]); time.sleep(1)
    r = sh(["kubectl", "apply", "-f", "-"], input=pod(cid, image, mode))
    if r.returncode:
        print(json.dumps({"case": cid, "verdict": "APPLY_REFUSE", "detail": r.stderr[:200]}))
        sys.stdout.flush(); continue
    verdict, detail = "TIMEOUT", ""
    for _ in range(40):
        time.sleep(5)
        g = sh(["kubectl", "get", "pod", cid, "-n", NS, "-o", "json"])
        if g.returncode: continue
        st = json.loads(g.stdout).get("status", {}); cs = (st.get("containerStatuses") or [{}])[0]
        w = cs.get("state", {}).get("waiting") or {}; term = cs.get("state", {}).get("terminated") or {}
        if w.get("reason") in ("CreateContainerConfigError", "CreateContainerError",
                               "ErrImagePull", "ImagePullBackOff"):
            verdict, detail = w["reason"], (w.get("message") or "")[:230]; break
        if term: verdict, detail = "EXIT_%s" % term.get("exitCode"), term.get("reason", ""); break
        if st.get("phase") == "Failed": verdict = "FAILED"; break
    lg = sh(["kubectl", "logs", cid, "-n", NS, "--tail=3"])
    print(json.dumps({"case": cid, "image": image, "mode": mode, "verdict": verdict,
                      "detail": detail, "id": (lg.stdout or "").strip()[:120]}, ensure_ascii=False))
    sys.stdout.flush()
