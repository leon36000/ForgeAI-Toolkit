#!/bin/bash
# Test réseau de laboratoire K8S-023 : les flux PERMIS passent, les INTERDITS sont bloqués.
for i in $(seq 1 20); do
  pr=$(kubectl get pods -n np-lab --no-headers 2>/dev/null|grep -c "1/1     Running")
  [ "$pr" -ge 3 ] && break; sleep 10
done
kubectl get pods -n np-lab --no-headers 2>/dev/null|awk '{print "  "$1" "$2" "$3}'
POD_LITELLM=$(kubectl get pod -n np-lab -l app=litellm -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
POD_ISOLE=$(kubectl get pod -n np-lab -l app=isole -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
essai() {  # $1=pod  $2=commande  $3=libellé  $4=attendu
  r=$(kubectl exec -n np-lab "$1" -- sh -c "$2" 2>/dev/null)
  [ -z "$r" ] && r="BLOQUE"
  ok="INATTENDU"; [ "$r" = "$4" ] && ok="conforme"
  printf "  %-46s -> %-8s (attendu %-8s) %s\n" "$3" "$r" "$4" "$ok"
}
echo "--- flux PERMIS (dépendance déclarée litellm -> redis) ---"
essai "$POD_LITELLM" "nc -z -w3 redis 6379 && echo PASSE" "litellm -> redis:6379" "PASSE"
echo "--- flux INTERDITS ---"
essai "$POD_ISOLE"   "nc -z -w3 redis 6379 && echo PASSE" "isole -> redis:6379 (aucune dépendance)" "BLOQUE"
essai "$POD_LITELLM" "wget -T3 -q -O- http://1.1.1.1 >/dev/null && echo PASSE" "litellm -> Internet (1.1.1.1)" "BLOQUE"
essai "$POD_ISOLE"   "wget -T3 -q -O- http://1.1.1.1 >/dev/null && echo PASSE" "isole -> Internet (1.1.1.1)" "BLOQUE"
echo "--- DNS (rouvert explicitement, sans ouvrir Internet) ---"
# FQDN complet : `nslookup redis` échouait sur la résolution du nom court (search domain),
# pas sur la politique réseau — faux positif de sonde, diagnostiqué avant tout correctif.
essai "$POD_LITELLM" "nslookup redis.np-lab.svc.cluster.local >/dev/null 2>&1 && echo PASSE" "litellm -> DNS kube-system:53" "PASSE"
