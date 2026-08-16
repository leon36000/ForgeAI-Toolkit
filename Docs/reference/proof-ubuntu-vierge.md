# Preuve « Ubuntu vierge » — déploiement de bout en bout depuis un système nu

ForgeAI Toolkit est distribué pour **le monde entier**, pas pour la machine d'un développeur. Cette
preuve le démontre : un utilisateur avec un `ubuntu:24.04` **fraîchement installé** (zéro pré-requis
IA) télécharge forgeai et obtient une **infra IA durcie fonctionnelle**, dans un environnement
100 % neuf et isolé (Docker-in-Docker), sans contaminer sa machine.

## Lancer la preuve

```bash
bash scripts/proof/prove_ubuntu_vierge.sh
```

Prérequis hôte : `docker` (droit `--privileged`). Durée ~15-20 min (téléchargements réels : ~2,5 Go
d'images + modèles). Le script est idempotent et nettoie tout en sortie (`trap EXIT`).

## Ce qui est prouvé (enchaînement réel)

1. **Système nu** : `ubuntu:24.04` privilégié, `/var/lib/docker` sur un volume dédié — le piège
   *overlayfs-sur-overlayfs* (`invalid argument`) est ainsi contourné (fs hôte ext4).
2. **Dépendances d'un système vierge** : `apt install python3 docker.io docker-compose-v2`, puis
   `dockerd` imbriqué. Note : `docker.io` seul **ne fournit pas** le plugin `docker compose` v2 —
   c'est pourquoi `forgeai doctor` le vérifie désormais explicitement (`check_docker`).
3. **Installation de l'app** : `pip install forgeai` — **zéro dépendance** (stdlib pur), donc
   portable partout.
4. **Déploiement from-scratch** : les 4 images officielles du socle durci sont *pull* dans le
   conteneur, puis `forgeai` génère le plan et `docker compose up`. Les 4 briques
   (ollama, qdrant v1.18.3, TEI/bge-m3, LiteLLM) atteignent l'état **healthy** (santé HTTP réelle).
5. **RAG durci ancré** :
   - *Contrôle négatif* — collection vide → aucune réponse fabriquée (`context_used=false`).
   - *Ancrage OOD* — un fait **fictif** (« Vornak-9 », hors connaissance paramétrique du modèle)
     est ingéré ; la réponse le contient et cite le document → l'ancrage vient du **retrieval**,
     pas des poids du modèle.
6. **Teardown propre** : la machine hôte reste inchangée.

## Traçabilité

Chaque exécution est destinée à être journalisée au registre (`evidence/registres/mission.jsonl`, type
`preuve_capacite`). La preuve est un **script reproductible** lancé à la demande (et non un test
CI : `--privileged` + réseau + ~2,5 Go la rendent inadaptée à l'intégration continue).
