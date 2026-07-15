# Revue aveugle de l'OUTIL de revue (revue.py + template) — ARRÊT DUR #1

CIV : l'outil qui juge toutes les revues futures ne peut être validé par son seul auteur.
Revue conduite le 2026-07-15, 3 vendors non-Anthropic, prompt NEUTRE généré par l'outil
lui-même (dogfooding). Ce document est livré à Nathan ; **l'outil n'est pas utilisé en
production avant son OK**.

## La revue a trouvé 3 défauts RÉELS (que la revue solo / #17 auraient manqués)
1. **Injection croisée de template** (Qwen3.7-Max, moyen) — `build_prompt` enchaînait les
   `.replace()` : un champ contenant `{artefact}` injectait un autre champ. **Corrigé** :
   substitution en un seul passage (`re.sub`, jamais de re-scan) + test d'injection.
2. **Fuite d'en-tête** (Nemotron-3-Ultra, élevé) — sans marqueur `-->`, l'en-tête interne
   du template partait dans le prompt (non-neutralité). **Corrigé** : marqueur OBLIGATOIRE,
   `ValueError` sinon + test.
3. **Faille Sybil sur les vendors** (Nemotron-3-Ultra, moyen) — `vendor_of` acceptait des
   vendors inconnus → des chaînes bidon simuleraient « 3 vendors distincts ». **Corrigé** :
   le dépouillement rejette tout vendor hors `_KNOWN_VENDORS` + test.

## Dépouillement déterministe (par le script — invariant #10)
Round final, prompt complet identique `sha256=29bcf99c…`, 3 vendors distincts connus :
| Vendor | Modèle | Verdict |
|---|---|---|
| deepseek | DeepSeek-V4-Pro | APPROVE |
| zhipu | GLM-5.2 | APPROVE |
| nvidia | Nemotron-3-Ultra | REJECT (2 objections ci-dessus) |

`revue.py tally reviews/outil-revue` → **REJECT (2/3), bloquante élevée** (exit 1). Les 2
objections de Nemotron ont été corrigées APRÈS ce verdict ; l'outil compte désormais 14
tests verts (injection, marqueur, Sybil, déterminisme, neutralité structurelle).

## Incidents de routes (journalisés, pas d'abandon)
Gemini tronque la sortie JSON ; LongCat/Composer/MiMo/Qwen ont subi des timeouts MCP
transitoires → réassignations JOURNALISÉES vers vendors vivants (deepseek/glm/nemotron),
3 vendors distincts maintenus.

## Ma faute de process (honnête)
Lors des premiers envois, j'ai abrégé/rogné l'artefact à la main → prompts NON identiques
entre reviewers (un reviewer a d'ailleurs signalé un faux `NameError` dû à mon abréviation).
C'est exactement le risque que le pipeline doit supprimer. **Leçon : la livraison du prompt
de revue doit être automatisée par le pipeline (fichier généré → envoi), jamais retapée à la
main.** À intégrer comme story d'amélioration (Étape 4).

## État livré (STOP — décision de Nathan)
- Outil : `scripts/revue.py` + `CANON/revue-template.md`, 3 défauts corrigés, 14 tests verts.
- Verdicts scellés : `reviews/outil-revue/*.verdict.json` (sha partagé, dépouillables).
- **Reste avant production** : une revue confirmatoire propre 3/3 sur le code FINAL (avec les
  3 correctifs) — à lancer après ton OK, ou après inspection de ta part.
