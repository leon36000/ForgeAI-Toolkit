#!/usr/bin/env python3
"""K8S-022 variante E : Restricted COMPLET + volumes inscriptibles explicites (emptyDir).
Hypothèse : les échecs qdrant/ollama sont des besoins d'ÉCRITURE, pas des besoins de privilège."""
import json, subprocess, sys, time
NS = "k8s022-probe"
CASES = [
    ("qdrant-e", "qdrant/qdrant:v1.12.5", "pc2-forge-b", 1000,
     ["/qdrant/storage", "/qdrant/snapshots", "/tmp"], {}, True),
    ("ollama-e", "ollama/ollama:latest", "pc2-forge-b", 1000,
     ["/root/.ollama", "/home/ubuntu", "/tmp"], {}, True),
    ("ollama-f", "ollama/ollama:latest", "pc2-forge-b", 1000, ["/root/.ollama", "/tmp"], {}, False),
]

def pod(cid, image, node, uid, mounts, env, rorf):
    envs = "".join(f"\n        - name: {k}\n          value: \"{v}\"" for k, v in env.items())
    envb = f"\n      env:{envs}" if envs else ""
    vm = "".join(f"\n        - name: w{i}\n          mountPath: {m}" for i, m in enumerate(mounts))
    vols = "".join(f"\n    - name: w{i}\n      emptyDir: {{}}" for i, _ in enumerate(mounts))
    ro = "\n        readOnlyRootFilesystem: true" if rorf else ""
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
      image: {image}
      imagePullPolicy: IfNotPresent{envb}
      securityContext:
        allowPrivilegeEscalation: false{ro}
        capabilities:
          drop: ["ALL"]
      volumeMounts:{vm}
  volumes:{vols}
"""

def sh(a, **k): return subprocess.run(a, capture_output=True, text=True, timeout=180, **k)
for cid, image, node, uid, mounts, env, rorf in CASES:
    sh(["kubectl", "delete", "pod", cid, "-n", NS, "--ignore-not-found", "--wait=false"]); time.sleep(2)
    r = sh(["kubectl", "apply", "-f", "-"], input=pod(cid, image, node, uid, mounts, env, rorf))
    if r.returncode:
        print(json.dumps({"case": cid, "verdict": "APPLY_REFUSE", "detail": r.stderr[:200]})); continue
    verdict = "TIMEOUT"
    for t in range(22):
        time.sleep(4)
        g = sh(["kubectl", "get", "pod", cid, "-n", NS, "-o", "json"])
        if g.returncode: continue
        st = json.loads(g.stdout).get("status", {}); cs = (st.get("containerStatuses") or [{}])[0]
        w = cs.get("state", {}).get("waiting") or {}; term = cs.get("state", {}).get("terminated") or {}
        if w.get("reason") in ("CreateContainerConfigError", "CrashLoopBackOff", "CreateContainerError"):
            verdict = w["reason"]; break
        if term: verdict = "EXIT_%s" % term.get("exitCode"); break
        if cs.get("ready") and st.get("phase") == "Running": verdict = "READY"; break
        if st.get("phase") == "Running" and t >= 8: verdict = "RUNNING_NOT_READY"; break
    lg = sh(["kubectl", "logs", cid, "-n", NS, "--tail=4"])
    print(json.dumps({"case": cid, "rorf": rorf, "mounts": mounts, "verdict": verdict,
                      "logs": (lg.stdout or lg.stderr).strip().replace("\n", " | ")[:220]},
                     ensure_ascii=False)); sys.stdout.flush()
