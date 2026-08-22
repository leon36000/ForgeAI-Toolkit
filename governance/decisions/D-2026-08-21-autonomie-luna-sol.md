# Décision — contrat d’autonomie Luna/Sol

Date : 2026-08-21

Référence : issue GitHub [#603 — mode autonome Luna/Sol](https://github.com/leon36000/ForgeAI-Toolkit/issues/603).

## Décision

GPT-5.6 Luna conduit et écrit les changements dans un mode explicite plafonné à
deux lanes d’écriture actives. GPT-5.6 Sol intervient comme reviewer frais,
aveugle et en lecture seule pour les livraisons soumises au mode sol_blind.

La politique active définit `sol_blind` comme mode par défaut pour les PR
courantes et exige ce mode dans le reçu qui les couvre. Le mode historique
multi-vendor reste compatible pour les reçus d’archive; il ne peut pas couvrir
une PR courante. Les identités actives luna_writer et sol sont ajoutées au
roster sans supprimer l’identité historique luna, qui reste résoluble pour
les reçus archivés.

## Portée et limites

Cette décision versionne le contrat observable dans
governance/autonomy-policy.json. Les frontières T3 de Nathan restent
inchangées : paiements, secrets de production, suppressions définitives et
engagements externes ne sont pas délégués.

Cette entrée matérialise la décision comme source d’autorité sous
l’identifiant gov.decision-autonomie-luna-sol.
