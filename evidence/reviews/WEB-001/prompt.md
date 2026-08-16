# WEB-001 — Manifeste du prompt de revue finale — round 3

- Round: `3`
- Base: `828714b25895b7f6a49e16bed0ae6b22366ce030`
- Candidat revu: `31ddc6653b0016d728f87df3ac5cba89403c5e4f`
- Artefact diff SHA-256:
  `92604858b0dd46a8410f1c3c6ad79a162003cc1063dea212d30dcb64ebf3e546`
- Prompt exact SHA-256:
  `f1c3d94e0534b4ad26b177559137073a9a22840e38a0b09949cd44e486e2a0a8`
- Preuve locale fournie aux reviewers SHA-256:
  `87470059f313488478d1a9bba29c8833af689609e390dfd6efc381c84d3f8b26`
- Générateur: `scripts/revue.py prompt`
- Template canonique: `CANON/revue-template.md`

Le prompt exact a été généré à partir du diff `base..candidat` et du rapport externe
`round-3-candidate-gates-report.md`, puis transmis sans modification aux trois reviewers.
Ses octets exacts sont conservés dans l'état PROOF externe et vérifiés par le hash ci-dessus.

La copie brute n'est pas versionnée ici: un diff unifié contient volontairement des lignes
de contexte composées d'un espace, que `git diff --check` interprète comme du whitespace
terminal lorsqu'elles sont intégrées dans un fichier Markdown. Ce manifeste garde le paquet
reproductible sans altérer les octets du prompt scellé ni affaiblir le gate whitespace.

Les verdicts associés déclarent explicitement trois contextes frais, deux variantes de
modèle, un seul fournisseur OpenAI et l'indisponibilité de `gpt-5.5`.
