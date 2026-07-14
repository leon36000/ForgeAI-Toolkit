# AGENTS — ForgeAI Toolkit

## Mission
Construire le ForgeAI Toolkit selon le plan maître BMAD
([CANON/PLAN-MAITRE-EXECUTION-BMAD-v1.0.md](CANON/PLAN-MAITRE-EXECUTION-BMAD-v1.0.md)).
Fable (session lead Claude Code) orchestre; les membres de l'équipe sont routés via
`forge-model-bridge` (LiteLLM, 127.0.0.1:4000) — voir `manifests/roles.yaml` et `manifests/routes.yaml`.

## Règles non négociables
1. **§8bis — zéro stub, zéro faux** : une story sort en DONE-avec-preuve ou BLOCKED-avec-raison.
   Interdits dans tout code mergé : corps vides, `NotImplementedError`, marqueurs de travail
   inachevé, tests sans assertion, données inventées présentées comme réelles.
   Gate : `python3 scripts/no_stub_scan.py --all` (bloquant, aucune exception).
2. **Preuve au registre** : chaque livrable ⇒ une entrée dans `Registres/*.jsonl` via
   `scripts/registre.py append`. Un livrable sans preuve n'existe pas.
3. **Revue aveugle scellée (§3)** : verdicts déposés dans `reviews/<étape>/<modèle>.verdict.json`
   sans accès aux verdicts des autres. Jamais de verdict attendu, de compte d'approbations
   ni d'identité de reviewers dans un prompt de revue.
4. **Sorties de modèles = CLAIMS non vérifiées** : toute réponse du bridge est marquée
   `_claim_status=UNVERIFIED` — vérifier avant de relayer ou merger.
5. **T3 = Nathan** : paiements, secrets de production, suppressions définitives,
   engagements externes. Le consensus recommande; l'humain lève.

## Commandes
```bash
python3 scripts/registre.py append Registres/mission.jsonl --type <type> --actor <actor> --payload-json '<json>'
python3 scripts/registre.py verify Registres/mission.jsonl
python3 scripts/no_stub_scan.py --all
pytest
```

## Canon externe
Canon Serveur (lecture seule) : `/media/pc1/Storage/Serveur/docs/CANON/`
