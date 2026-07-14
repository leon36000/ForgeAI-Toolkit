<!-- Livrable Phase A (rattrapage) — §1 plan maître
membre: longcat (LongCat-2.0 via forge-model-bridge, provider_id=LongCat-2.0)
date: 2026-07-14 | statut: DONE (en 3 lots ultra-courts — la route timeout au-delà de ~10 lignes) | claim: UNVERIFIED
Lève le BLOCKED du registre seq 5 — précondition P2 satisfaite (constats à intégrer dans les stories P2).
-->
# Revue critique du protocole multi-nœuds — sécurité/secrets

## Constats

| ID | Sévérité | Problème → Recommandation |
|---|---|---|
| SEC-01 | Élevée | Clés ed25519 sans rotation sur les nœuds → Rotation automatisée via rekey et cron |
| SEC-02 | Moyenne | Authkeys Tailscale persistants → Utiliser `--ephemeral=true` et ACLs restrictives |
| SEC-03 | **Critique** | TOFU SSH distribué (risque MITM) → Implémenter une PKI interne ou Tailscale SSH |
| SEC-04 | Élevée | Métadonnées registres committées en clair → Stripper les labels sensibles avant le push Git |
| SEC-05 | **Critique** | Images conteneurs non pinnées par digest → Imposer le pinning par digest SHA256 |
| SEC-06 | **Critique** | Nœud compromis/exfiltration → Appliquer des Network Policies restrictives (Calico/Cilium) |
| SEC-07 | **Critique** | ACL Tailscale par défaut → Restreindre les ACL au moindre privilège |
| SEC-08 | Faible | Annexe technique v2.2 absente du dossier → Intégrer l'annexe v2.2 manquante |

## Exigences pré-code P2 (testables)

- EX-1 : Le système doit rejeter toute connexion SSH avec une clé d'hôte inconnue en imposant une vérification stricte (pas de TOFU).
- EX-2 : Toutes les images conteneurs doivent être épinglées via leur empreinte cryptographique SHA256 plutôt qu'un tag mutable.
- EX-3 : Les ACL Tailscale doivent appliquer une politique de refus par défaut (deny-all) pour tout trafic inter-nœud non autorisé.
- EX-4 : Le système doit automatiquement isoler le nœud et révoquer ses accès réseau à la détection d'une compromission.
- EX-5 : Les clés ed25519 (hôtes et utilisateurs) doivent être renouvelées automatiquement avant leur expiration.
