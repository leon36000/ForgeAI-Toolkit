# Configuration openbao PRODUCTION (hors mode DEV) — epic FAI-0005 (#108).
# Stockage FICHIER persistant (souverain, instance unique) ; le coffre démarre SCELLÉ et non
# initialisé : l'init/unseal est orchestré par le flux de déploiement (S5) + un sidecar de
# re-unseal (S3/S4).
# Chemin `/openbao/file` : répertoire PRÉ-CRÉÉ INSCRIPTIBLE par l'utilisateur non-root `openbao`
# (UID 100) de l'image officielle (convention image, comme /vault/file de HashiCorp Vault). Un
# volume monté sur /openbao/data serait possédé par root -> openbao ne peut PAS y écrire (prouvé
# e2e S6 : « mkdir /openbao/data/core: permission denied »).
#
# disable_mlock = true : POSTURE CONTENEUR STANDARD (défaut du chart Helm HashiCorp Vault). PROUVÉ
# e2e S6 : l'image officielle lance `bao` en UTILISATEUR NON-ROOT (UID 100) sans file-capability et
# sans setcap à l'entrypoint -> un `cap_add: IPC_LOCK` reste dans le set BOUNDING mais JAMAIS dans le
# set EFFECTIVE du process (CapEff=0) -> mlockall() ne verrouille RIEN (VmLck=0). Prétendre « mlock
# actif » via cap_add serait donc un FAUX (secrets swappables malgré tout). Contrôle compensatoire
# DÉTERMINISTE = désactiver le swap sur le nœud (ou swap chiffré) — prérequis opérateur documenté
# (Docs/how-to/openbao-migration.md), frontière T3. Ainsi openbao démarre proprement (aucune erreur
# « Failed to lock memory ») et aucune capability privilégiée inutile n'est accordée (moindre privilège).
disable_mlock = true

storage "file" {
  path = "/openbao/file"
}

listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = 1
}

api_addr = "http://openbao:8200"
