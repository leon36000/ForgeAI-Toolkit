# RES-012B — journal de la revue scellée

**APPROVE 3/3** — vendors distincts `deepseek / google / xai`, sceau `8af770671f5e`,
**0 objection critique**. Trio stable applicable : seul **MiniMax-M3** a codé ce package, aucun
chevauchement de vendor avec les trois reviewers. Aucun SWAP CIV nécessaire.

## Objection reçue et traitée
**DeepSeek-V4-Pro, sévérité MINEURE** : *« La spécification mentionne 6 codes `ERR_RES_*` stables,
mais le diff n'en définit que 5. »*

**Objection RECEVABLE — vérifiée puis corrigée.** Comptage déterministe sur le source :
```
$ grep -o 'ERR_RES_[A-Z_]*' src/forgeai/core/models.py | sort -u | wc -l
5
```
`ERR_RES_CLASSE_INCONNUE`, `ERR_RES_DEROGATION_PARTIELLE`, `ERR_RES_CPU_INVALIDE`,
`ERR_RES_MEMOIRE_INVALIDE`, `ERR_RES_LIMITS_INFERIEURES`.

Le chiffre « 6 » était une **affirmation inexacte de ma part**, répétée dans la story, le corps de
la PR et le message de commit. Story et PR corrigées ; l'historique de commit n'est pas réécrit ;
la correction est journalisée au registre hash-chaîné (`PATCH-RES-012B.jsonl`, seq 2, type
`correction`).

C'est exactement le rôle de la revue indépendante : aucune des trois relectures n'a contesté le
fond — mais l'une a vérifié un chiffre que j'avais avancé sans le compter.

## Ce que le pack contenait
Diff intégral, preuve rouge sur `origin/main`, **mesure de l'empreinte mémoire réelle de litellm**
sur cluster (~1018 Mi au repos, expliquant l'OOMKill sous la limite de 1024 Mi), et le
**déploiement réel** post-correctif : litellm `1/1 Running`, 0 redémarrage, 1009 Mi sous 2Gi.
