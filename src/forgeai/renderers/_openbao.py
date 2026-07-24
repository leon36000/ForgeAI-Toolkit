"""Constantes openbao partagées par les renderers compose et k3s (source unique du script de re-unseal).

Le script de re-unseal est identique pour les deux backends : k3s l'exécute dans un 2e conteneur du
pod openbao (BAO_ADDR=127.0.0.1, même pod) ; compose l'exécute dans un service séparé
(BAO_ADDR=http://openbao:8200, réseau compose). Une seule source évite toute dérive entre backends.
"""
from __future__ import annotations

# Script POSIX sh du sidecar/service openbao-unsealer (sans jq ; ne fuit jamais la clé). BAO_ADDR
# paramètre l'adresse ; UNSEAL_MAX_ITERS borne la boucle pour les tests (0/absent = boucle infinie).
UNSEAL_SCRIPT = r"""ADDR="${BAO_ADDR:-http://127.0.0.1:8200}"
MAX_ITERS="${UNSEAL_MAX_ITERS:-0}"
i=0
key_empty_since=-1
while true; do
  if [ "$MAX_ITERS" -gt 0 ] && [ "$i" -ge "$MAX_ITERS" ]; then
    echo "openbao-unsealer: max iters atteint, sortie"; exit 0
  fi
  out=$(bao status -address="$ADDR" 2>/dev/null || true)
  if [ -z "$out" ]; then
    sleep 5; i=$((i + 1)); continue          # openbao pas encore joignable
  fi
  initialized=$(echo "$out" | grep -i '^Initialized' | awk '{print $NF}')
  sealed=$(echo "$out" | grep -i '^Sealed' | awk '{print $NF}')
  if [ "$initialized" = "false" ]; then
    if [ "$i" -ge 120 ]; then                 # 120*5s = 600s : init (flux de déploiement) absente
      echo "openbao-unsealer: non initialisé après 600s"; exit 1
    fi
  elif [ "$sealed" = "true" ]; then
    if [ -s /keys/unseal_key ]; then
      key_empty_since=-1
      bao operator unseal -address="$ADDR" "$(cat /keys/unseal_key)" >/dev/null 2>&1 || true
    else
      if [ "$key_empty_since" -lt 0 ]; then key_empty_since=$i; fi
      if [ $(( i - key_empty_since )) -ge 60 ]; then   # 60*5s = 300s de grâce (propagation kubelet)
        echo "openbao-unsealer: clé d'unseal absente (coffre cassé)"; exit 1
      fi
    fi
  else
    key_empty_since=-1                    # descellé -> no-op, reset compteur de grâce
  fi
  sleep 5; i=$((i + 1))
done
"""
