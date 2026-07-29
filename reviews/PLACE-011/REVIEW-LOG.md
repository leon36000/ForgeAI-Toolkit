# PLACE-011 — journal de la revue scellée

## Tour 2 : **APPROVE 3/3, zéro objection**
Vendors distincts `deepseek / google / xai`, sceau `cfeda4d3b5c3`. Trio stable applicable : seul
**MiniMax-M3** a codé ce package, aucun chevauchement de vendor. Aucun SWAP CIV nécessaire.

## Tour 1 : APPROVE 3/3 — mais quatre objections mineures, toutes recevables
Sceau `258d2f6d1de2`. Le verdict global était déjà APPROVE ; les objections ont néanmoins **toutes
été traitées**. Un APPROVE n'autorise pas à ignorer ce que les relecteurs ont vu.

### Convergence à trois sur le même point
Gemini, Grok et DeepSeek ont relevé **indépendamment** que `NodeInventaire` levait
`ERR_PLACE_VENDOR_INCONNU` pour un hostname vide et une VRAM négative — deux cas étrangers au
vendor. Ironie utile : ce package existe pour produire des erreurs **causales**, et son propre
contrat en portait une trompeuse. Trois codes distincts désormais.

### DeepSeek — inventaire vide ≠ absence d'inventaire
`None` = « je ne sais pas » ; `()` = « je sais, et il n'y a rien ». Le correctif du contrat ne
suffisait pas : **mon propre câblage du renderer** testait `if inventaire:` et court-circuitait la
validation avant de l'appeler. Corrigé en `is not None`. Sans le test rouge écrit avant, je
l'aurais manqué — le contrat était juste, le branchement ne l'était pas.

### Grok — un comportement prouvé n'est pas un comportement protégé
`ERR_PLACE_NOEUD_INCONNU` était démontré dans `COMPORTEMENT.txt` mais aucun test ne le couvrait. Le
test ajouté **passe du premier coup** : la fonctionnalité existait, rien ne la protégeait d'une
régression. Même famille d'erreur que le test-sur-chemin-inventé de RAG-005, vue par l'autre bout —
là un test sans comportement, ici un comportement sans test.

## Méthode appliquée
Trois tests rouges écrits **avant** tout correctif. Deux ont échoué, un est passé d'emblée — ce qui
a confirmé précisément le diagnostic de Grok. Le tour 2 a jugé le pack **reconstruit après
correction** : les trois vendors ont donc évalué l'artefact final, pas un diff supersédé.
