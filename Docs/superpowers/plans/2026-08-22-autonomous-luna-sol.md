# Plan de livraison — autonomie Luna/Sol

## État initial

La phase compacte (#609) avait déjà livré la politique, le dispatch Sol, la
validation de reçu et la preuve `ORCH-LUNA-SOL-603-phaseA-r5`. Après fusion,
l’audit archive a révélé quatorze entrées historiques de `BINDING.txt` ne
pointaient plus vers des ancêtres de `main`; l’état antérieur à #609 présentait
le même défaut.

## Exécution bornée

1. Retirer uniquement ces entrées du manifeste actif, conserver les dossiers et
   consigner chaque retrait dans `ARCHIVE-UNMERGED.txt`.
2. Ajouter la preuve de non-régression du mode archive au test du manifeste réel.
3. Mettre à jour la story et la référence exécutable, puis ajouter ce plan et
   la spécification de conception.
4. Ajouter l’événement de livraison au registre avec `scripts/registre.py
   append`, régénérer les vues et vérifier l’autorité.
5. Construire un prompt Sol frais et aveugle pour le diff final, obtenir son
   APPROVE, sceller le reçu `ORCH-LUNA-SOL-603-final-seal`, l’ajouter à
   `BINDING.txt`, puis exécuter les gates PR locaux et CI avant le merge. La
   story reste `IN_PROGRESS` pendant cette étape.
6. Après le merge, rejouer le mode archive sur `main` fusionné. Si ce contrôle
   passe, créer la transaction de clôture post-merge qui passe la story à
   `DONE_WITH_EVIDENCE` et ajoute l’événement terminal au registre; sinon
   conserver `BLOCKED_WITH_REASON` avec la sortie du gate.
7. Vérifier les vues régénérées et l’état terminal après cette clôture; aucune
   transition terminale n’est faite avant le contrôle archive post-merge.

## Critère d’arrêt

Le travail n’est terminé que si le gate archive, le gate PR, les tests complets,
les registres et les vues générées passent, et si la preuve Sol finale est
liée au diff exact. Sinon la story reste bloquée avec une raison vérifiable.
