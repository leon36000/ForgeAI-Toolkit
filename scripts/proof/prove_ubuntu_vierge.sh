#!/usr/bin/env bash
# Preuve REPRODUCTIBLE « Ubuntu vierge » — la vision ForgeAI de bout en bout.
#
# Démontre qu'un utilisateur avec un ubuntu:24.04 FRAÎCHEMENT installé (zéro pré-requis IA)
# peut télécharger forgeai et obtenir une infra IA DURCIE fonctionnelle, dans un environnement
# 100 % neuf et isolé (Docker-in-Docker), sans contaminer sa machine.
#
# Enchaînement prouvé :
#   ubuntu:24.04 nu → apt install python3 + docker.io + docker-compose-v2 → dockerd imbriqué
#   → pip install forgeai (ZÉRO dépendance, depuis les sources du repo)
#   → 4 images officielles pull FROM SCRATCH dans le conteneur
#   → forgeai déploie le socle durci → 4 services healthy
#   → RAG durci : contrôle négatif (aucune fabrication) + ancrage OOD (« Vornak-9 »)
#   → teardown (machine hôte propre)
#
# Prérequis HÔTE : docker (avec droit --privileged). Lourd (~15-20 min : pull ~2,5 Go + modèles).
# Usage : bash scripts/proof/prove_ubuntu_vierge.sh
#
# Piège DinD résolu : /var/lib/docker monté sur un VOLUME (fs hôte ext4), sinon overlayfs-sur-
# overlayfs échoue (invalid argument).
set -euo pipefail

REPO="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
INNER="$REPO/scripts/proof/prove_ubuntu_vierge_inner.py"
C=forgeai-vierge
VOL=forgeai-vierge-lib
IMAGES="ollama/ollama:latest qdrant/qdrant:v1.18.3 ghcr.io/huggingface/text-embeddings-inference:cpu-1.9 ghcr.io/berriai/litellm:main-stable"

cleanup() { docker rm -f "$C" >/dev/null 2>&1 || true; docker volume rm "$VOL" >/dev/null 2>&1 || true; }
trap cleanup EXIT
cleanup

echo "===== 1. ubuntu:24.04 NU (privilégié, /var/lib/docker sur volume) ====="
docker run -d --privileged -v "$VOL":/var/lib/docker -v "$REPO":/opt/forgeai-src:ro \
  --name "$C" ubuntu:24.04 sleep infinity >/dev/null

echo "===== 2. apt install python3 + docker.io + docker-compose-v2 ====="
docker exec "$C" bash -c "apt-get update -qq >/dev/null 2>&1 && \
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3 python3-pip docker.io docker-compose-v2 >/dev/null 2>&1 && echo OK-deps"

echo "===== 3. dockerd imbriqué ====="
docker exec -d "$C" bash -c "dockerd >/var/log/dockerd.log 2>&1"
docker exec "$C" bash -c 'for i in $(seq 1 20); do docker info >/dev/null 2>&1 && { echo dockerd-OK; break; }; sleep 2; done'

echo "===== 4. télécharger + installer forgeai (zéro dépendance) ====="
docker exec "$C" bash -c "mkdir -p /root/app && cp -r /opt/forgeai-src/pyproject.toml /opt/forgeai-src/src /root/app/ && \
  pip install --break-system-packages -q /root/app && \
  python3 -c 'import forgeai.rag.hardened; print(\"forgeai installé\")'"

echo "===== 5. pré-pull images officielles (retry DNS) ====="
docker cp "$INNER" "$C":/root/prove.py
for img in $IMAGES; do
  docker exec "$C" bash -c "for t in 1 2 3 4; do docker image inspect $img >/dev/null 2>&1 && break; docker pull -q $img >/dev/null 2>&1 && break; sleep 8; done; docker image inspect $img >/dev/null 2>&1 && echo 'OK $img' || { echo 'ECHEC-PULL $img'; exit 1; }"
done

echo "===== 6. forgeai DÉPLOIE le socle durci + PREUVE RAG ancré (dans l'ubuntu vierge) ====="
docker exec "$C" python3 /root/prove.py

echo "===== 7. teardown (trap EXIT) ====="
echo "UBUNTU-VIERGE-PROOF-OK"
