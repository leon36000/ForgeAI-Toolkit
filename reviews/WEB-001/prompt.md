# WEB-001 — Manifeste du prompt de revue finale

- Round: `2`
- Base: `828714b25895b7f6a49e16bed0ae6b22366ce030`
- Candidat revu: `0488e3ebbd029d794acf051db75c17dd672366fe`
- Artefact diff SHA-256:
  `b7d67909e2b95fb5dc221b3bc04fa7df74f59a50574f179ec315bfb8221147ff`
- Prompt exact SHA-256:
  `dbbbdf96d3ef849743148bb7ac2615327ded3cb5b63614462174d07a97d11f59`
- Preuve locale fournie aux reviewers SHA-256:
  `d2ca0644dff3897dc340aa51e4b934f81038f521e61c4b4ba393779edcfed9ae`
- Générateur: `scripts/revue.py prompt`
- Template canonique: `CANON/revue-template.md`

Le prompt exact a été généré à partir du diff `base..candidat` et du rapport externe
`final-candidate-gates-report.md`, puis transmis sans modification aux trois reviewers.
Ses octets exacts sont conservés dans l'état PROOF externe et vérifiés par le hash ci-dessus.

La copie brute n'est pas versionnée ici: un diff unifié contient volontairement des lignes
de contexte composées d'un espace, que `git diff --check` interprète comme du whitespace
terminal lorsqu'elles sont intégrées dans un fichier Markdown. Ce manifeste garde le paquet
reproductible sans altérer les octets du prompt scellé ni affaiblir le gate whitespace.

Les verdicts associés déclarent explicitement trois contextes frais, deux variantes de
modèle, un seul fournisseur OpenAI et l'indisponibilité de `gpt-5.5`.
