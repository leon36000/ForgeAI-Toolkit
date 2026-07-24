# Configuration openbao PRODUCTION (hors mode DEV) — epic FAI-0005 (#108).
# Stockage FICHIER persistant (souverain, instance unique) ; le coffre démarre SCELLÉ et non
# initialisé : l'init/unseal est orchestré par le flux de déploiement (S5) + un sidecar de
# re-unseal (S3/S4). mlock ACTIF (pas de disable_mlock) → requiert la capability IPC_LOCK.
storage "file" {
  path = "/openbao/data"
}

listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = 1
}

api_addr = "http://openbao:8200"
