# Docs/ — documentation Diátaxis

Racine **unique** de la documentation (le dossier `docs/` en minuscules a été consolidé ici — cf.
`explanation/ADR-0001-structure-docs.md`). Quatre quadrants :

- `tutorials/` — prise en main guidée _(à alimenter)_
- `how-to/` — recettes ciblées _(à alimenter)_
- `reference/` — référence : gates et procédures
  - [`catalogue-gate.md`](reference/catalogue-gate.md) — gate de désambiguïsation du catalogue (B-26)
  - [`plugin-gate.md`](reference/plugin-gate.md) — gate de vérification des plugins (B-15)
  - [`reeval-defaults.md`](reference/reeval-defaults.md) — réévaluation des défauts par sphère (B-21)
  - [`proof-ubuntu-vierge.md`](reference/proof-ubuntu-vierge.md) — preuve de déploiement « Ubuntu vierge »
- `explanation/` — architecture et décisions
  - [`ADR-0001-structure-docs.md`](explanation/ADR-0001-structure-docs.md) — dossier de doc unique (Docs/)

Un merge touchant une API publique sans mise à jour de doc/canon est rejeté (§7 du plan maître).
