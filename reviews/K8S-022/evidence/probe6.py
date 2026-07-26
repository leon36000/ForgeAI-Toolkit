#!/usr/bin/env python3
"""K8S-022 — un pod GPU en passthrough hostPath (/dev/dri) tourne-t-il en Restricted
(non-root + drop ALL) et le device reste-t-il LISIBLE ? Décide de l'exception GPU."""
import json, subprocess, time
NS = "k8s022-probe"
SCRIPT = ("id; ls -ln /dev/dri | head -6; ok=0; ko=0; "
          "for d in /dev/dri/renderD* /dev/dri/card*; do "
          "[ -e $d ] || continue; if [ -r $d ] && [ -w $d ]; then ok=$((ok+1)); "
          "echo ACCES_OK $d; else ko=$((ko+1)); echo ACCES_REFUSE $d; fi; done; "
          "echo BILAN ok=$ok refuses=$ko")
CASES = [("gpu-nonroot", 1000, True, None), ("gpu-nonroot-grp", 1000, True, 44),
         ("gpu-root", None, True, None)]

def pod(cid, uid, dropall, suppl):
    psc = "\n    seccompProfile:\n      type: RuntimeDefault"
    if uid:
        psc = f"\n    runAsNonRoot: true\n    runAsUser: {uid}\n    runAsGroup: {uid}" + psc
    if suppl:
        psc += f"\n    supplementalGroups: [{suppl}]"
    csc = "\n        allowPrivilegeEscalation: false"
    if dropall:
        csc += "\n        capabilities:\n          drop:\n            - ALL"
    return f"""apiVersion: v1
kind: Pod
metadata:
  name: {cid}
  namespace: {NS}
spec:
  restartPolicy: Never
  nodeSelector:
    kubernetes.io/hostname: pc1-x870e-taichi
  securityContext:{psc}
  containers:
    - name: c
      image: busybox:latest
      imagePullPolicy: IfNotPresent
      command:
        - sh
        - -c
        - {SCRIPT!r}
      securityContext:{csc}
      volumeMounts:
        - name: dri
          mountPath: /dev/dri
  volumes:
    - name: dri
      hostPath:
        path: /dev/dri
"""

def sh(a, **k): return subprocess.run(a, capture_output=True, text=True, timeout=200, **k)
for cid, uid, dropall, suppl in CASES:
    sh(["kubectl", "delete", "pod", cid, "-n", NS, "--ignore-not-found", "--wait=false"]); time.sleep(1)
    r = sh(["kubectl", "apply", "-f", "-"], input=pod(cid, uid, dropall, suppl))
    if r.returncode:
        print(json.dumps({"case": cid, "verdict": "APPLY_REFUSE", "detail": r.stderr[:220]}),
              flush=True); continue
    verdict = "TIMEOUT"
    for _ in range(20):
        time.sleep(4)
        g = sh(["kubectl", "get", "pod", cid, "-n", NS, "-o", "jsonpath={.status.phase}"])
        if g.stdout in ("Succeeded", "Failed"): verdict = g.stdout; break
    lg = sh(["kubectl", "logs", cid, "-n", NS])
    print(json.dumps({"case": cid, "uid": uid, "suppl": suppl, "verdict": verdict,
                      "logs": (lg.stdout or lg.stderr).strip().replace("\n", " | ")[:420]},
                     ensure_ascii=False), flush=True)
