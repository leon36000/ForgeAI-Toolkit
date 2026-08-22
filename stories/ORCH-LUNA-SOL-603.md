# Story ORCH-LUNA-SOL-603 — contrat autonome Luna/Sol

Status: IN_PROGRESS — implémentation finale prête; scellement de la preuve Sol
et passage à l’état terminal après la revue aveugle.

## Contexte et périmètre

Cette story fixe le contrat observable de la politique autonome Luna/Sol. Elle
ne prétend aucune réussite runtime, matérielle, réseau ou externe. Le mode
actif est `sol_blind`; le mode historique `multi_vendor` reste compatible pour
les archives uniquement.

## Critères d’acceptation

- [x] La politique versionnée fixe GPT-5.6 Luna, exactement deux writer lanes,
  GPT-5.6 Sol, le mode frais/aveugle/read-only et les états terminaux.
- [x] Le dispatch de revue conserve le tally historique `multi_vendor` et
  exige un unique reviewer Sol pour `sol_blind`.
- [x] Le reçu Sol lie le diff Git, l’arbre, le prompt, les journaux exclus et
  les limites de fraîcheur sans dépendre de la configuration locale de Git.
- [x] La documentation, les registres, les vues et le nettoyage contrôlé de
  l’archive sont prêts; les anciens reçus non ancêtres restent conservés et
  sont listés dans `evidence/reviews/ARCHIVE-UNMERGED.txt`.
- [ ] Le reçu Sol final est scellé dans
  `evidence/reviews/ORCH-LUNA-SOL-603-final-r2/RECU.json`, lié au manifeste
  actif, puis le gate PR et le gate archive sur `main` fusionné passent.
- [ ] La story passe à `DONE_WITH_EVIDENCE` uniquement après ces preuves;
  aucune réussite runtime, matérielle, réseau ou externe n’est revendiquée.

## Limites

Les paiements, secrets de production, suppressions définitives et engagements
externes restent des décisions T3 humaines. Aucun workflow du contrat Luna/Sol
ne reçoit un droit d’écriture distant, ne force-push ou ne s’auto-écrit. Les
automatisations indépendantes et historiques du dépôt, notamment la mise à jour
contrôlée du lockfile CI, restent hors de ce contrat et conservent leur propre
politique de permissions.
