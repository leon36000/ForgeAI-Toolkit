#!/usr/bin/env python3
"""Banc de mesure K8S-022 : quel profil de securityContext chaque image du socle tolère-t-elle
RÉELLEMENT sur un cluster k3s ? Aucune valeur inventée : chaque ligne = un pod appliqué + observé."""
import json, subprocess, sys, time

NS = "k8s022-probe"
CASES = [
    # (id, image, node, uid, data_mount, env)
    ("redis-restricted",  "redis:7-alpine",         "pc2-forge-b", 999,  "/data", {}),
    ("redis-root-drop",   "redis:7-alpine",         "pc2-forge-b", None, "/data", {}),
    ("qdrant-restricted", "qdrant/qdrant:v1.12.5",  "pc2-forge-b", 1000, "/qdrant/storage", {}),
    ("litellm-restricted","ghcr.io/berriai/litellm:main-stable","pc2-forge-b",1000,"/appdata",{}),
    ("tei-restricted",    "ghcr.io/huggingface/text-embeddings-inference:cpu-1.5","pc2-forge-b",1000,"/data",{}),
    ("ollama-restricted", "ollama/ollama:latest",   "pc2-forge-b", 1000, "/root/.ollama", {}),
    ("ollama-homeover",   "ollama/ollama:latest",   "pc2-forge-b", 1000, "/models",
     {"HOME": "/models", "OLLAMA_MODELS": "/models"}),
    ("postgres-restricted","postgres:18.3-alpine",  "pc1-x870e-taichi", 999, "/var/lib/postgresql/data",
     {"POSTGRES_PASSWORD": "probe-only-not-a-secret"}),
]

def pod(cid, image, node, uid, mount, env):
    envs = "".join(f"\n            - name: {k}\n              value: \"{v}\"" for k, v in env.items())
    envb = f"\n          env:{envs}" if envs else ""
    pod_sc = "\n    seccompProfile:\n      type: RuntimeDefault"
    if uid is not None:
        pod_sc = (f"\n    runAsNonRoot: true\n    runAsUser: {uid}\n    runAsGroup: {uid}"
                  f"\n    fsGroup: {uid}" + pod_sc)
    return f"""apiVersion: v1
kind: Pod
metadata:
  name: {cid}
  namespace: {NS}
spec:
  restartPolicy: Never
  nodeSelector: {{kubernetes.io/hostname: {node}}}
  securityContext:{pod_sc}
  containers:
    - name: c
      image: {image}
      imagePullPolicy: IfNotPresent{envb}
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities:
          drop: ["ALL"]
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

def sh(a, **k): return subprocess.run(a, capture_output=True, text=True, timeout=120, **k)

sh(["kubectl", "create", "ns", NS])
for cid, image, node, uid, mount, env in CASES:
    sh(["kubectl", "delete", "pod", cid, "-n", NS, "--ignore-not-found"])
    r = sh(["kubectl", "apply", "-f", "-"], input=pod(cid, image, node, uid, mount, env))
    if r.returncode:
        print(json.dumps({"case": cid, "verdict": "APPLY_REFUSE", "detail": r.stderr.strip()[:300]}))
        continue
    verdict, detail = "TIMEOUT", ""
    for _ in range(30):
        time.sleep(4)
        g = sh(["kubectl", "get", "pod", cid, "-n", NS, "-o", "json"])
        if g.returncode:
            continue
        st = json.loads(g.stdout).get("status", {})
        cs = (st.get("containerStatuses") or [{}])[0]
        phase = st.get("phase")
        waiting = (cs.get("state", {}).get("waiting") or {})
        term = (cs.get("state", {}).get("lastState", {}) or {})
        if waiting.get("reason") in ("CreateContainerConfigError", "CrashLoopBackOff",
                                     "CreateContainerError", "ErrImagePull", "ImagePullBackOff"):
            verdict = waiting["reason"]; detail = (waiting.get("message") or "")[:260]; break
        if phase == "Failed":
            verdict = "FAILED"; detail = str(term)[:260]; break
        if cs.get("ready") and phase == "Running":
            verdict = "READY"; break
        if phase == "Running" and cs.get("restartCount", 0) == 0 and _ >= 5:
            verdict = "RUNNING_NO_RESTART"; break
    logs = sh(["kubectl", "logs", cid, "-n", NS, "--tail=6"]).stdout.strip().replace("\n", " | ")[:300]
    print(json.dumps({"case": cid, "uid": uid, "image": image, "verdict": verdict,
                      "detail": detail, "logs": logs}, ensure_ascii=False))
    sys.stdout.flush()
